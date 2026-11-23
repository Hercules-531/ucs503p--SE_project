"""Summarize manually observed, anonymous developer-pilot outcomes."""

import argparse
import json
import statistics
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    outcome: Literal["completed", "timed_out", "stopped"]
    elapsed_seconds: int = Field(ge=0, le=3600)
    assistance: bool


class Pilot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    timeout_seconds: int = Field(gt=0, le=3600)
    observations: list[Observation] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_durations(self):
        for item in self.observations:
            if item.elapsed_seconds > self.timeout_seconds:
                raise ValueError("An observation exceeds the pilot timeout")
            if item.outcome == "timed_out" and item.elapsed_seconds != self.timeout_seconds:
                raise ValueError("A timeout must equal the configured timeout")
        return self


def summarize(pilot: Pilot) -> dict:
    successful = [entry for entry in pilot.observations if entry.outcome == "completed"]
    independent = [entry for entry in successful if not entry.assistance]
    return {
        "participants": len(pilot.observations),
        "completed": len(successful),
        "completed_without_assistance": len(independent),
        "timed_out": sum(entry.outcome == "timed_out" for entry in pilot.observations),
        "stopped": sum(entry.outcome == "stopped" for entry in pilot.observations),
        "assisted": sum(entry.assistance for entry in pilot.observations),
        "completion_rate": len(successful) / len(pilot.observations),
        "median_completed_seconds": (
            statistics.median(entry.elapsed_seconds for entry in successful) if successful else None
        ),
        "median_independent_seconds": (
            statistics.median(entry.elapsed_seconds for entry in independent)
            if independent
            else None
        ),
        "timeout_seconds": pilot.timeout_seconds,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "observations", type=Path, help="JSON file with anonymous observed outcomes"
    )
    args = parser.parse_args()
    try:
        pilot = Pilot.model_validate_json(args.observations.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Could not read pilot observations: {exc}\n")
    print(json.dumps(summarize(pilot), indent=2))


if __name__ == "__main__":
    main()
