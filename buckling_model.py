"""Simplified, physics-informed railway buckling operational-risk model.

This is an educational simulation, not an engineering safety calculation.

The model deliberately separates:
  1) Track buckling susceptibility: direct rail-temperature sensor reading,
     neutral/stress-free temperature, track condition and curvature.
  2) Train dynamic exposure: a smaller speed-related term for a train moving
     through a thermally vulnerable section.
  3) Operational recommendation: a smooth, train-specific speed advisory based
     on the resulting risk score. The recommendation is a project simulation
     control, not a real railway operating limit.
"""

from __future__ import annotations

from dataclasses import dataclass

from track_geometry import TRACK_PROPERTIES, curvature_severity


@dataclass(frozen=True)
class SegmentProfile:
    segment_id: str
    rnt_c: float
    condition: str
    curvature: float


CONDITION_COMPONENT = {
    "GOOD": 0.0,
    "FAIR": 5.0,
    "POOR": 10.0,
}

SEGMENT_PROFILES = {
    segment: SegmentProfile(
        segment_id=segment,
        rnt_c=properties["neutral_temperature_c"],
        condition=properties["track_condition"],
        curvature=curvature_severity(segment),
    )
    for segment, properties in TRACK_PROPERTIES.items()
}


def recommended_speed_from_risk(
    current_speed_kmh: float,
    base_speed_kmh: float,
    operational_risk_score: float,
    risk_level: str,
) -> float:
    """Return a simulated operational speed advisory for the train.

    The recommendation is always capped at the train's current speed so the
    system never advises acceleration during an elevated-risk condition.
    HIGH and CRITICAL risk explicitly produce a lower target than the current
    speed when the train is moving. These are project simulation controls, not
    real railway operating limits.
    """
    current = max(0.0, float(current_speed_kmh))
    base = max(0.0, float(base_speed_kmh))

    if risk_level == "LOW":
        return round(min(current, base), 1)

    # Smooth base-speed advisory that grows with risk, capped at a 50%
    # reduction from the train's normal/base speed.
    reduction_fraction = min(
        0.50,
        0.50 * max(0.0, operational_risk_score - 30.0) / 70.0,
    )
    base_advisory = base * (1.0 - reduction_fraction)

    # Safety-response rule for the simulation:
    # HIGH  -> at least ~10% below the current speed
    # CRITICAL -> at least ~20% below the current speed
    # MEDIUM -> use the smooth base-speed advisory, never above current speed
    if risk_level == "HIGH":
        current_speed_target = current * 0.90
    elif risk_level == "CRITICAL":
        current_speed_target = current * 0.80
    else:
        current_speed_target = current

    recommended = min(current, base_advisory, current_speed_target)

    # Preserve a positive movement target when the train is moving. If it is
    # already stopped, recommending 0 km/h is appropriate.
    if current > 0.0:
        recommended = max(0.0, recommended)

    return round(recommended, 1)


def calculate_risk(
    segment_id: str,
    rail_temperature_c: float,
    train_speed_kmh: float = 0.0,
    base_speed_kmh: float = 100.0,
) -> dict:
    """Calculate project-level track susceptibility + operational risk."""
    profile = SEGMENT_PROFILES[segment_id]

    temperature_excess = max(0.0, rail_temperature_c - profile.rnt_c)

    # Thermal loading is the largest component. A small excess above RNT starts
    # the contribution; very large excesses saturate rather than growing forever.
    thermal_component = min(
        55.0,
        max(0.0, (temperature_excess - 2.0) / 16.0) * 55.0,
    )

    condition_component = CONDITION_COMPONENT[profile.condition]
    curvature_component = profile.curvature * 8.0
    track_vulnerability_component = condition_component + curvature_component

    # Train speed is a secondary dynamic-exposure term. It is intentionally
    # modest compared with thermal/track susceptibility and rises continuously.
    speed_component = min(
        15.0,
        15.0 * (max(0.0, train_speed_kmh) / 120.0) ** 2,
    )

    track_susceptibility_score = min(
        100.0,
        thermal_component + track_vulnerability_component,
    )
    operational_risk_score = min(
        100.0,
        track_susceptibility_score + speed_component,
    )

    if operational_risk_score >= 70.0:
        level = "CRITICAL"
    elif operational_risk_score >= 50.0:
        level = "HIGH"
    elif operational_risk_score >= 30.0:
        level = "MEDIUM"
    else:
        level = "LOW"

    recommended_speed = recommended_speed_from_risk(
        train_speed_kmh,
        base_speed_kmh,
        operational_risk_score,
        level,
    )

    return {
        "buckling_score": round(operational_risk_score, 2),
        "risk_level": level,
        "rail_temperature_c": round(rail_temperature_c, 2),
        "neutral_temperature_c": profile.rnt_c,
        "temperature_excess_c": round(temperature_excess, 2),
        "track_condition": profile.condition,
        "curvature_index": round(profile.curvature, 4),
        "thermal_component": round(thermal_component, 2),
        "track_vulnerability_component": round(track_vulnerability_component, 2),
        "speed_component": round(speed_component, 2),
        "track_susceptibility_score": round(track_susceptibility_score, 2),
        "dynamic_exposure_score": round(speed_component, 2),
        "train_speed_kmh": round(train_speed_kmh, 2),
        "recommended_speed_kmh": recommended_speed,
    }
