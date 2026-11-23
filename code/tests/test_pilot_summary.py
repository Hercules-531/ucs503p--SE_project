import pytest
from pydantic import ValidationError

from scripts.summarize_pilot import Pilot, summarize


def test_summary_keeps_incomplete_attempts_out_of_completion_times():
    pilot = Pilot.model_validate(
        {
            "timeout_seconds": 600,
            "observations": [
                {"outcome": "completed", "elapsed_seconds": 100, "assistance": False},
                {"outcome": "completed", "elapsed_seconds": 200, "assistance": True},
                {"outcome": "timed_out", "elapsed_seconds": 600, "assistance": False},
                {"outcome": "stopped", "elapsed_seconds": 75, "assistance": True},
            ],
        }
    )
    result = summarize(pilot)
    assert result["participants"] == 4
    assert result["completion_rate"] == 0.5
    assert result["median_completed_seconds"] == 150
    assert result["median_independent_seconds"] == 100
    assert result["assisted"] == 2
    assert result["timed_out"] == result["stopped"] == 1


def test_no_completion_produces_null_medians_and_identifying_fields_are_rejected():
    pilot = Pilot.model_validate(
        {
            "timeout_seconds": 600,
            "observations": [{"outcome": "timed_out", "elapsed_seconds": 600, "assistance": False}],
        }
    )
    assert summarize(pilot)["median_completed_seconds"] is None
    with pytest.raises(ValidationError):
        Pilot.model_validate(
            {
                "timeout_seconds": 600,
                "observations": [
                    {
                        "outcome": "completed",
                        "elapsed_seconds": 10,
                        "assistance": False,
                        "email": "private@example.org",
                    }
                ],
            }
        )
    with pytest.raises(ValidationError):
        Pilot.model_validate(
            {
                "timeout_seconds": 600,
                "observations": [
                    {"outcome": "timed_out", "elapsed_seconds": 200, "assistance": False}
                ],
            }
        )
