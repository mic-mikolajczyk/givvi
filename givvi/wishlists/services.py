from decimal import Decimal
from decimal import InvalidOperation
from urllib.parse import urlsplit

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.orm import Session

from givvi.errors import ApiError
from givvi.models import Gift
from givvi.models import User
from givvi.models import Wishlist

MAX_GIFTS = 200
MAX_GIFT_PRICE = Decimal("999999.99")


def wishlist_for_user(database: Session, user: User, lock: bool = False) -> Wishlist:
    query = select(Wishlist).where(Wishlist.user_id == user.id)
    if lock:
        query = query.with_for_update()
    wishlist = database.scalar(query)
    if not wishlist:
        raise ApiError("not_found", 404)
    return wishlist


def gifts(database: Session, wishlist: Wishlist, lock: bool = False) -> list[Gift]:
    query = select(Gift).where(Gift.wishlist_id == wishlist.user_id).order_by(Gift.position)
    if lock:
        query = query.with_for_update()
    return list(database.scalars(query))


def gift_view(gift: Gift) -> dict:
    return {
        "id": gift.id,
        "name": gift.name,
        "description": gift.description,
        "price": str(gift.price) if gift.price is not None else None,
        "currency": gift.currency,
        "link": gift.link,
        "position": gift.position,
    }


def validate_gift_fields(body: dict, existing: Gift | None = None) -> dict:
    name = body.get("name", existing.name if existing else None)
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise ApiError("validation_error", 400, {"name": "name_length"})

    description = body.get("description", existing.description if existing else None)
    if description is not None and not isinstance(description, str):
        raise ApiError("validation_error", 400, {"description": "field_length"})
    if description is not None and len(description) > 2000:
        raise ApiError("validation_error", 400, {"description": "field_length"})
    description = description.strip() if description and description.strip() else None

    raw_price = body.get("price", existing.price if existing else None)
    if raw_price in (None, ""):
        price = None
    else:
        try:
            price = Decimal(str(raw_price))
        except (InvalidOperation, ValueError):
            raise ApiError("validation_error", 400, {"price": "invalid_price"}) from None
        exponent = price.as_tuple().exponent
        if not price.is_finite() or price < 0 or price > MAX_GIFT_PRICE or not isinstance(exponent, int) or exponent < -2:
            raise ApiError("validation_error", 400, {"price": "invalid_price"})

    currency = body.get("currency", existing.currency if existing else None)
    if price is None and existing is not None and "price" in body and "currency" not in body:
        currency = None
    if currency == "":
        currency = None
    if (currency not in ("EUR", "PLN", None)) or (price is None) != (currency is None):
        raise ApiError("validation_error", 400, {"currency": "invalid_currency"})

    link = body.get("link", existing.link if existing else None)
    if link in (None, ""):
        link = None
    elif not isinstance(link, str) or len(link) > 2048:
        raise ApiError("validation_error", 400, {"link": "invalid_link"})
    else:
        link = link.strip()
        try:
            parsed = urlsplit(link)
            valid = parsed.scheme.lower() in ("http", "https") and bool(parsed.hostname)
            valid = valid and parsed.username is None and parsed.password is None
            valid = valid and not any(character.isspace() or ord(character) < 32 for character in link)
            parsed.port
        except ValueError:
            valid = False
        if not valid:
            raise ApiError("validation_error", 400, {"link": "invalid_link"})

    return {"name": name.strip(), "description": description, "price": price, "currency": currency, "link": link}


def add_gift(database: Session, wishlist: Wishlist, body: dict) -> Gift:
    count = database.scalar(select(func.count()).select_from(Gift).where(Gift.wishlist_id == wishlist.user_id)) or 0
    if count >= MAX_GIFTS:
        raise ApiError("validation_error", 400, {"name": "gift_limit"})
    position = database.scalar(select(func.max(Gift.position)).where(Gift.wishlist_id == wishlist.user_id))
    gift = Gift(wishlist_id=wishlist.user_id, position=(position + 1 if position is not None else 0),
                **validate_gift_fields(body))
    database.add(gift)
    wishlist.order_version += 1
    database.flush()
    return gift


def update_gift(gift: Gift, body: dict) -> None:
    for field, value in validate_gift_fields(body, gift).items():
        setattr(gift, field, value)


def assign_positions(database: Session, wishlist: Wishlist, ordered_gifts: list[Gift]) -> None:
    maximum_position = max((gift.position for gift in ordered_gifts), default=-1)
    offset = maximum_position + len(ordered_gifts) + 1
    if ordered_gifts:
        database.execute(
            update(Gift).where(Gift.wishlist_id == wishlist.user_id).values(position=Gift.position + offset)
        )
        database.flush()
        for position, gift in enumerate(ordered_gifts):
            gift.position = position
        database.flush()


def reorder_gifts(database: Session, wishlist: Wishlist, body: dict) -> list[Gift]:
    supplied_version = body.get("order_version")
    if type(supplied_version) is not int or not isinstance(body.get("gift_ids"), list):
        raise ApiError("invalid_request", 400)
    if supplied_version != wishlist.order_version:
        raise ApiError("order_stale", 409)

    requested_ids = body["gift_ids"]
    if any(not isinstance(gift_id, str) for gift_id in requested_ids) or len(set(requested_ids)) != len(requested_ids):
        raise ApiError("invalid_order", 400)
    current_gifts = gifts(database, wishlist, lock=True)
    if set(requested_ids) != {gift.id for gift in current_gifts}:
        raise ApiError("invalid_order", 400)

    gift_by_id = {gift.id: gift for gift in current_gifts}
    assign_positions(database, wishlist, [gift_by_id[gift_id] for gift_id in requested_ids])
    wishlist.order_version += 1
    database.flush()
    return gifts(database, wishlist)
