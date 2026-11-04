from datetime import timezone
from zoneinfo import ZoneInfo

from flask import Blueprint
from flask import current_app
from flask import jsonify
from flask import request
from flask import Response
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy.orm import Session

from givvi.accounts.security import require_csrf
from givvi.accounts.security import require_user
from givvi.accounts.security import throttle
from givvi.errors import ApiError
from givvi.events import services
from givvi.models import Event
from givvi.models import EventParticipant
from givvi.models import Wishlist
from givvi.wishlists import services as wishlist_services

events = Blueprint("events", __name__, url_prefix="/api/events")


def request_body() -> dict:
    body = request.get_json()
    if not isinstance(body, dict):
        raise ApiError("invalid_request", 400)
    return body


def event_response(
    database: Session,
    event: Event,
    user_id: str,
    participants: list[EventParticipant] | None = None
) -> dict:
    view = services.event_view(event, user_id, services.roster(database, event.id) if participants is None else participants)
    view["period"] = event_period(event)
    return view


def get_admin_event(database: Session, event_id: str, user_id: str, lock: bool = False) -> Event:
    event = services.event_for_user(database, event_id, user_id, lock=lock)
    services.require_admin(event, user_id)
    return event


def event_period(event: Event) -> str:
    clock = current_app.config["CLOCK"]()
    today = clock.astimezone(ZoneInfo(event.time_zone)).date() if clock.tzinfo else clock.replace(
        tzinfo=timezone.utc).astimezone(ZoneInfo(event.time_zone)).date()
    if event.exchange_date < today:
        return "past"
    return "ongoing" if event.exchange_date == today else "upcoming"


@events.get("")
def list_events() -> Response:
    try:
        page = int(request.args.get("page", "1"))
        page_size = int(request.args.get("page_size", "50"))
    except ValueError:
        raise ApiError("invalid_request", 400) from None
    if page < 1 or page_size < 1 or page_size > 100:
        raise ApiError("invalid_request", 400)

    with Session(current_app.extensions["database"]) as database, database.begin():
        user = require_user(database)
        member_event_ids = select(EventParticipant.event_id).where(EventParticipant.user_id == user.id)
        visibility = or_(Event.admin_id == user.id, Event.id.in_(member_event_ids))
        query = select(Event).where(visibility).order_by(Event.exchange_date, Event.id)
        found = list(database.scalars(query.offset((page - 1) * page_size).limit(page_size)))
        total_count = database.scalar(select(func.count()).select_from(Event).where(visibility)) or 0
        rosters: dict[str, list[EventParticipant]] = {event.id: [] for event in found}
        if rosters:
            for participant in database.scalars(select(EventParticipant).where(
                EventParticipant.event_id.in_(rosters),
            ).order_by(EventParticipant.name)):
                rosters[participant.event_id].append(participant)
        result = []
        for event in found:
            result.append(event_response(database, event, user.id, rosters[event.id]))
        return jsonify(events=result, page=page, page_size=page_size, total=total_count)


@events.post("")
def create_event() -> tuple[Response, int]:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        values = services.validate_event_fields(request_body(), user=user)
        services.ensure_valid_local_time(values["exchange_date"], values["exchange_time"], values["time_zone"])
        event = Event(admin_id=user.id, **values)
        database.add(event)
        database.flush()
        return jsonify(event=event_response(database, event, user.id)), 201


@events.get("/<event_id>")
def get_event(event_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        user = require_user(database)
        event = services.event_for_user(database, event_id, user.id)
        return jsonify(event=event_response(database, event, user.id))


@events.post("/<event_id>/archive")
def archive_event(event_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        event = get_admin_event(database, event_id, user.id, lock=True)
        services.archive_event(event)
        return jsonify(event=event_response(database, event, user.id))


@events.delete("/<event_id>/archive")
def unarchive_event(event_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        event = get_admin_event(database, event_id, user.id, lock=True)
        services.unarchive_event(event)
        return jsonify(event=event_response(database, event, user.id))


@events.post("/<event_id>/cancel")
def cancel_event(event_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        event = get_admin_event(database, event_id, user.id, lock=True)
        services.cancel_event(database, event)
        return jsonify(event=event_response(database, event, user.id))


@events.delete("/<event_id>")
def delete_event(event_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        event = get_admin_event(database, event_id, user.id, lock=True)
        services.delete_event(database, event)
        return jsonify(code="event_deleted")


@events.get("/<event_id>/participants/<participant_id>/wishlist")
def get_participant_wishlist(event_id: str, participant_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        user = require_user(database)
        is_member = database.scalar(select(EventParticipant.id).where(
            EventParticipant.event_id == event_id, EventParticipant.user_id == user.id,
        ))
        participant = database.scalar(select(EventParticipant).where(
            EventParticipant.id == participant_id,
            EventParticipant.event_id == event_id,
            EventParticipant.user_id.is_not(None),
        ))
        if not is_member or not participant:
            raise ApiError("not_found", 404)
        wishlist = database.scalar(select(Wishlist).where(Wishlist.user_id == participant.user_id))
        if not wishlist:
            raise ApiError("not_found", 404)
        event = database.get(Event, event_id)
        if not event:
            raise ApiError("not_found", 404)
        return jsonify(
            event={"id": event.id, "name": event.name, "budget": str(event.budget) if event.budget is not None else None,
                   "currency": event.currency},
            participant={"id": participant.id, "name": participant.name},
            gifts=[wishlist_services.gift_view(gift) for gift in wishlist_services.gifts(database, wishlist)],
        )


@events.patch("/<event_id>")
def update_event(event_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        event = get_admin_event(database, event_id, user.id, lock=True)
        services.require_writable(event)
        values = services.validate_event_fields(request_body(), existing=event)
        services.ensure_valid_local_time(values["exchange_date"], values["exchange_time"], values["time_zone"])
        for field, value in values.items():
            setattr(event, field, value)
        database.flush()
        return jsonify(event=event_response(database, event, user.id))


@events.post("/<event_id>/participants")
def create_participant(event_id: str) -> tuple[Response, int]:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        event = get_admin_event(database, event_id, user.id, lock=True)
        participant = services.add_participant(database, event, request_body().get("name"))
        return jsonify(participant={"id": participant.id, "name": participant.name, "claimed": False}), 201


@events.patch("/<event_id>/participants/<participant_id>")
def rename_participant(event_id: str, participant_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        event = get_admin_event(database, event_id, user.id, lock=True)
        services.require_writable(event)
        participant = database.scalar(select(EventParticipant).where(
            EventParticipant.id == participant_id, EventParticipant.event_id == event.id,
        ).with_for_update())
        if not participant:
            raise ApiError("not_found", 404)
        services.update_participant(participant, request_body().get("name"))
        return jsonify(participant={
            "id": participant.id, "name": participant.name, "claimed": participant.user_id is not None,
        })


@events.delete("/<event_id>/participants/<participant_id>")
def remove_participant(event_id: str, participant_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        event = get_admin_event(database, event_id, user.id, lock=True)
        services.require_writable(event)
        participant = database.scalar(select(EventParticipant).where(
            EventParticipant.id == participant_id, EventParticipant.event_id == event.id,
        ).with_for_update())
        if not participant:
            raise ApiError("not_found", 404)
        if participant.user_id is not None:
            raise ApiError("participant_claimed", 409)
        database.delete(participant)
        return jsonify(code="participant_removed")


@events.post("/<event_id>/invite-link")
def regenerate_invite_link(event_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        event = get_admin_event(database, event_id, user.id, lock=True)
        services.require_writable(event)
        token = services.rotate_invite_token(event)
        return jsonify(link=services.invitation_link(event, token))


@events.get("/<event_id>/invite-link")
def get_invite_link(event_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        user = require_user(database)
        event = services.event_for_user(database, event_id, user.id)
        services.require_writable(event)
        return jsonify(link=services.invitation_link(event))


@events.delete("/<event_id>/invite-link")
def revoke_invite_link(event_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        event = get_admin_event(database, event_id, user.id, lock=True)
        services.require_writable(event)
        event.invite_token_hash = None
        event.invite_token_encrypted = None
        return jsonify(code="invite_link_revoked")


@events.post("/<event_id>/invitations")
def send_invitation(event_id: str) -> tuple[Response, int]:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        event = get_admin_event(database, event_id, user.id, lock=True)
        services.require_writable(event)
        email = request_body().get("email")
        throttle("event_invitation", str(email).casefold() if isinstance(email, str) else "")
        if not event.invite_token_hash:
            services.rotate_invite_token(event)
        services.queue_invitation_email(database, event, email)
        return jsonify(code="invitation_queued"), 202


@events.post("/<event_id>/invitation-preview")
def preview_invitation(event_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        invitation = services.invitation_preview(database, event_id, request_body().get("token"))
        return jsonify(invitation=invitation)


@events.post("/<event_id>/claim")
def claim_event_participant(event_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        event = database.scalar(select(Event).where(Event.id == event_id).with_for_update())
        if not event:
            raise ApiError("invite_invalid", 404)
        body = request_body()
        throttle("event_claim", user.email)
        services.claim_participant(database, event, user, body.get("participant_id"), body.get("token"))
        database.flush()
        return jsonify(event=event_response(database, event, user.id), code="claim_completed")


@events.delete("/<event_id>/participants/<participant_id>/claim")
def release_event_claim(event_id: str, participant_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        event = get_admin_event(database, event_id, user.id, lock=True)
        services.release_claim(database, event, participant_id)
        return jsonify(code="claim_released")


@events.post("/<event_id>/drawing")
def enable_event_drawing(event_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        event = get_admin_event(database, event_id, user.id, lock=True)
        return jsonify(drawing=services.enable_drawing(database, event))


@events.get("/<event_id>/drawing")
def get_event_drawing_status(event_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        user = require_user(database)
        event = services.event_for_user(database, event_id, user.id, lock=True)
        return jsonify(drawing=services.drawing_status(database, event, user.id))


@events.post("/<event_id>/reveal")
def reveal_event_assignment(event_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        event = services.event_for_user(database, event_id, user.id, lock=True)
        recipient = services.reveal_assignment(database, event, user.id)
        return jsonify(recipient=recipient)


@events.get("/<event_id>/reveal")
def get_revealed_assignment(event_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        user = require_user(database)
        event = services.event_for_user(database, event_id, user.id, lock=True)
        if not services.drawing_status(database, event, user.id)["has_revealed"]:
            raise ApiError("not_found", 404)
        return jsonify(recipient=services.reveal_assignment(database, event, user.id))


@events.delete("/<event_id>/drawing")
def reset_event_drawing(event_id: str) -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        require_csrf(database)
        user = require_user(database)
        event = get_admin_event(database, event_id, user.id, lock=True)
        return jsonify(drawing=services.reset_drawing(database, event))
