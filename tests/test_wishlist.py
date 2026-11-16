def register(client, app, email: str) -> str:
    csrf = client.get("/api/auth/csrf").json["csrf_token"]
    response = client.post("/api/auth/register", json={
        "name": "Wishlist owner", "email": email, "password": "correct horse battery staple",
    }, headers={"X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"]})
    assert response.status_code == 201
    return response.json["csrf_token"]


def post(client, app, csrf: str, path: str, body: dict):
    return client.post(path, json=body, headers={"X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"]})


def test_owner_manages_gifts_and_order(account_app) -> None:
    client = account_app.test_client()
    csrf = register(client, account_app, "wishlist-owner@example.com")

    empty = client.get("/api/wishlist")
    first = post(client, account_app, csrf, "/api/wishlist/gifts", {
        "name": "  Wool scarf  ", "description": "Blue", "price": "35.50", "currency": "EUR",
        "link": "https://shop.example/scarf",
    })
    second = post(client, account_app, csrf, "/api/wishlist/gifts", {"name": "Book"})

    assert empty.status_code == 200
    assert empty.json == {"gifts": [], "order_version": 0}
    assert first.status_code == 201
    assert first.json["gift"] == {
        "id": first.json["gift"]["id"], "name": "Wool scarf", "description": "Blue", "price": "35.50",
        "currency": "EUR", "link": "https://shop.example/scarf", "position": 0,
    }
    assert second.status_code == 201
    assert [gift["name"] for gift in client.get("/api/wishlist").json["gifts"]] == ["Wool scarf", "Book"]

    reorder = client.patch("/api/wishlist/order", json={
        "gift_ids": [second.json["gift"]["id"], first.json["gift"]["id"]], "order_version": 2,
    }, headers={"X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"]})

    assert reorder.status_code == 200
    assert reorder.json["order_version"] == 3
    assert [gift["name"] for gift in client.get("/api/wishlist").json["gifts"]] == ["Book", "Wool scarf"]

    updated = client.patch(f"/api/wishlist/gifts/{first.json['gift']['id']}", json={"name": "Warm scarf"}, headers={
        "X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"],
    })
    assert updated.status_code == 200
    assert updated.json["gift"]["name"] == "Warm scarf"

    removed = client.delete(f"/api/wishlist/gifts/{second.json['gift']['id']}", headers={
        "X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"],
    })
    assert removed.status_code == 200
    assert [gift["name"] for gift in client.get("/api/wishlist").json["gifts"]] == ["Warm scarf"]


def test_gift_validation_and_stale_order_are_rejected(account_app) -> None:
    client = account_app.test_client()
    csrf = register(client, account_app, "wishlist-validation@example.com")
    created = post(client, account_app, csrf, "/api/wishlist/gifts", {"name": "Gift"})
    gift_id = created.json["gift"]["id"]

    invalid = [
        {"name": "  "},
        {"name": "Gift", "price": "1.001", "currency": "EUR"},
        {"name": "Gift", "price": "1000000.00", "currency": "EUR"},
        {"name": "Gift", "price": "10.00"},
        {"name": "Gift", "price": "10.00", "currency": "USD"},
        {"name": "Gift", "link": "javascript:alert(1)"},
        {"name": "Gift", "link": "https://user:pass@example.com/"},
    ]
    responses = [post(client, account_app, csrf, "/api/wishlist/gifts", body) for body in invalid]
    duplicate = client.patch("/api/wishlist/order", json={
        "gift_ids": [gift_id, gift_id], "order_version": 1,
    }, headers={"X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"]})
    missing = client.patch("/api/wishlist/order", json={
        "gift_ids": [], "order_version": 1,
    }, headers={"X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"]})
    stale = client.patch("/api/wishlist/order", json={
        "gift_ids": [gift_id], "order_version": 0,
    }, headers={"X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"]})

    assert all(response.status_code == 400 for response in responses)
    assert duplicate.status_code == 400
    assert missing.status_code == 400
    assert stale.status_code == 409
    assert client.get("/api/wishlist").json["order_version"] == 1


def test_deleting_a_middle_gift_compacts_positions_without_conflicts(account_app) -> None:
    client = account_app.test_client()
    csrf = register(client, account_app, "wishlist-delete@example.com")
    created = [
        post(client, account_app, csrf, "/api/wishlist/gifts", {"name": name}).json["gift"]
        for name in ("First", "Middle", "Last")
    ]

    removed = client.delete(f"/api/wishlist/gifts/{created[1]['id']}", headers={
        "X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"],
    })
    wishlist = client.get("/api/wishlist").json

    assert removed.status_code == 200
    assert removed.json["order_version"] == 4
    assert [(gift["name"], gift["position"]) for gift in wishlist["gifts"]] == [("First", 0), ("Last", 1)]


def test_clearing_a_gift_price_clears_its_currency(account_app) -> None:
    client = account_app.test_client()
    csrf = register(client, account_app, "wishlist-price-clear@example.com")
    created = post(client, account_app, csrf, "/api/wishlist/gifts", {
        "name": "Price later", "price": "12.50", "currency": "PLN",
    })

    updated = client.patch(f"/api/wishlist/gifts/{created.json['gift']['id']}", json={"price": None}, headers={
        "X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"],
    })

    assert updated.status_code == 200
    assert updated.json["gift"]["price"] is None
    assert updated.json["gift"]["currency"] is None


def test_gift_links_are_validated_without_fetching_them(account_app) -> None:
    client = account_app.test_client()
    csrf = register(client, account_app, "wishlist-link@example.com")

    response = post(client, account_app, csrf, "/api/wishlist/gifts", {
        "name": "Local product", "link": "http://127.0.0.1:1/private",
    })

    assert response.status_code == 201
    assert response.json["gift"]["link"] == "http://127.0.0.1:1/private"


def test_gifts_are_private_and_owner_only(account_app) -> None:
    owner = account_app.test_client()
    owner_csrf = register(owner, account_app, "private-wishlist@example.com")
    created = post(owner, account_app, owner_csrf, "/api/wishlist/gifts", {"name": "Private gift"})

    anonymous = account_app.test_client()
    other = account_app.test_client()
    other_csrf = register(other, account_app, "other-wishlist@example.com")

    assert anonymous.get("/api/wishlist").status_code == 401
    assert other.get("/api/wishlist").json["gifts"] == []
    denied = other.patch(f"/api/wishlist/gifts/{created.json['gift']['id']}", json={"name": "Taken"}, headers={
        "X-CSRF-Token": other_csrf, "Origin": account_app.config["APP_ORIGIN"],
    })
    assert denied.status_code == 404


def test_event_wishlists_require_claimed_membership_and_hide_account_identity(account_app) -> None:
    admin = account_app.test_client()
    admin_csrf = register(admin, account_app, "wishlist-event-admin@example.com")
    created_event = post(admin, account_app, admin_csrf, "/api/events", {
        "name": "Gift exchange", "exchange_date": "2026-12-20", "time_zone": "UTC",
        "currency": "EUR", "budget": "30.00",
    })
    event_id = created_event.json["event"]["id"]
    target_entry = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/participants", {"name": "Target name"})
    viewer_entry = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/participants", {"name": "Viewer name"})
    invite_link = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/invite-link", {}).json["link"]
    token = invite_link.split("#token=", 1)[1]

    target = account_app.test_client()
    target_csrf = register(target, account_app, "wishlist-target@example.com")
    post(target, account_app, target_csrf, "/api/wishlist/gifts", {
        "name": "Gift idea", "price": "45.00", "currency": "EUR",
    })
    target_claim = post(target, account_app, target_csrf, f"/api/events/{event_id}/claim", {
        "participant_id": target_entry.json["participant"]["id"], "token": token,
    })

    viewer = account_app.test_client()
    viewer_csrf = register(viewer, account_app, "wishlist-viewer@example.com")
    viewer_claim = post(viewer, account_app, viewer_csrf, f"/api/events/{event_id}/claim", {
        "participant_id": viewer_entry.json["participant"]["id"], "token": token,
    })
    target_wishlist = viewer.get(
        f"/api/events/{event_id}/participants/{target_entry.json['participant']['id']}/wishlist",
    )
    admin_access = admin.get(
        f"/api/events/{event_id}/participants/{target_entry.json['participant']['id']}/wishlist",
    )
    outsider = account_app.test_client()
    register(outsider, account_app, "wishlist-outsider@example.com")
    outsider_access = outsider.get(
        f"/api/events/{event_id}/participants/{target_entry.json['participant']['id']}/wishlist",
    )

    assert target_claim.status_code == 200
    assert viewer_claim.status_code == 200
    assert target_wishlist.status_code == 200
    assert target_wishlist.json["event"] == {"id": event_id, "name": "Gift exchange", "budget": "30.00", "currency": "EUR"}
    assert target_wishlist.json["participant"] == {
        "id": target_entry.json["participant"]["id"], "name": "Target name",
    }
    assert target_wishlist.json["gifts"][0]["name"] == "Gift idea"
    assert "email" not in str(target_wishlist.json)
    assert "wishlist-target@example.com" not in str(target_wishlist.json)

    assert admin_access.status_code == 404
    assert outsider_access.status_code == 404

    released = admin.delete(
        f"/api/events/{event_id}/participants/{target_entry.json['participant']['id']}/claim",
        headers={"X-CSRF-Token": admin_csrf, "Origin": account_app.config["APP_ORIGIN"]},
    )
    removed_member_access = viewer.get(
        f"/api/events/{event_id}/participants/{target_entry.json['participant']['id']}/wishlist",
    )
    assert released.status_code == 200
    assert removed_member_access.status_code == 404
