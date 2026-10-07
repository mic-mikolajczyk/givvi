from flask import Flask
import pytest

from givvi import create_app


def test_app_instances_have_isolated_configuration() -> None:
    first = create_app({"TESTING": True, "DATABASE_URL": "sqlite://", "INSTANCE_LABEL": "first"})
    second = create_app({"TESTING": True, "DATABASE_URL": "sqlite://", "INSTANCE_LABEL": "second"})

    first.config["INSTANCE_LABEL"] = "changed"

    assert second.config["INSTANCE_LABEL"] == "second"
    first.extensions["database"].dispose()
    second.extensions["database"].dispose()


def test_readiness_checks_database(app: Flask) -> None:
    response = app.test_client().get("/api/health/ready")

    assert response.status_code == 200
    assert response.json == {"status": "ready"}
    assert response.headers["Cache-Control"] == "no-store"


def test_missing_database_configuration_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GIVVI_DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="GIVVI_DATABASE_URL"):
        create_app()


def test_environment_configuration_is_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIVVI_DATABASE_URL", "sqlite://")
    application = create_app()

    assert application.config["DATABASE_URL"] == "sqlite://"
    assert application.debug is False
    application.extensions["database"].dispose()


def test_liveness_does_not_depend_on_database(app: Flask) -> None:
    response = app.test_client().get("/api/health/live")

    assert response.status_code == 200
    assert response.json == {"status": "alive"}


def test_unavailable_database_does_not_leak_connection_details(caplog: pytest.LogCaptureFixture) -> None:
    application = create_app({
        "TESTING": True,
        "DATABASE_URL": "postgresql+psycopg://private_user:private_password@127.0.0.1:1/private_database",
    })

    response = application.test_client().get("/api/health/ready")

    assert response.status_code == 503
    assert response.json == {"status": "unavailable"}
    assert "Database readiness check failed" in caplog.text
    for sensitive_value in ("private_user", "private_password", "private_database"):
        assert sensitive_value not in response.get_data(as_text=True)
        assert sensitive_value not in caplog.text
    application.extensions["database"].dispose()
