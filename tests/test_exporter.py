import io
import json
import zipfile

from exporter import activity_metric_rows, full_activity_export


def test_activity_metric_rows_uses_descriptors() -> None:
    rows = activity_metric_rows(
        {
            "metricDescriptors": [
                {"metricsIndex": 0, "key": "sumElapsedDuration"},
                {"metricsIndex": 1, "key": "directHeartRate"},
            ],
            "activityDetailMetrics": [
                {"metrics": [0, 120]},
                {"metrics": [60, 130]},
            ],
        }
    )
    assert rows == [
        {"sumElapsedDuration": 0, "directHeartRate": 120},
        {"sumElapsedDuration": 60, "directHeartRate": 130},
    ]


def test_full_activity_export_contains_expected_files() -> None:
    bundle = {
        "activity_id": "42",
        "summary": {"activityId": 42},
        "details": {
            "metricDescriptors": [
                {"metricsIndex": 0, "key": "sumElapsedDuration"},
                {"metricsIndex": 1, "key": "directHeartRate"},
            ],
            "activityDetailMetrics": [
                {"metrics": [0, 120]},
                {"metrics": [60, 130]},
            ],
        },
        "warnings": [],
        "original_fit_zip": b"PK-fake-original",
    }
    payload = full_activity_export({"id": "42", "name": "Test run"}, bundle)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert {
            "analysis_prompt_and_report.md",
            "full_workout.json",
            "metrics.csv",
            "charts/heart_rate.svg",
            "original_fit.zip",
        } <= names
        exported = json.loads(archive.read("full_workout.json"))
        assert exported["normalized_summary"]["id"] == "42"
        assert archive.read("original_fit.zip") == b"PK-fake-original"

