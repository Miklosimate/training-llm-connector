"""Garmin Light: ephemeral Garmin activity exporter for WSGI hosting."""

from __future__ import annotations

import hmac
import logging
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from io import BytesIO
from typing import Any

from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from exporter import full_activity_export
from garmin_client import GarminLightError, GarminLightService, LoginResult, activity_row


@dataclass
class EphemeralSession:
    service: GarminLightService | None = None
    pending_mfa: Any | None = None
    last_seen: float = field(default_factory=time.monotonic)


class EphemeralSessionStore:
    """Process-local state with expiration; nothing is written to disk."""

    def __init__(self, ttl_seconds: int = 3600, maximum_sessions: int = 64) -> None:
        self.ttl_seconds = ttl_seconds
        self.maximum_sessions = maximum_sessions
        self._items: dict[str, EphemeralSession] = {}
        self._lock = threading.RLock()

    def _prune(self) -> None:
        cutoff = time.monotonic() - self.ttl_seconds
        expired = [key for key, value in self._items.items() if value.last_seen < cutoff]
        for key in expired:
            self._items.pop(key, None)
        while len(self._items) >= self.maximum_sessions:
            oldest = min(self._items, key=lambda key: self._items[key].last_seen)
            self._items.pop(oldest, None)

    def get(self, key: str) -> EphemeralSession:
        with self._lock:
            self._prune()
            state = self._items.setdefault(key, EphemeralSession())
            state.last_seen = time.monotonic()
            return state

    def delete(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)


def _enabled(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    configured_secret = os.environ.get("GARMIN_LIGHT_SECRET_KEY")
    if not configured_secret:
        configured_secret = secrets.token_hex(32)
        logging.getLogger(__name__).warning(
            "GARMIN_LIGHT_SECRET_KEY is unset; browser sessions will reset after app restart."
        )
    app.config.from_mapping(
        SECRET_KEY=configured_secret,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_enabled(
            os.environ.get("GARMIN_LIGHT_SECURE_COOKIE"), default=True
        ),
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    store = EphemeralSessionStore(
        ttl_seconds=int(os.environ.get("GARMIN_LIGHT_SESSION_TTL", "3600")),
        maximum_sessions=int(os.environ.get("GARMIN_LIGHT_MAX_SESSIONS", "64")),
    )
    app.extensions["garmin_session_store"] = store

    def session_id() -> str:
        key = session.get("garmin_light_id")
        if not isinstance(key, str):
            key = uuid.uuid4().hex
            session["garmin_light_id"] = key
        return key

    def state() -> EphemeralSession:
        return store.get(session_id())

    def csrf_token() -> str:
        token = session.get("csrf_token")
        if not isinstance(token, str):
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return token

    def valid_csrf() -> bool:
        expected = session.get("csrf_token")
        supplied = request.form.get("csrf_token", "")
        return (
            isinstance(expected, str)
            and isinstance(supplied, str)
            and hmac.compare_digest(expected, supplied)
        )

    def require_csrf() -> Response | None:
        if valid_csrf():
            return None
        return Response("Invalid or expired form. Reload the page and try again.", status=400)

    def render_home(
        *,
        selected_date: str | None = None,
        activities: list[dict[str, Any]] | None = None,
    ) -> str:
        current = state()
        return render_template(
            "index.html",
            csrf_token=csrf_token(),
            today=date.today().isoformat(),
            selected_date=selected_date or date.today().isoformat(),
            activities=activities,
            connected=current.service is not None,
            pending_mfa=current.pending_mfa is not None,
            display_name=current.service.display_name if current.service else None,
        )

    @app.get("/")
    def index() -> str:
        return render_home()

    @app.post("/login")
    def login() -> Response | str:
        rejected = require_csrf()
        if rejected:
            return rejected
        current = state()
        try:
            result: LoginResult = GarminLightService.login(
                request.form.get("email", ""),
                request.form.get("password", ""),
            )
            current.service = (
                GarminLightService(result.api) if result.api is not None else None
            )
            current.pending_mfa = result.pending_mfa
            if current.pending_mfa is not None:
                flash("Enter the verification code Garmin sent you.", "info")
            else:
                flash("Connected to Garmin.", "success")
            return redirect(url_for("index"))
        except GarminLightError as exc:
            flash(str(exc), "error")
            return render_home()

    @app.post("/mfa")
    def mfa() -> Response | str:
        rejected = require_csrf()
        if rejected:
            return rejected
        current = state()
        if current.pending_mfa is None:
            flash("The Garmin verification session expired. Log in again.", "error")
            return redirect(url_for("index"))
        try:
            current.service = GarminLightService.finish_mfa(
                current.pending_mfa,
                request.form.get("code", ""),
            )
            current.pending_mfa = None
            flash("Connected to Garmin.", "success")
            return redirect(url_for("index"))
        except GarminLightError as exc:
            flash(str(exc), "error")
            return render_home()

    @app.post("/logout")
    def logout() -> Response:
        rejected = require_csrf()
        if rejected:
            return rejected
        key = session.get("garmin_light_id")
        if isinstance(key, str):
            store.delete(key)
        session.clear()
        return redirect(url_for("index"))

    @app.post("/activities")
    def activities() -> Response | str:
        rejected = require_csrf()
        if rejected:
            return rejected
        current = state()
        if current.service is None:
            flash("Log in to Garmin first.", "error")
            return redirect(url_for("index"))
        raw_day = request.form.get("date", "")
        try:
            selected_day = date.fromisoformat(raw_day)
        except ValueError:
            flash("Choose a valid date.", "error")
            return render_home()
        if selected_day > date.today():
            flash("The activity date cannot be in the future.", "error")
            return render_home(selected_date=raw_day)
        try:
            found = current.service.activities_on(selected_day)
            if not found:
                flash("No Garmin activities were found on that date.", "info")
            return render_home(selected_date=raw_day, activities=found)
        except GarminLightError as exc:
            flash(str(exc), "error")
            return render_home(selected_date=raw_day)

    @app.post("/download/<activity_id>")
    def download(activity_id: str) -> Response:
        rejected = require_csrf()
        if rejected:
            return rejected
        current = state()
        if current.service is None:
            flash("The Garmin session expired. Log in again.", "error")
            return redirect(url_for("index"))
        if not activity_id.isdigit():
            return Response("Invalid activity ID.", status=400)
        try:
            bundle = current.service.fetch_activity_bundle(activity_id)
            raw_summary = bundle.get("summary")
            summary = activity_row(raw_summary) if isinstance(raw_summary, dict) else {
                "id": activity_id
            }
            payload = full_activity_export(summary, bundle)
            return send_file(
                BytesIO(payload),
                mimetype="application/zip",
                as_attachment=True,
                download_name=f"garmin_full_workout_{activity_id}.zip",
                max_age=0,
            )
        except GarminLightError as exc:
            flash(str(exc), "error")
            return redirect(url_for("index"))

    @app.after_request
    def security_headers(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; form-action 'self'; "
            "frame-ancestors 'none'; base-uri 'self'"
        )
        return response

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)

