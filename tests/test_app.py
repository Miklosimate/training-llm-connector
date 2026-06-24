from datetime import date

from app import create_app
from garmin_client import LoginResult


class FakeService:
    display_name = "Test Athlete"

    def activities_on(self, selected: date):
        assert selected == date(2026, 6, 24)
        return [
            {
                "id": "42",
                "name": "Morning Run",
                "type": "running",
                "distance_km": 10.0,
                "duration_hours": 1.0,
            }
        ]


class FakeGarminLightService:
    @classmethod
    def login(cls, email: str, password: str) -> LoginResult:
        assert email == "athlete@example.com"
        assert password == "secret"
        return LoginResult(api=object(), pending_mfa=None)

    def __new__(cls, api):
        return FakeService()


def csrf(client) -> str:
    client.get("/")
    with client.session_transaction() as flask_session:
        return flask_session["csrf_token"]


def test_login_and_activity_list(monkeypatch) -> None:
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SESSION_COOKIE_SECURE": False,
        }
    )
    client = app.test_client()
    token = csrf(client)

    monkeypatch.setattr("app.GarminLightService", FakeGarminLightService)

    response = client.post(
        "/login",
        data={"csrf_token": token, "email": "athlete@example.com", "password": "secret"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Connected as Test Athlete" in response.data

    response = client.post(
        "/activities",
        data={"csrf_token": token, "date": "2026-06-24"},
    )
    assert response.status_code == 200
    assert b"Morning Run" in response.data
    assert b"Download full ZIP" in response.data


def test_post_requires_csrf() -> None:
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SESSION_COOKIE_SECURE": False,
        }
    )
    response = app.test_client().post("/logout")
    assert response.status_code == 400
