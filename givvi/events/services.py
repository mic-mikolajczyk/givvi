from datetime import date
from datetime import datetime
from datetime import time
from decimal import Decimal
from decimal import InvalidOperation
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from givvi.errors import ApiError
from givvi.models import Event
from givvi.models import EventParticipant
from givvi.models import User

MAX_ROSTER_ENTRIES = 100
MAX_EVENT_BUDGET = Decimal("999999.99")


def event_view(event: Event, user_id: str, participants: list[EventParticipant]) -> dict:
    return {
        "id": event.id,
        "name": event.name,
        "exchange_date": event.exchange_date.isoformat(),
        "exchange_time": event.exchange_time.strftime("%H:%M") if event.exchange_time else None,
        "time_zone": event.time_zone,
        "location": event.location,
        "description": event.description,
        "currency": event.currency,
        "budget": str(event.budget) if event.budget is not None else None,
        "is_admin": event.admin_id == user_id,
        "drawing_enabled": event.drawing_enabled,
        "archived": event.archived,
        "cancelled": event.cancelled,
        "participants": [
            {"id": participant.id, "name": participant.name, "claimed": participant.user_id is not None}
            for participant in participants
        ],
    }


def validate_event_fields(body: dict, existing: Event | None = None, user: User | None = None) -> dict:
    values: dict = {}
    raw_name = body.get("name", existing.name if existing else None)
    if not isinstance(raw_name, str) or not raw_name.strip() or len(raw_name.strip()) > 120:
        raise ApiError("validation_error", 400, {"name": "name_length"})
    values["name"] = raw_name.strip()

    raw_date = body.get("exchange_date", existing.exchange_date.isoformat() if existing else None)
    try:
        if not isinstance(raw_date, str):
            raise ValueError
        values["exchange_date"] = date.fromisoformat(raw_date)
    except ValueError:
        raise ApiError("validation_error", 400, {"exchange_date": "invalid_date"}) from None

    raw_zone = body.get("time_zone", existing.time_zone if existing else "UTC")
    if not isinstance(raw_zone, str) or len(raw_zone) > 64:
        raise ApiError("validation_error", 400, {"time_zone": "invalid_time_zone"})
    try:
        ZoneInfo(raw_zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ApiError("validation_error", 400, {"time_zone": "invalid_time_zone"}) from None
    values["time_zone"] = raw_zone

    raw_time = body.get(
        "exchange_time",
        existing.exchange_time.strftime("%H:%M") if existing and existing.exchange_time else None,
    )
    if raw_time in (None, ""):
        values["exchange_time"] = None
    else:
        try:
            if not isinstance(raw_time, str):
                raise ValueError
            parsed_time = time.fromisoformat(raw_time)
            if parsed_time.tzinfo is not None or parsed_time.second or parsed_time.microsecond:
                raise ValueError
            values["exchange_time"] = parsed_time
        except ValueError:
            raise ApiError("validation_error", 400, {"exchange_time": "invalid_time"}) from None

    for field, maximum in (("location", 255), ("description", 2000)):
        raw_value = body.get(field, getattr(existing, field) if existing else None)
        if raw_value is not None and (not isinstance(raw_value, str) or len(raw_value) > maximum):
            raise ApiError("validation_error", 400, {field: "field_length"})
        values[field] = raw_value.strip() if raw_value and raw_value.strip() else None

    raw_currency = body.get(
        "currency",
        existing.currency if existing else ("PLN" if user and user.language == "pl" else "EUR"),
    )
    if raw_currency not in ("EUR", "PLN"):
        raise ApiError("validation_error", 400, {"currency": "invalid_currency"})
    values["currency"] = raw_currency

    raw_budget = body.get("budget", existing.budget if existing else None)
    if raw_budget in (None, ""):
        values["budget"] = None
    else:
        try:
            budget = Decimal(str(raw_budget))
        except (InvalidOperation, ValueError):
            raise ApiError("validation_error", 400, {"budget": "invalid_budget"}) from None
        if not budget.is_finite():
            raise ApiError("validation_error", 400, {"budget": "invalid_budget"})
        exponent = budget.as_tuple().exponent
        too_precise = not isinstance(exponent, int) or exponent < -2
        if budget < 0 or budget > MAX_EVENT_BUDGET or too_precise:
            raise ApiError("validation_error", 400, {"budget": "invalid_budget"})
        values["budget"] = budget
    return values


def event_for_user(database: Session, event_id: str, user_id: str, lock: bool = False) -> Event:
    query = select(Event).where(Event.id == event_id)
    if lock:
        query = query.with_for_update()
    event = database.scalar(query)
    if not event:
        raise ApiError("not_found", 404)
    is_member = event.admin_id == user_id or database.scalar(
        select(EventParticipant.id).where(EventParticipant.event_id == event.id, EventParticipant.user_id == user_id)
    ) is not None
    if not is_member:
        raise ApiError("not_found", 404)
    return event


def require_admin(event: Event, user_id: str) -> None:
    if event.admin_id != user_id:
        raise ApiError("forbidden", 403)


def require_writable(event: Event) -> None:
    if event.drawing_enabled or event.archived or event.cancelled:
        raise ApiError("event_read_only", 409)


def roster(database: Session, event_id: str, lock: bool = False) -> list[EventParticipant]:
    query = select(EventParticipant).where(EventParticipant.event_id == event_id).order_by(EventParticipant.name)
    if lock:
        query = query.with_for_update()
    return list(database.scalars(query))


def add_participant(database: Session, event: Event, name: object) -> EventParticipant:
    require_writable(event)
    participants = roster(database, event.id, lock=True)
    if len(participants) >= MAX_ROSTER_ENTRIES:
        raise ApiError("validation_error", 400, {"name": "roster_limit"})
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        raise ApiError("validation_error", 400, {"name": "name_length"})
    participant = EventParticipant(event_id=event.id, name=name.strip())
    database.add(participant)
    database.flush()
    return participant


def update_participant(participant: EventParticipant, name: object) -> None:
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        raise ApiError("validation_error", 400, {"name": "name_length"})
    participant.name = name.strip()


def ensure_valid_local_time(exchange_date: date, exchange_time: time | None, time_zone: str) -> None:
    if exchange_time is None:
        return
    zone = ZoneInfo(time_zone)
    local = datetime.combine(exchange_date, exchange_time)
    first = local.replace(tzinfo=zone, fold=0)
    second = local.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        raise ApiError("validation_error", 400, {"exchange_time": "ambiguous_local_time"})
    if first.astimezone(ZoneInfo("UTC")).astimezone(zone).replace(tzinfo=None) != local:
        raise ApiError("validation_error", 400, {"exchange_time": "nonexistent_local_time"})
