from flask import Blueprint
from flask import current_app
from flask import jsonify
from flask import request
from flask import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from givvi.accounts.security import require_csrf
from givvi.accounts.security import require_user
from givvi.errors import ApiError
from givvi.models import Gift
from givvi.wishlists import services

wishlists = Blueprint("wishlists", __name__, url_prefix="/api/wishlist")


def request_body() -> dict:
    body = request.get_json()
    if not isinstance(body, dict):
        raise ApiError("invalid_request", 400)
    return body


@wishlists.get("")
def get_wishlist() -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        user = require_user(database)
        wishlist = services.wishlist_for_user(database, user)
        return jsonify(gifts=[services.gift_view(gift) for gift in services.gifts(database, wishlist)],
                       order_version=wishlist.order_version)


@wishlists.post("/gifts")
def create_gift() -> tuple[Response, int]:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        wishlist = services.wishlist_for_user(database, user, lock=True)
        gift = services.add_gift(database, wishlist, request_body())
        return jsonify(gift=services.gift_view(gift), order_version=wishlist.order_version), 201


@wishlists.patch("/gifts/<gift_id>")
def edit_gift(gift_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        wishlist = services.wishlist_for_user(database, user, lock=True)
        gift = database.scalar(select(Gift).where(
            Gift.id == gift_id, Gift.wishlist_id == wishlist.user_id,
        ).with_for_update())
        if not gift:
            raise ApiError("not_found", 404)
        services.update_gift(gift, request_body())
        return jsonify(gift=services.gift_view(gift), order_version=wishlist.order_version)


@wishlists.delete("/gifts/<gift_id>")
def delete_gift(gift_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        wishlist = services.wishlist_for_user(database, user, lock=True)
        gift = database.scalar(select(Gift).where(
            Gift.id == gift_id, Gift.wishlist_id == wishlist.user_id,
        ).with_for_update())
        if not gift:
            raise ApiError("not_found", 404)
        database.delete(gift)
        database.flush()
        remaining = services.gifts(database, wishlist, lock=True)
        services.assign_positions(database, wishlist, remaining)
        wishlist.order_version += 1
        return jsonify(code="gift_removed", order_version=wishlist.order_version)


@wishlists.patch("/order")
def update_gift_order() -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        wishlist = services.wishlist_for_user(database, user, lock=True)
        reordered = services.reorder_gifts(database, wishlist, request_body())
        return jsonify(gifts=[services.gift_view(gift) for gift in reordered],
                       order_version=wishlist.order_version)
