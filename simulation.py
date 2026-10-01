"""Shared pseudo-sensor simulation for the live railway demo.

Weather and rail temperature are separate sensor streams.
The rail-temperature stream represents direct measurements from trackside rail
sensors; the buckling model consumes those measurements directly and does not
calculate rail temperature from weather.
"""

from __future__ import annotations

import math
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Dict

from config import (
    DEMO_AIR_AMPLITUDE_C,
    DEMO_AIR_BASE_C,
    DEMO_CYCLE_SECONDS,
    DEMO_MODE,
    DEMO_PEAK_HOUR,
    TRACK_SEGMENTS,
)

IST = timezone(timedelta(hours=5, minutes=30))

SEGMENT_WEATHER_OFFSETS: Dict[str, float] = {
    "SEG-001": -0.4,
    "SEG-002": 0.0,
    "SEG-003": 0.5,
    "SEG-004": 1.2,
    "SEG-005": -0.2,
}

# Small sensor-location effects. These are not derived from weather.
SEGMENT_RAIL_OFFSETS: Dict[str, float] = {
    "SEG-001": -1.5,
    "SEG-002": 0.5,
    "SEG-003": 1.5,
    "SEG-004": 3.0,
    "SEG-005": 0.0,
}


def simulation_timestamp(now: datetime | None = None) -> str:
    """Return an ISO-8601 UTC timestamp for Kafka/MySQL/Grafana."""
    if now is None:
        aware = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        aware = now.replace(tzinfo=IST).astimezone(timezone.utc)
    else:
        aware = now.astimezone(timezone.utc)
    return aware.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _minute_seed(now: datetime) -> int:
    return int(now.timestamp() // 60)


def _heat_factor(now: datetime | None = None) -> float:
    """Return a smooth 0..1 thermal cycle for the demo sensor readings."""
    now = now or datetime.now()
    if DEMO_MODE:
        phase = (time.time() % DEMO_CYCLE_SECONDS) / DEMO_CYCLE_SECONDS * 2.0 * math.pi
        # Peak around the middle of the demo cycle.
        return 0.5 + 0.5 * math.cos(phase - math.pi)

    hour = now.hour + now.minute / 60.0
    phase = ((hour - DEMO_PEAK_HOUR) / 12.0) * math.pi
    return 0.5 + 0.5 * max(0.0, math.cos(phase))


def weather_for_segment(segment_id: str, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    heat_factor = _heat_factor(now)

    if DEMO_MODE:
        air = DEMO_AIR_BASE_C + DEMO_AIR_AMPLITUDE_C * heat_factor
    else:
        air = 27.0 + 10.0 * heat_factor

    rng = random.Random(f"weather-{segment_id}-{_minute_seed(now)}")
    cloud_noise = rng.uniform(-0.10, 0.10)
    wind_noise = rng.uniform(-1.0, 1.0)

    solar = max(0.0, 950.0 * heat_factor * (1.0 - max(0.0, cloud_noise)))
    wind = max(1.0, 5.5 + 3.0 * (1.0 - heat_factor) + wind_noise)
    humidity = min(85.0, max(25.0, 72.0 - 24.0 * heat_factor + rng.uniform(-2.0, 2.0)))
    air += SEGMENT_WEATHER_OFFSETS[segment_id] + rng.uniform(-0.25, 0.25)

    if solar > 650:
        condition = "Sunny"
    elif solar > 300:
        condition = "Partly Cloudy"
    else:
        condition = "Cloudy"

    return {
        "timestamp": simulation_timestamp(now),
        "track_segment_id": segment_id,
        "air_temperature_c": round(air, 2),
        "humidity_percent": round(humidity, 2),
        "wind_speed_kmh": round(wind, 2),
        "solar_radiation_w_m2": round(solar, 2),
        "weather_condition": condition,
    }


def rail_temperature_sensor_for_segment(segment_id: str, now: datetime | None = None) -> float:
    """Simulate a direct rail-temperature sensor reading.

    This is deliberately independent of the weather stream. Weather is a
    separate contextual sensor stream; the buckling model consumes this rail
    temperature measurement directly.
    """
    now = now or datetime.now()
    heat_factor = _heat_factor(now)

    # Demo sensor regime: roughly 44-60 C before small segment effects.
    # The curve is smooth in time so the sensor behaves like a real time series.
    base = 44.0 + 14.0 * heat_factor

    # Small thermal inertia and sensor noise make the reading less perfectly
    # deterministic while keeping it stable from one 5-second tick to the next.
    phase = (time.time() % DEMO_CYCLE_SECONDS) / DEMO_CYCLE_SECONDS * 2.0 * math.pi
    inertia = 0.8 * math.sin(phase / 2.0 + hash(segment_id) % 13)
    rng = random.Random(f"rail-sensor-{segment_id}-{int(time.time() // 15)}")
    noise = rng.uniform(-0.25, 0.25)

    reading = base + SEGMENT_RAIL_OFFSETS[segment_id] + inertia + noise
    return round(reading, 2)


def weather_and_rail(now: datetime | None = None) -> dict:
    """Return the two independent pseudo-sensor streams for inspection/tests."""
    now = now or datetime.now()
    result = {}
    for segment in TRACK_SEGMENTS:
        result[segment] = {
            "weather": weather_for_segment(segment, now),
            "rail_temperature_c": rail_temperature_sensor_for_segment(segment, now),
        }
    return result
