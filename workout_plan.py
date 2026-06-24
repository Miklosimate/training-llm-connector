"""Validation and Garmin conversion for the documented Garmin Light plan schema."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from typing import Any

SPORTS = {
    "running": {"id": 1, "key": "running", "display_order": 1},
    "cycling": {"id": 2, "key": "cycling", "display_order": 2},
    "swimming": {"id": 4, "key": "swimming", "display_order": 3},
}

STEP_TYPES = {
    "warmup": {"id": 1, "key": "warmup", "display_order": 1},
    "cooldown": {"id": 2, "key": "cooldown", "display_order": 2},
    "interval": {"id": 3, "key": "interval", "display_order": 3},
    "recovery": {"id": 4, "key": "recovery", "display_order": 4},
    "rest": {"id": 5, "key": "rest", "display_order": 5},
    "repeat": {"id": 6, "key": "repeat", "display_order": 6},
    "other": {"id": 7, "key": "other", "display_order": 7},
    "main": {"id": 8, "key": "main", "display_order": 8},
}

END_CONDITIONS = {
    "lap_button": {"id": 1, "key": "lap.button", "display_order": 1, "displayable": True},
    "time": {"id": 2, "key": "time", "display_order": 2, "displayable": True},
    "distance": {"id": 3, "key": "distance", "display_order": 3, "displayable": True},
}

TARGET_TYPES = {
    "no_target": {"id": 1, "key": "no.target", "display_order": 1},
    "power_zone": {"id": 2, "key": "power.zone", "display_order": 2},
    "cadence": {"id": 3, "key": "cadence", "display_order": 3},
    "heart_rate_zone": {"id": 4, "key": "heart.rate.zone", "display_order": 4},
    "pace_zone": {"id": 6, "key": "pace.zone", "display_order": 6},
}

TIME_UNITS = {"seconds": 1.0, "minutes": 60.0, "hours": 3600.0}
DISTANCE_UNITS = {"meters": 1.0, "kilometers": 1000.0, "miles": 1609.344}
INTENSITIES = {"easy", "moderate", "hard"}
TARGET_ALIASES = {
    "heart_rate": "heart_rate_zone",
    "hr": "heart_rate_zone",
    "power": "power_zone",
    "pace": "pace_zone",
}
UNIT_ALIASES = {
    "s": "seconds",
    "sec": "seconds",
    "secs": "seconds",
    "min": "minutes",
    "mins": "minutes",
    "m": "meters",
    "km": "kilometers",
    "mi": "miles",
    "w": "watts",
    "min/km": "minutes_per_kilometer",
    "sec/km": "seconds_per_kilometer",
    "min/mi": "minutes_per_mile",
    "min/mile": "minutes_per_mile",
    "sec/mi": "seconds_per_mile",
    "sec/mile": "seconds_per_mile",
}
PACE_UNITS = {
    "minutes_per_kilometer",
    "seconds_per_kilometer",
    "minutes_per_mile",
    "seconds_per_mile",
}


def _key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _unit(value: Any, default: str) -> str:
    normalized = _key(value).replace("_per_", "/")
    return UNIT_ALIASES.get(normalized, UNIT_ALIASES.get(_key(value), _key(value) or default))


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _pace_seconds(value: Any, unit: str) -> float | None:
    if isinstance(value, str):
        cleaned = value.strip().lower()
        for suffix in ("/km", "/mi", "/mile"):
            cleaned = cleaned.removesuffix(suffix).strip()
        if ":" in cleaned:
            parts = cleaned.split(":")
            try:
                if len(parts) == 2:
                    seconds = float(parts[0]) * 60 + float(parts[1])
                elif len(parts) == 3:
                    seconds = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                else:
                    return None
            except ValueError:
                return None
        else:
            number = _number(cleaned)
            if number is None:
                return None
            seconds = number
    else:
        number = _number(value)
        if number is None:
            return None
        seconds = number

    if unit.startswith("minutes_") and not (isinstance(value, str) and ":" in value):
        seconds *= 60
    return seconds if seconds > 0 else None


def _target_number(value: Any, target_type: str, unit: str) -> float | None:
    if target_type != "pace_zone":
        return _number(value)
    seconds = _pace_seconds(value, unit)
    if seconds is None:
        return None
    distance = 1609.344 if unit.endswith("_mile") else 1000.0
    return distance / seconds


def example_plan(start: date | None = None) -> dict[str, Any]:
    day = start or date.today()
    return {
        "plan_name": "Example Garmin Light plan",
        "workouts": [
            {
                "date": day.isoformat(),
                "sport": "running",
                "name": "Easy aerobic run",
                "description": "Keep the effort conversational.",
                "intensity": "easy",
                "steps": [
                    {
                        "type": "warmup",
                        "end_condition": {"type": "time", "value": 10, "unit": "minutes"},
                        "instruction": "Very easy",
                    },
                    {
                        "type": "main",
                        "end_condition": {"type": "time", "value": 30, "unit": "minutes"},
                        "target": {
                            "type": "heart_rate",
                            "min": 120,
                            "max": 140,
                            "unit": "bpm",
                        },
                        "instruction": "Easy aerobic effort",
                    },
                    {
                        "type": "cooldown",
                        "duration_minutes": 5,
                        "instruction": "Easy",
                    },
                ],
            }
        ],
    }


def parse_uploaded_plan(contents: bytes) -> Any:
    try:
        return json.loads(contents.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid UTF-8 JSON plan: {exc}") from exc


def _normalize_end_condition(
    step: dict[str, Any], prefix: str, errors: list[str]
) -> dict[str, Any]:
    raw = step.get("end_condition")
    if raw is None and "duration_minutes" in step:
        raw = {"type": "time", "value": step.get("duration_minutes"), "unit": "minutes"}
    if not isinstance(raw, dict):
        errors.append(f"{prefix} end_condition must be an object.")
        return {"type": "time", "value": 0.0, "unit": "seconds"}

    condition_type = _key(raw.get("type"))
    if condition_type in {"lap", "open"}:
        condition_type = "lap_button"
    if condition_type not in END_CONDITIONS:
        errors.append(f"{prefix} end condition must be lap_button, time, or distance.")
        condition_type = "time"

    if condition_type == "lap_button":
        return {"type": "lap_button", "value": 0.0, "unit": "seconds"}

    default_unit = "seconds" if condition_type == "time" else "meters"
    unit = _unit(raw.get("unit"), default_unit)
    allowed_units = TIME_UNITS if condition_type == "time" else DISTANCE_UNITS
    if unit not in allowed_units:
        errors.append(f"{prefix} has an invalid {condition_type} unit.")
    value = _number(raw.get("value"))
    if value is None or value <= 0:
        errors.append(f"{prefix} end condition value must be greater than 0.")
        value = 0.0
    return {"type": condition_type, "value": round(value, 4), "unit": unit}


def _normalize_target(step: dict[str, Any], prefix: str, errors: list[str]) -> dict[str, Any]:
    raw = step.get("target")
    if raw is None:
        return {"type": "no_target"}
    if not isinstance(raw, dict):
        errors.append(f"{prefix} target must be an object.")
        return {"type": "no_target"}

    target_type = TARGET_ALIASES.get(_key(raw.get("type")), _key(raw.get("type")))
    if target_type not in TARGET_TYPES:
        errors.append(
            f"{prefix} target type must be no_target, heart_rate, power, cadence, or pace."
        )
        return {"type": "no_target"}
    if target_type == "no_target":
        return {"type": "no_target"}

    low = raw.get("low", raw.get("min"))
    high = raw.get("high", raw.get("max"))
    zone = _number(raw.get("zone"))
    if target_type == "pace_zone":
        inline = " ".join(str(value).lower() for value in (low, high) if value is not None)
        default_unit = "minutes_per_mile" if "/mi" in inline or "/mile" in inline else (
            "minutes_per_kilometer"
        )
        unit = _unit(raw.get("unit"), default_unit)
        if unit not in PACE_UNITS:
            errors.append(f"{prefix} pace unit must be min/km, sec/km, min/mile, or sec/mile.")
    else:
        unit = _unit(raw.get("unit"), "native")

    result: dict[str, Any] = {"type": target_type, "unit": unit}
    if zone is not None:
        if not zone.is_integer() or not 1 <= zone <= 10:
            errors.append(f"{prefix} target zone must be an integer from 1 to 10.")
        else:
            result["zone"] = int(zone)
        return result

    if low is None or high is None:
        errors.append(f"{prefix} target must provide both min and max, or a zone.")
        return result
    low_number = _target_number(low, target_type, unit)
    high_number = _target_number(high, target_type, unit)
    if low_number is None or high_number is None:
        errors.append(f"{prefix} target min or max is invalid.")
    else:
        result.update(low=low, high=high)
    return result


def _normalize_steps(
    raw_steps: Any,
    workout_prefix: str,
    errors: list[str],
    counter: list[int],
    *,
    depth: int = 0,
) -> tuple[list[dict[str, Any]], float, float]:
    if not isinstance(raw_steps, list) or not raw_steps:
        errors.append(f"{workout_prefix} must contain at least one step.")
        return [], 0.0, 0.0
    if depth > 2:
        errors.append(f"{workout_prefix} repeat groups can be nested at most 2 levels deep.")
        return [], 0.0, 0.0

    normalized: list[dict[str, Any]] = []
    seconds = 0.0
    meters = 0.0
    for raw in raw_steps:
        counter[0] += 1
        prefix = f"{workout_prefix}, step {counter[0]}"
        if counter[0] > 40:
            if counter[0] == 41:
                errors.append(f"{workout_prefix} can contain at most 40 steps.")
            continue
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        step_type = _key(raw.get("type"))
        if step_type not in STEP_TYPES:
            errors.append(f"{prefix} has an unsupported step type.")
            continue

        if step_type == "repeat":
            iterations = _number(raw.get("iterations"))
            if iterations is None or not iterations.is_integer() or not 2 <= iterations <= 99:
                errors.append(f"{prefix} iterations must be an integer from 2 to 99.")
                iteration_count = 2
            else:
                iteration_count = int(iterations)
            children, child_seconds, child_meters = _normalize_steps(
                raw.get("steps"), prefix, errors, counter, depth=depth + 1
            )
            normalized.append(
                {"type": "repeat", "iterations": iteration_count, "steps": children}
            )
            seconds += child_seconds * iteration_count
            meters += child_meters * iteration_count
            continue

        end_condition = _normalize_end_condition(raw, prefix, errors)
        target = _normalize_target(raw, prefix, errors)
        if end_condition["type"] == "time":
            seconds += float(end_condition["value"]) * TIME_UNITS.get(end_condition["unit"], 0)
        if end_condition["type"] == "distance":
            meters += float(end_condition["value"]) * DISTANCE_UNITS.get(
                end_condition["unit"], 0
            )
        normalized.append(
            {
                "type": step_type,
                "end_condition": end_condition,
                "target": target,
                "instruction": str(raw.get("instruction", "")).strip()[:200],
            }
        )
    return normalized, seconds, meters


def validate_plan(
    payload: Any, *, today: date | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    current_day = today or date.today()
    if not isinstance(payload, dict):
        return [], ["The plan must be a JSON object."]
    raw_workouts = payload.get("workouts")
    if not isinstance(raw_workouts, list) or not raw_workouts:
        return [], ["The plan must contain a non-empty workouts list."]
    if len(raw_workouts) > 20:
        errors.append("A single upload can contain at most 20 workouts.")

    workouts: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_workouts[:20], start=1):
        prefix = f"Workout {index}"
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        try:
            scheduled_date = date.fromisoformat(str(raw.get("date", "")))
        except ValueError:
            errors.append(f"{prefix} has an invalid date; use YYYY-MM-DD.")
            continue
        if scheduled_date < current_day:
            errors.append(f"{prefix} is scheduled in the past ({scheduled_date}).")

        sport = _key(raw.get("sport"))
        if sport not in SPORTS:
            errors.append(f"{prefix} sport must be running, cycling, or swimming.")
        name = str(raw.get("name", "")).strip()
        if not name or len(name) > 80:
            errors.append(f"{prefix} name must contain 1–80 characters.")
        intensity = _key(raw.get("intensity", "easy"))
        if intensity not in INTENSITIES:
            errors.append(f"{prefix} intensity must be easy, moderate, or hard.")

        steps, seconds, meters = _normalize_steps(raw.get("steps"), prefix, errors, [0])
        maximum_minutes = {"running": 240, "cycling": 480, "swimming": 180}.get(sport, 480)
        if seconds / 60 > maximum_minutes:
            errors.append(f"{prefix} exceeds the {maximum_minutes}-minute safety limit.")
        workout = {
            "date": scheduled_date.isoformat(),
            "sport": sport,
            "name": name,
            "description": str(raw.get("description", "")).strip()[:500],
            "intensity": intensity,
            "steps": steps,
            "duration_minutes": round(seconds / 60, 2),
            "estimated_distance_meters": round(meters, 2),
            "status": "draft",
            "garmin_workout_id": None,
            "garmin_schedule_id": None,
            "last_error": None,
        }
        canonical = json.dumps(workout, sort_keys=True, separators=(",", ":"))
        workout["local_id"] = hashlib.sha256(canonical.encode()).hexdigest()[:20]
        workouts.append(workout)

    hard_dates = sorted(
        date.fromisoformat(workout["date"])
        for workout in workouts
        if workout["intensity"] == "hard"
    )
    for previous, following in zip(hard_dates, hard_dates[1:], strict=False):
        if (following - previous).days <= 1:
            errors.append(f"Hard workouts are too close together: {previous} and {following}.")
    return workouts, errors


def _end_condition_payload(end_condition: dict[str, Any]) -> tuple[dict[str, Any], float]:
    definition = END_CONDITIONS[end_condition["type"]]
    value = float(end_condition["value"])
    if end_condition["type"] == "time":
        value *= TIME_UNITS[end_condition["unit"]]
    elif end_condition["type"] == "distance":
        value *= DISTANCE_UNITS[end_condition["unit"]]
    return (
        {
            "conditionTypeId": definition["id"],
            "conditionTypeKey": definition["key"],
            "displayOrder": definition["display_order"],
            "displayable": definition["displayable"],
        },
        round(value, 4),
    )


def _target_payload(target: dict[str, Any]) -> dict[str, Any]:
    definition = TARGET_TYPES[target["type"]]
    result: dict[str, Any] = {
        "targetType": {
            "workoutTargetTypeId": definition["id"],
            "workoutTargetTypeKey": definition["key"],
            "displayOrder": definition["display_order"],
        }
    }
    if "zone" in target:
        result["zoneNumber"] = target["zone"]
    elif "low" in target:
        result["targetValueOne"] = round(
            float(_target_number(target["low"], target["type"], target["unit"])), 7
        )
        result["targetValueTwo"] = round(
            float(_target_number(target["high"], target["type"], target["unit"])), 7
        )
    return result


def to_garmin_workout(workout: dict[str, Any]) -> dict[str, Any]:
    sport = SPORTS[workout["sport"]]
    sport_type = {
        "sportTypeId": sport["id"],
        "sportTypeKey": sport["key"],
        "displayOrder": sport["display_order"],
    }
    order = [0]

    def convert_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for step in steps:
            order[0] += 1
            definition = STEP_TYPES[step["type"]]
            step_type = {
                "stepTypeId": definition["id"],
                "stepTypeKey": definition["key"],
                "displayOrder": definition["display_order"],
            }
            if step["type"] == "repeat":
                converted.append(
                    {
                        "type": "RepeatGroupDTO",
                        "stepOrder": order[0],
                        "stepType": step_type,
                        "numberOfIterations": step["iterations"],
                        "workoutSteps": convert_steps(step["steps"]),
                        "endCondition": {
                            "conditionTypeId": 7,
                            "conditionTypeKey": "iterations",
                            "displayOrder": 7,
                            "displayable": False,
                        },
                        "endConditionValue": float(step["iterations"]),
                        "smartRepeat": False,
                        "skipLastRestStep": False,
                    }
                )
                continue
            end_condition, value = _end_condition_payload(step["end_condition"])
            payload = {
                "type": "ExecutableStepDTO",
                "stepOrder": order[0],
                "stepType": step_type,
                "endCondition": end_condition,
                "endConditionValue": value,
                "description": step.get("instruction", ""),
            }
            payload.update(_target_payload(step["target"]))
            converted.append(payload)
        return converted

    segment = {
        "segmentOrder": 1,
        "sportType": sport_type,
        "workoutSteps": convert_steps(workout["steps"]),
    }
    description = workout.get("description", "")
    if workout.get("intensity"):
        description = f"Intensity: {workout['intensity']}. {description}".strip()
    result = {
        "workoutName": workout["name"],
        "description": description,
        "sportType": sport_type,
        "estimatedDurationInSecs": round(float(workout["duration_minutes"]) * 60),
        "workoutSegments": [segment],
    }
    if workout.get("estimated_distance_meters"):
        result["estimatedDistanceInMeters"] = workout["estimated_distance_meters"]
    return result

