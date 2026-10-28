from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta
from decimal import Decimal
from decimal import InvalidOperation
import json
import secrets
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken
from flask import current_app
from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.orm import Session

from givvi.accounts.security import digest
from givvi.accounts.security import now
from givvi.accounts.security import throttle
from givvi.accounts.services import normalized_email
from givvi.errors import ApiError
from givvi.models import EmailMessage
from givvi.models import Event
from givvi.models import EventAssignment
from givvi.models import EventDraw
from givvi.models import EventParticipant
from givvi.models import User

MAX_ROSTER_ENTRIES = 100
MAX_EVENT_BUDGET = Decimal("999999.99")
INVITATION_EMAIL_RETENTION_DAYS = 30
MAX_DRAW_ATTEMPTS = 1000


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
        "is_participant": any(participant.user_id == user_id for participant in participants),
        "drawing_enabled": event.drawing_enabled,
        "can_delete": not event.drawing_enabled and not event.drawing_ever_enabled,
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


def _secure_shuffle(participants: list[EventParticipant]) -> None:
    secrets.SystemRandom().shuffle(participants)


def enable_drawing(database: Session, event: Event) -> dict:
    if event.archived or event.cancelled:
        raise ApiError("event_read_only", 409)
    if event.drawing_enabled:
        return drawing_status(database, event, None)

    participants = roster(database, event.id, lock=True)
    if len(participants) < 3:
        raise ApiError("not_enough_participants", 409)

    recipients = list(participants)
    shuffle = current_app.config.get("DRAW_SHUFFLE", _secure_shuffle)
    for _ in range(MAX_DRAW_ATTEMPTS):
        shuffle(recipients)
        if all(giver.id != recipient.id for giver, recipient in zip(participants, recipients, strict=True)):
            break
    else:
        raise ApiError("draw_generation_failed", 503)

    draw = EventDraw(event_id=event.id, created_at=now(), reset_at=None)
    database.add(draw)
    database.flush()
    database.add_all([
        EventAssignment(
            draw_id=draw.id,
            event_id=event.id,
            giver_participant_id=giver.id,
            recipient_participant_id=recipient.id,
        )
        for giver, recipient in zip(participants, recipients, strict=True)
    ])
    event.drawing_enabled = True
    event.drawing_ever_enabled = True
    database.flush()
    return drawing_status(database, event, None)


def drawing_status(database: Session, event: Event, user_id: str | None) -> dict:
    draw = database.scalar(select(EventDraw).where(
        EventDraw.event_id == event.id, EventDraw.reset_at.is_(None),
    ))
    if event.drawing_enabled and not draw:
        raise ApiError("draw_unavailable", 503)
    participant_count = database.scalar(select(func.count()).select_from(EventParticipant).where(
        EventParticipant.event_id == event.id,
    )) or 0
    is_admin = user_id is None or event.admin_id == user_id
    revealed_count: int | None = 0 if is_admin else None
    has_revealed = False
    if draw:
        if is_admin:
            revealed_count = database.scalar(select(func.count()).select_from(EventAssignment).where(
                EventAssignment.draw_id == draw.id, EventAssignment.revealed_at.is_not(None),
            )) or 0
        if user_id:
            has_revealed = database.scalar(select(EventAssignment.draw_id).join(
                EventParticipant, EventParticipant.id == EventAssignment.giver_participant_id,
            ).where(
                EventAssignment.draw_id == draw.id,
                EventParticipant.user_id == user_id,
                EventAssignment.revealed_at.is_not(None),
            )) is not None
    return {
        "enabled": event.drawing_enabled,
        "participant_count": participant_count,
        "revealed_count": revealed_count,
        "has_revealed": has_revealed,
    }


def reveal_assignment(database: Session, event: Event, user_id: str) -> dict:
    if not event.drawing_enabled:
        raise ApiError("drawing_disabled", 409)
    draw = database.scalar(select(EventDraw).where(
        EventDraw.event_id == event.id, EventDraw.reset_at.is_(None),
    ))
    if not draw:
        raise ApiError("draw_unavailable", 503)
    giver = database.scalar(select(EventParticipant).where(
        EventParticipant.event_id == event.id, EventParticipant.user_id == user_id,
    ))
    if not giver:
        raise ApiError("not_found", 404)
    assignment = database.scalar(select(EventAssignment).where(
        EventAssignment.draw_id == draw.id, EventAssignment.giver_participant_id == giver.id,
    ).with_for_update())
    if not assignment:
        raise ApiError("draw_unavailable", 503)
    if assignment.revealed_at is None:
        if event.archived or event.cancelled:
            raise ApiError("event_read_only", 409)
        assignment.revealed_at = now()
        database.flush()
    recipient = database.get(EventParticipant, assignment.recipient_participant_id)
    if not recipient:
        raise ApiError("draw_unavailable", 503)
    return {"id": recipient.id, "name": recipient.name}


def reset_drawing(database: Session, event: Event) -> dict:
    if event.archived or event.cancelled:
        raise ApiError("event_read_only", 409)
    if not event.drawing_enabled:
        raise ApiError("drawing_disabled", 409)
    draw = database.scalar(select(EventDraw).where(
        EventDraw.event_id == event.id, EventDraw.reset_at.is_(None),
    ).with_for_update())
    if not draw:
        raise ApiError("draw_unavailable", 503)
    database.execute(delete(EventAssignment).where(EventAssignment.draw_id == draw.id))
    database.delete(draw)
    event.drawing_enabled = False
    event.drawing_ever_enabled = False
    database.flush()
    return drawing_status(database, event, None)


def archive_event(event: Event) -> None:
    if event.cancelled:
        raise ApiError("event_read_only", 409)
    event.archived = True


def unarchive_event(event: Event) -> None:
    if event.cancelled:
        raise ApiError("event_read_only", 409)
    event.archived = False


def cancel_event(database: Session, event: Event) -> None:
    event.cancelled = True
    event.invite_token_hash = None
    event.invite_token_encrypted = None
    database.execute(delete(EmailMessage).where(EmailMessage.event_id == event.id))


def delete_event(database: Session, event: Event) -> None:
    if event.drawing_enabled or event.drawing_ever_enabled:
        raise ApiError("event_delete_blocked", 409)
    database.execute(delete(EmailMessage).where(EmailMessage.event_id == event.id))
    database.delete(event)


def transfer_admin(database: Session, event: Event, participant_id: object) -> None:
    if event.archived or event.cancelled:
        raise ApiError("event_read_only", 409)
    if not isinstance(participant_id, str):
        raise ApiError("invalid_request", 400)
    participant = database.scalar(select(EventParticipant).where(
        EventParticipant.id == participant_id,
        EventParticipant.event_id == event.id,
    ).with_for_update())
    if not participant or not participant.user_id or participant.user_id == event.admin_id:
        raise ApiError("transfer_target_invalid", 409)
    event.admin_id = participant.user_id


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


def rotate_invite_token(event: Event) -> str:
    token = secrets.token_urlsafe(32)
    event.invite_token_hash = digest(token)
    event.invite_token_encrypted = Fernet(current_app.config["OUTBOX_KEY"].encode()).encrypt(
        token.encode(),
    ).decode()
    return token


def invite_token(event: Event) -> str:
    if not event.invite_token_hash or not event.invite_token_encrypted:
        raise ApiError("invite_link_missing", 404)
    try:
        token = Fernet(current_app.config["OUTBOX_KEY"].encode()).decrypt(
            event.invite_token_encrypted.encode(),
        ).decode()
    except (InvalidToken, UnicodeDecodeError):
        raise ApiError("invite_link_unavailable", 503) from None
    if digest(token) != event.invite_token_hash:
        raise ApiError("invite_link_unavailable", 503)
    return token


def invitation_link(event: Event, token: str | None = None) -> str:
    active_token = token or invite_token(event)
    return f'{current_app.config["APP_ORIGIN"].rstrip("/")}/invite/{event.id}#token={active_token}'


def validate_invite(event: Event, token: object) -> None:
    if not isinstance(token, str) or not 1 <= len(token) <= 128:
        raise ApiError("invite_invalid", 404)
    if not event.invite_token_hash or not secrets.compare_digest(digest(token), event.invite_token_hash):
        raise ApiError("invite_invalid", 404)
    require_writable(event)


def invitation_preview(database: Session, event_id: str, token: object) -> dict:
    token_digest = digest(token) if isinstance(token, str) else "invalid"
    throttle("invitation_preview", token_digest)
    event = database.get(Event, event_id)
    if not event:
        raise ApiError("invite_invalid", 404)
    validate_invite(event, token)
    return {
        "event_id": event.id,
        "participants": [
            {"id": participant.id, "name": participant.name, "available": participant.user_id is None}
            for participant in roster(database, event.id)
        ],
    }


def claim_participant(database: Session, event: Event, user: User, participant_id: object, token: object) -> None:
    require_writable(event)
    validate_invite(event, token)
    if database.scalar(select(EventParticipant.id).where(
        EventParticipant.event_id == event.id, EventParticipant.user_id == user.id,
    )):
        raise ApiError("already_claimed", 409)
    if not isinstance(participant_id, str):
        raise ApiError("invalid_request", 400)
    participant = database.scalar(select(EventParticipant).where(
        EventParticipant.id == participant_id, EventParticipant.event_id == event.id,
    ).with_for_update())
    if not participant:
        raise ApiError("not_found", 404)
    result = database.execute(update(EventParticipant).where(
        EventParticipant.id == participant.id, EventParticipant.user_id.is_(None),
    ).values(user_id=user.id))
    if result.rowcount != 1:
        raise ApiError("entry_unavailable", 409)


def release_claim(database: Session, event: Event, participant_id: str) -> None:
    require_writable(event)
    participant = database.scalar(select(EventParticipant).where(
        EventParticipant.id == participant_id, EventParticipant.event_id == event.id,
    ).with_for_update())
    if not participant:
        raise ApiError("not_found", 404)
    if participant.user_id is None:
        raise ApiError("participant_not_claimed", 409)
    participant.user_id = None


def queue_invitation_email(database: Session, event: Event, email_value: object) -> None:
    email = normalized_email(email_value)
    recipient = database.scalar(select(User).where(User.email == email))
    language = recipient.language if recipient else "en"
    templates = {
        "en": (f"GIVVI invitation: {event.name}", f"You are invited to join {event.name}. Claim your place:\n"),
        "pl": (f"Zaproszenie GIVVI: {event.name}", f"Zapraszamy do udziału w wydarzeniu {event.name}. Zajmij miejsce:\n"),
    }
    subject, introduction = templates[language]
    token = invite_token(event)
    link = invitation_link(event, token)
    payload = json.dumps({"to": email, "subject": subject, "body": f"{introduction}\n{link}"}, ensure_ascii=False)
    encrypted = Fernet(current_app.config["OUTBOX_KEY"].encode()).encrypt(payload.encode()).decode()
    database.add(EmailMessage(
        user_id=recipient.id if recipient else None,
        event_id=event.id,
        payload=encrypted,
        available_at=now(),
        expires_at=now() + timedelta(days=INVITATION_EMAIL_RETENTION_DAYS),
    ))


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
