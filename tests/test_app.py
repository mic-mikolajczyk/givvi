from cryptography.fernet import Fernet
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
    monkeypatch.setenv("GIVVI_OUTBOX_KEY", Fernet.generate_key().decode())
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


@pytest.mark.parametrize("override", [
    {"DEBUG": True},
    {"TESTING": True},
    {"COOKIE_SECURE": False},
    {"APP_ORIGIN": "http://givvi.example"},
    {"APP_ORIGIN": "https://givvi.example/path"},
    {"DATABASE_URL": "sqlite://"},
    {"DATABASE_URL": "postgresql+psycopg://givvi@db/givvi?sslmode=require"},
    {"SMTP_TLS": False},
    {"METRICS_TOKEN": "short"},
    {"OUTBOX_KEY": "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="},
])
def test_production_rejects_unsafe_configuration(override: dict) -> None:
    config = {
        "ENVIRONMENT": "production", "DATABASE_URL": "postgresql+psycopg://givvi@db/givvi?sslmode=verify-full",
        "OUTBOX_KEY": Fernet.generate_key().decode(), "METRICS_TOKEN": "operator-only-test-token-at-least-32-chars",
        "APP_ORIGIN": "https://givvi.example", "SMTP_TLS": True,
    }
    config.update(override)

    with pytest.raises(RuntimeError, match="Production"):
        create_app(config)


def test_metrics_are_protected_and_contain_only_aggregates(account_app: Flask) -> None:
    client = account_app.test_client()
    assert client.get("/api/health/metrics").status_code == 404
    account_app.config["METRICS_TOKEN"] = "private-monitor-token"
    assert client.get("/api/health/metrics").status_code == 404
    assert client.get("/api/health/metrics", headers={"Authorization": "Bearer incorrect"}).status_code == 404

    response = client.get("/api/health/metrics", headers={"Authorization": "Bearer private-monitor-token"})

    assert response.status_code == 200
    assert "givvi_outbox_pending 0" in response.text
    assert "givvi_outbox_failed 0" in response.text
    assert "private-monitor-token" not in response.text
    assert response.headers["Cache-Control"] == "no-store"


def test_security_headers_and_request_logs_do_not_include_raw_urls(app: Flask, caplog) -> None:
    with caplog.at_level("INFO", logger=app.logger.name):
        response = app.test_client().get("/api/health/live?token=private-url-secret")

    assert response.headers["Content-Security-Policy"] == (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Request completed" in caplog.text
    assert "private-url-secret" not in caplog.text


def test_secret_files_are_loaded_without_logging_contents(tmp_path, monkeypatch, caplog) -> None:
    secret_file = tmp_path / "outbox-key"
    key = Fernet.generate_key().decode()
    secret_file.write_text(f"{key}\n")
    monkeypatch.setenv("GIVVI_OUTBOX_KEY_FILE", str(secret_file))

    application = create_app({"TESTING": True, "DATABASE_URL": "sqlite://"})

    assert application.config["OUTBOX_KEY"] == key
    assert key not in caplog.text
    application.extensions["database"].dispose()


def test_production_rejects_flask_debug_environment(monkeypatch) -> None:
    monkeypatch.setenv("FLASK_DEBUG", "1")

    with pytest.raises(RuntimeError, match="Production"):
        create_app({
            "ENVIRONMENT": "production", "DATABASE_URL": "postgresql+psycopg://givvi@db/givvi?sslmode=verify-full",
            "OUTBOX_KEY": Fernet.generate_key().decode(), "METRICS_TOKEN": "operator-only-test-token-at-least-32-chars",
            "APP_ORIGIN": "https://givvi.example", "SMTP_TLS": True,
        })


def test_production_error_identifies_invalid_settings_without_values() -> None:
    config = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+psycopg://private_user:private_password@db/private_database?sslmode=require",
        "OUTBOX_KEY": Fernet.generate_key().decode(),
        "METRICS_TOKEN": "operator-only-test-token-at-least-32-chars",
        "APP_ORIGIN": "http://givvi.example",
        "SMTP_TLS": False,
    }

    with pytest.raises(RuntimeError) as error:
        create_app(config)

    message = str(error.value)
    assert "APP_ORIGIN" in message
    assert "DATABASE_URL" in message
    assert "SMTP_TLS" in message
    for sensitive_value in ("private_user", "private_password", "private_database"):
        assert sensitive_value not in message
