import os

import pytest

from givvi import create_app


@pytest.mark.integration
def test_readiness_against_postgresql() -> None:
    database_url = os.environ.get("GIVVI_TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("GIVVI_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    application = create_app({"TESTING": True, "DATABASE_URL": database_url})

    try:
        response = application.test_client().get("/api/health/ready")

        assert application.extensions["database"].dialect.name == "postgresql"
        assert response.status_code == 200
        assert response.json == {"status": "ready"}
    finally:
        application.extensions["database"].dispose()
