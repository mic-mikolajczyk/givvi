from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from givvi.models import Gift
from givvi.models import User


def register(client, app, email: str) -> str:
    csrf = client.get("/api/auth/csrf").json["csrf_token"]
    response = client.post("/api/auth/register", json={
        "name": "Wishlist owner", "email": email, "password": "correct horse battery staple",
    }, headers={"X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"]})
    assert response.status_code == 201
    return response.json["csrf_token"]


@pytest.mark.integration
def test_competing_reorders_serialize_and_reject_the_stale_version(migrated_app) -> None:
    app, unused_config = migrated_app
    email = f"wishlist-race-{uuid4()}@example.com"
    first_client = app.test_client()
    first_csrf = register(first_client, app, email)
    created = []
    for name in ("First", "Second"):
        response = first_client.post("/api/wishlist/gifts", json={"name": name}, headers={
            "X-CSRF-Token": first_csrf, "Origin": app.config["APP_ORIGIN"],
        })
        assert response.status_code == 201
        created.append(response.json["gift"]["id"])

    second_client = app.test_client()
    login_csrf = second_client.get("/api/auth/csrf").json["csrf_token"]
    login = second_client.post("/api/auth/login", json={
        "email": email, "password": "correct horse battery staple",
    }, headers={"X-CSRF-Token": login_csrf, "Origin": app.config["APP_ORIGIN"]})
    assert login.status_code == 200
    second_csrf = login.json["csrf_token"]
    barrier = Barrier(2)

    def reorder(client, csrf: str, gift_ids: list[str]) -> int:
        barrier.wait(timeout=10)
        return client.patch("/api/wishlist/order", json={
            "gift_ids": gift_ids, "order_version": 2,
        }, headers={"X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"]}).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(reorder, first_client, first_csrf, created[::-1]),
            executor.submit(reorder, second_client, second_csrf, created),
        ]
        statuses = [future.result() for future in futures]

    assert sorted(statuses) == [200, 409]
    with Session(app.extensions["database"]) as database:
        ordered_gifts = list(database.scalars(select(Gift).order_by(Gift.position)))
        assert [gift.position for gift in ordered_gifts] == [0, 1]
        assert {gift.id for gift in ordered_gifts} == set(created)


@pytest.mark.integration
def test_postgresql_enforces_gift_currency_and_unique_order_constraints(migrated_app) -> None:
    app, unused_config = migrated_app
    client = app.test_client()
    email = f"wishlist-constraints-{uuid4()}@example.com"
    csrf = register(client, app, email)
    created = client.post("/api/wishlist/gifts", json={"name": "Valid"}, headers={
        "X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"],
    })
    assert created.status_code == 201
    with Session(app.extensions["database"]) as database:
        user_id = database.scalar(select(User.id).where(User.email == email))
    assert user_id is not None

    with Session(app.extensions["database"]) as database, pytest.raises(IntegrityError):
        with database.begin():
            database.add(Gift(
                wishlist_id=user_id, name="Invalid price", price=Decimal("1.00"),
                currency=None, position=1,
            ))
            database.flush()

    with Session(app.extensions["database"]) as database, pytest.raises(IntegrityError):
        with database.begin():
            database.add(Gift(wishlist_id=user_id, name="Duplicate position", position=0))
            database.flush()
