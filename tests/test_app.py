import io
import json
import re
import zipfile
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

    def fetch_activity_bundle(self, activity_id: str):
        assert activity_id == "42"
        return {
            "activity_id": "42",
            "summary": {
                "activityId": 42,
                "activityName": "Morning Run",
                "activityType": {"typeKey": "running"},
            },
            "details": None,
            "warnings": [],
            "original_fit_zip": b"PK-fake-original",
        }

    def upload_workout(self, workout):
        assert workout["name"] == "Easy Run"
        return "9001"

    def schedule_workout(self, workout_id: str, scheduled_date: str):
        assert workout_id == "9001"
        assert scheduled_date == "2030-01-01"
        return "7001"


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

    response = client.post("/download/42", data={"csrf_token": token})
    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert archive.read("original_fit.zip") == b"PK-fake-original"


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


def test_prompt_plan_upload_review_and_publish(monkeypatch) -> None:
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

    prompt = client.get("/workout-prompt.md")
    assert prompt.status_code == 200
    assert prompt.mimetype == "text/markdown"
    assert b'"workouts": []' in prompt.data
    assert b"Complete valid example" in prompt.data

    client.post(
        "/login",
        data={"csrf_token": token, "email": "athlete@example.com", "password": "secret"},
    )
    payload = {
        "workouts": [
            {
                "date": "2030-01-01",
                "sport": "running",
                "name": "Easy Run",
                "intensity": "easy",
                "steps": [{"type": "main", "duration_minutes": 30}],
            }
        ]
    }
    preview = client.post(
        "/plan",
        data={
            "csrf_token": token,
            "plan_file": (
                io.BytesIO(json.dumps(payload).encode()),
                "plan.json",
            ),
        },
        content_type="multipart/form-data",
    )
    assert preview.status_code == 200
    assert b"Easy Run" in preview.data
    match = re.search(rb'action="/publish/([a-f0-9]+)"', preview.data)
    assert match is not None

    published = client.post(
        f"/publish/{match.group(1).decode()}",
        data={"csrf_token": token, "reviewed": "yes", "schedule": "yes"},
    )
    assert published.status_code == 200
    assert b"uploaded and scheduled" in published.data
    assert b"Garmin ID 9001" in published.data
