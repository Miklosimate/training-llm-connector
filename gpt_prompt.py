"""Downloadable instructions for generating a Garmin Light workout plan."""

from __future__ import annotations

import json
from datetime import date, timedelta

from workout_plan import example_plan


def workout_prompt(today: date | None = None) -> str:
    current = today or date.today()
    example = example_plan(current + timedelta(days=1))
    return f"""# Garmin Light workout-plan prompt

Create a structured Garmin workout plan for me. Provide the result as a downloadable file named
`plan.json`. Do not only paste the JSON into the chat response. The downloadable file must contain
only one UTF-8 JSON object, without Markdown fences, comments, or explanatory text. The file will
be reviewed before it is uploaded to Garmin.

Today is `{current.isoformat()}`. Every workout date must be today or later and use `YYYY-MM-DD`.

## Required top-level structure

```json
{{
  "plan_name": "Short plan name",
  "workouts": []
}}
```

The `workouts` list may contain at most 20 workouts.

## Workout structure

Each workout requires:

- `date`: `YYYY-MM-DD`
- `sport`: `running`, `cycling`, or `swimming`
- `name`: 1–80 characters
- `intensity`: `easy`, `moderate`, or `hard`
- `steps`: one or more structured steps

Optional workout fields:

- `description`: concise execution and safety notes

## Step structure

Normal step types:

- `warmup`
- `main`
- `interval`
- `recovery`
- `rest`
- `cooldown`
- `other`

Each normal step requires an `end_condition`, or may use the `duration_minutes` shortcut.

Supported end conditions:

```json
{{"type": "time", "value": 10, "unit": "minutes"}}
{{"type": "distance", "value": 5, "unit": "kilometers"}}
{{"type": "lap_button"}}
```

Time units: `seconds`, `minutes`, `hours`.
Distance units: `meters`, `kilometers`, `miles`.

A step may include a short `instruction`.

## Targets

Targets are optional. Supported target types:

```json
{{"type": "heart_rate", "min": 120, "max": 140, "unit": "bpm"}}
{{"type": "heart_rate", "zone": 2}}
{{"type": "power", "min": 180, "max": 220, "unit": "watts"}}
{{"type": "power", "zone": 3}}
{{"type": "cadence", "min": 85, "max": 95, "unit": "rpm"}}
{{"type": "pace", "min": "5:00", "max": "5:30", "unit": "min/km"}}
```

Pace units: `min/km`, `sec/km`, `min/mile`, `sec/mile`.

## Repeats

A repeat step contains `iterations` from 2 to 99 and nested `steps`:

```json
{{
  "type": "repeat",
  "iterations": 4,
  "steps": [
    {{
      "type": "interval",
      "duration_minutes": 3,
      "target": {{"type": "pace", "min": "4:30", "max": "4:45", "unit": "min/km"}}
    }},
    {{
      "type": "recovery",
      "duration_minutes": 2,
      "instruction": "Very easy"
    }}
  ]
}}
```

Use no more than 40 total steps per workout. Do not place hard workouts on consecutive days.
Use realistic durations and targets. Do not invent medical advice.

## Complete valid example

```json
{json.dumps(example, indent=2)}
```

Create and attach a downloadable file named `plan.json`. Its contents must be only the final JSON
object. Do not put the JSON only in a Markdown code block or ordinary chat message.
"""
