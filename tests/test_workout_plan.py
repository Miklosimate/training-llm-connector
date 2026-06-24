from datetime import date

from gpt_prompt import workout_prompt
from workout_plan import example_plan, to_garmin_workout, validate_plan


def test_example_plan_validates_and_converts() -> None:
    normalized, errors = validate_plan(
        example_plan(date(2030, 1, 1)),
        today=date(2029, 1, 1),
    )
    assert errors == []
    assert normalized[0]["duration_minutes"] == 45

    garmin = to_garmin_workout(normalized[0])
    assert garmin["sportType"]["sportTypeKey"] == "running"
    assert garmin["estimatedDurationInSecs"] == 2700
    assert (
        garmin["workoutSegments"][0]["workoutSteps"][1]["targetType"][
            "workoutTargetTypeKey"
        ]
        == "heart.rate.zone"
    )


def test_repeat_distance_and_pace_conversion() -> None:
    payload = {
        "workouts": [
            {
                "date": "2030-01-01",
                "sport": "running",
                "name": "Intervals",
                "intensity": "hard",
                "steps": [
                    {
                        "type": "repeat",
                        "iterations": 3,
                        "steps": [
                            {
                                "type": "interval",
                                "end_condition": {
                                    "type": "distance",
                                    "value": 1,
                                    "unit": "kilometers",
                                },
                                "target": {
                                    "type": "pace",
                                    "min": "4:30",
                                    "max": "4:45",
                                    "unit": "min/km",
                                },
                            },
                            {"type": "recovery", "duration_minutes": 2},
                        ],
                    }
                ],
            }
        ]
    }
    normalized, errors = validate_plan(payload, today=date(2029, 1, 1))
    assert errors == []
    assert normalized[0]["estimated_distance_meters"] == 3000
    assert normalized[0]["duration_minutes"] == 6

    garmin = to_garmin_workout(normalized[0])
    repeat = garmin["workoutSegments"][0]["workoutSteps"][0]
    interval = repeat["workoutSteps"][0]
    assert repeat["numberOfIterations"] == 3
    assert interval["endConditionValue"] == 1000
    assert interval["targetValueOne"] == 3.7037037
    assert interval["targetValueTwo"] == 3.5087719


def test_prompt_contains_schema_and_valid_example() -> None:
    prompt = workout_prompt(date(2029, 1, 1))
    assert '"workouts": []' in prompt
    assert '"date": "2029-01-02"' in prompt
    assert "downloadable file named `plan.json`" in prompt
    assert "Do not only paste the JSON into the chat response." in prompt
