from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from contracts import MatchEvent, OverlayCard, TrackingFrame

from .conftest import validator

PASS_EVENT: dict[str, Any] = {
    "event_id": "01M5Z89R804S5RCP6FF34G8MH6",
    "match_id": "lag-hcf-default-s42",
    "seq": 1,
    "clock_ms": 1520,
    "period": 1,
    "type": "pass",
    "team_id": "LAG",
    "player_id": "LAG-09",
    "x": 52.5,
    "y": 34.0,
    "end_x": 40.1,
    "end_y": 44.0,
    "outcome": "complete",
    "under_pressure": False,
    "ball_speed_kmh": 41.5,
    "recipient_id": "LAG-08",
}

OVERLAY: dict[str, Any] = {
    "overlay_id": "ov-1",
    "match_id": "lag-hcf-default-s42",
    "clock_ms": 600_000,
    "slot": "lower_third",
    "priority": 3,
    "ttl_ms": 8000,
    "audience_profile_hash": "a1b2c3",
    "lang": "pcm",
    "title": "Okunade don score!",
    "body": "Na 33 km/h run, e no fit catch am.",
    "stats": [
        {"label": "Top speed", "value": 33.1, "unit": "km/h"},
        {"label": "xG", "value": 0.18},
    ],
    "evidence_event_ids": ["01M5Z89R804S5RCP6FF34G8MH6"],
    "trace_id": "trace-1",
}


@pytest.mark.parametrize("name", ["event", "tracking", "overlay", "world"])
def test_schema_is_valid_draft_2020_12(name: str) -> None:
    validator(name)  # check_schema raises on an invalid schema


def test_valid_pass_event_accepted_by_schema_and_model() -> None:
    validator("event").validate(PASS_EVENT)
    assert MatchEvent.model_validate(PASS_EVENT).type == "pass"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("x", 105.5),
        ("y", -0.1),
        ("event_id", "not-a-ulid"),
        ("type", "dribble"),
        ("period", 3),
        ("surprise", True),
    ],
)
def test_invalid_event_rejected_by_schema_and_model(field: str, value: Any) -> None:
    bad = {**PASS_EVENT, field: value}
    assert not validator("event").is_valid(bad)
    with pytest.raises(ValidationError):
        MatchEvent.model_validate(bad)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e.pop("team_id"),
        lambda e: e.pop("ball_speed_kmh"),
        lambda e: e.pop("end_x"),
        lambda e: e.update(outcome="saved"),
    ],
)
def test_conditional_rules_enforced_by_json_schema(mutate: Any) -> None:
    bad = copy.deepcopy(PASS_EVENT)
    mutate(bad)
    assert not validator("event").is_valid(bad)


def test_period_end_needs_no_team_or_player() -> None:
    event = {k: PASS_EVENT[k] for k in ("event_id", "match_id", "seq", "clock_ms", "period", "x")}
    event.update(type="period_end", y=34.0, under_pressure=False)
    validator("event").validate(event)


def test_tracking_frame_accepts_positions_and_rejects_out_of_bounds() -> None:
    frame = {
        "match_id": "m",
        "clock_ms": 200,
        "period": 1,
        "players": [{"player_id": "LAG-09", "x": 52.5, "y": 34.0}],
        "ball": {"x": 52.5, "y": 34.0},
    }
    validator("tracking").validate(frame)
    TrackingFrame.model_validate(frame)
    frame["ball"] = {"x": 106.0, "y": 34.0}
    assert not validator("tracking").is_valid(frame)


def test_overlay_card_contract() -> None:
    validator("overlay").validate(OVERLAY)
    assert OverlayCard.model_validate(OVERLAY).lang == "pcm"
    for field, value in [("priority", 6), ("slot", "banner"), ("lang", "de")]:
        bad = {**OVERLAY, field: value}
        assert not validator("overlay").is_valid(bad)
        with pytest.raises(ValidationError):
            OverlayCard.model_validate(bad)
