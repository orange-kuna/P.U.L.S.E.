"""Validated public API inputs. SI units unless a suffix says otherwise."""

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SimulationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    profile_id: Literal["falcon9", "electron", "research"] = "falcon9"
    site_id: Literal["cape", "vandenberg", "sriharikota", "mahia"] = "cape"
    weather_mode: Literal["standard", "live"] = "standard"
    duration_s: int = Field(default=420, ge=60, le=900)
    pitch_deg: float = Field(default=70, ge=0, le=85)
    heading_deg: float = Field(default=90, ge=0, le=360)
    throttle: float = Field(default=1, ge=0.5, le=1)
    max_q_limit_kpa: float = Field(default=50, ge=5, le=100)
    wind_limit_ms: float = Field(default=35, ge=5, le=100)
    launch_time: datetime | None = None

    @field_validator("launch_time")
    @classmethod
    def validate_time(cls, value):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("launch_time must include a timezone.")
        value = value.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        if not now - timedelta(hours=1) <= value <= now + timedelta(days=6):
            raise ValueError("Choose a forecast time between now and six days ahead.")
        return value
