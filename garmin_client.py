"""Ephemeral Garmin Connect session used by the light exporter."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


class GarminLightError(RuntimeError):
    """A safe error that can be displayed in the web UI."""


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def activity_row(activity: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a Garmin activity for the selection table and ZIP summary."""
    activity_type = activity.get("activityType") or {}
    if isinstance(activity_type, Mapping):
        type_name = activity_type.get("typeKey") or activity_type.get("typeId")
    else:
        type_name = activity_type

    distance = _number(activity.get("distance"))
    duration = _number(activity.get("duration"))
    return {
        "id": activity.get("activityId"),
        "date": activity.get("startTimeLocal") or activity.get("startTimeGMT"),
        "name": activity.get("activityName") or "Untitled activity",
        "type": type_name or "other",
        "distance_km": round(distance / 1000, 2) if distance is not None else None,
        "duration_hours": round(duration / 3600, 2) if duration is not None else None,
        "calories": _number(activity.get("calories")),
        "average_hr": _number(activity.get("averageHR")),
        "max_hr": _number(activity.get("maxHR")),
        "elevation_gain_m": _number(activity.get("elevationGain")),
        "training_effect": _number(activity.get("aerobicTrainingEffect")),
        "anaerobic_training_effect": _number(activity.get("anaerobicTrainingEffect")),
        "training_load": _number(activity.get("activityTrainingLoad")),
        "average_power": _number(activity.get("avgPower")),
        "normalized_power": _number(activity.get("normPower")),
        "max_power": _number(activity.get("maxPower")),
    }


@dataclass
class LoginResult:
    api: Garmin | None
    pending_mfa: Garmin | None


class GarminLightService:
    """Authenticate and retrieve activities without writing tokens or data to disk."""

    def __init__(self, api: Garmin) -> None:
        self.api = api

    @classmethod
    def login(cls, email: str, password: str) -> LoginResult:
        if not email.strip() or not password:
            raise GarminLightError("Enter your Garmin email and password.")
        try:
            api = Garmin(
                email=email.strip(),
                password=password,
                return_on_mfa=True,
            )
            mfa_status, _ = api.login()
            if mfa_status == "needs_mfa":
                return LoginResult(api=None, pending_mfa=api)
            # garminconnect intentionally returns before profile loading whenever
            # return_on_mfa=True, including logins that did not require MFA.
            api._load_profile_and_settings()  # noqa: SLF001
            api.password = None
            return LoginResult(api=api, pending_mfa=None)
        except GarminConnectTooManyRequestsError as exc:
            raise GarminLightError(
                "Garmin rate-limited the login. Wait and try again later."
            ) from exc
        except GarminConnectAuthenticationError as exc:
            raise GarminLightError("Garmin rejected the email or password.") from exc
        except GarminConnectConnectionError as exc:
            raise GarminLightError(f"Could not reach Garmin Connect: {exc}") from exc

    @classmethod
    def finish_mfa(cls, pending_api: Garmin, code: str) -> GarminLightService:
        if not code.strip():
            raise GarminLightError("Enter the verification code sent by Garmin.")
        try:
            pending_api.resume_login({}, code.strip())
            pending_api.password = None
            return cls(pending_api)
        except GarminConnectTooManyRequestsError as exc:
            raise GarminLightError(
                "Garmin rate-limited MFA verification. Try again later."
            ) from exc
        except GarminConnectAuthenticationError as exc:
            raise GarminLightError("Garmin rejected the verification code.") from exc
        except GarminConnectConnectionError as exc:
            raise GarminLightError(f"Could not complete Garmin verification: {exc}") from exc

    @property
    def display_name(self) -> str:
        try:
            return self.api.get_full_name() or "Garmin user"
        except Exception:
            return "Garmin user"

    def activities_on(self, day: date) -> list[dict[str, Any]]:
        try:
            activities = self.api.get_activities_by_date(day.isoformat(), day.isoformat())
            return [
                activity_row(item)
                for item in activities or []
                if isinstance(item, Mapping) and item.get("activityId") is not None
            ]
        except GarminConnectTooManyRequestsError as exc:
            raise GarminLightError(
                "Garmin rate-limited the activity request. Try again later."
            ) from exc
        except GarminConnectAuthenticationError as exc:
            raise GarminLightError("The Garmin session expired. Log in again.") from exc
        except GarminConnectConnectionError as exc:
            raise GarminLightError(f"Could not fetch Garmin activities: {exc}") from exc

    def _safe_call(
        self,
        label: str,
        method: Callable[..., Any],
        *args: Any,
    ) -> tuple[Any, str | None]:
        try:
            return method(*args), None
        except GarminConnectTooManyRequestsError:
            return None, f"{label}: Garmin rate limit reached; try again later."
        except GarminConnectAuthenticationError:
            return None, f"{label}: Garmin session expired; log in again."
        except GarminConnectConnectionError as exc:
            return None, f"{label}: unavailable ({exc})."
        except Exception as exc:
            return None, f"{label}: unexpected Garmin response ({exc})."

    def fetch_activity_bundle(self, activity_id: str) -> dict[str, Any]:
        """Fetch readable detail endpoints and the untouched original FIT archive."""
        endpoints: tuple[tuple[str, Callable[..., Any]], ...] = (
            ("summary", self.api.get_activity),
            ("details", self.api.get_activity_details),
            ("splits", self.api.get_activity_splits),
            ("typed_splits", self.api.get_activity_typed_splits),
            ("split_summaries", self.api.get_activity_split_summaries),
            ("weather", self.api.get_activity_weather),
            ("heart_rate_zones", self.api.get_activity_hr_in_timezones),
            ("power_zones", self.api.get_activity_power_in_timezones),
            ("exercise_sets", self.api.get_activity_exercise_sets),
        )
        bundle: dict[str, Any] = {"activity_id": str(activity_id), "warnings": []}
        for key, method in endpoints:
            if key == "details":
                value, warning = self._safe_call(
                    "Full activity details", method, activity_id, 50000, 50000
                )
            else:
                value, warning = self._safe_call(
                    key.replace("_", " ").title(), method, activity_id
                )
            bundle[key] = value
            if warning:
                bundle["warnings"].append(warning)

        original, warning = self._safe_call(
            "Original FIT download",
            self.api.download_activity,
            activity_id,
            Garmin.ActivityDownloadFormat.ORIGINAL,
        )
        bundle["original_fit_zip"] = original
        if warning:
            bundle["warnings"].append(warning)
        if bundle.get("details") is None and original is None:
            raise GarminLightError(
                "Garmin returned neither readable details nor the original FIT file."
            )
        return bundle
