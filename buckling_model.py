"""Simplified, physics-informed railway buckling operational-risk model.

This is an educational simulation, not an engineering safety calculation.

The model deliberately separates:
  1) Track buckling susceptibility: direct rail-temperature sensor reading,
     neutral/stress-free temperature, track condition and curvature.
  2) Train dynamic exposure: a secondary speed-related term for a train
     moving through a thermally vulnerable section.
  3) Operational recommendation: a smooth, train-specific advisory maximum
     speed based on the resulting risk score.

The advisory speed is a simulated project value, not a real railway
operating speed limit.
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


# Track-condition contribution to vulnerability.
CONDITION_COMPONENT = {
    "GOOD": 0.0,
    "FAIR": 5.0,
    "POOR": 10.0,
}


# Build a profile for every configured track segment.
SEGMENT_PROFILES = {
    segment: SegmentProfile(
        segment_id=segment,
        rnt_c=properties["neutral_temperature_c"],
        condition=properties["track_condition"],
        curvature=curvature_severity(segment),
    )
    for segment, properties in TRACK_PROPERTIES.items()
}


def advisory_max_speed_from_risk(
    base_speed_kmh: float,
    operational_risk_score: float,
) -> float:
    """Calculate a simulated advisory maximum speed.

    The advisory maximum speed is determined by the calculated
    operational risk, not by the train's current speed.

    LOW risk:
        No restriction; the normal/base speed is used.

    Higher risk:
        The advisory maximum speed is progressively reduced.

    This is an educational simulation rule, not a real railway
    operating speed limit.
    """

    base_speed = max(0.0, float(base_speed_kmh))
    risk_score = max(
        0.0,
        min(100.0, float(operational_risk_score)),
    )

    # ---------------------------------------------------------
    # LOW RISK
    # ---------------------------------------------------------
    # No simulated speed restriction.
    if risk_score < 30.0:
        advisory_speed = base_speed

    # ---------------------------------------------------------
    # MEDIUM / HIGH / CRITICAL RISK
    # ---------------------------------------------------------
    else:
        # Progressive reduction as risk increases.
        #
        # Risk = 30  -> 0% reduction
        # Risk = 100 -> maximum 50% reduction
        reduction_fraction = min(
            0.50,
            0.50 * (risk_score - 30.0) / 70.0,
        )

        advisory_speed = base_speed * (
            1.0 - reduction_fraction
        )

    # Project-level lower floor.
    advisory_speed = max(
        40.0,
        advisory_speed,
    )

    return round(
        advisory_speed,
        1,
    )


def calculate_risk(
    segment_id: str,
    rail_temperature_c: float,
    train_speed_kmh: float = 0.0,
    base_speed_kmh: float = 100.0,
) -> dict:
    """Calculate project-level track susceptibility and operational risk."""

    if segment_id not in SEGMENT_PROFILES:
        raise ValueError(
            f"Unknown track segment: {segment_id}"
        )

    profile = SEGMENT_PROFILES[segment_id]

    # =========================================================
    # 1. THERMAL COMPONENT
    # =========================================================

    # Difference between measured rail temperature and
    # the segment's neutral/stress-free temperature.
    temperature_excess = max(
        0.0,
        rail_temperature_c - profile.rnt_c,
    )

    # Thermal loading is the largest contributor.
    #
    # Below approximately 2°C above RNT:
    #     contribution = 0
    #
    # Increasing excess:
    #     contribution rises
    #
    # Very large excess:
    #     contribution saturates at 55 points
    thermal_component = min(
        55.0,
        max(
            0.0,
            (temperature_excess - 2.0) / 16.0,
        ) * 55.0,
    )

    # =========================================================
    # 2. TRACK VULNERABILITY
    # =========================================================

    # Track condition contribution.
    condition_component = CONDITION_COMPONENT[
        profile.condition
    ]

    # Curvature contribution.
    curvature_component = (
        profile.curvature * 8.0
    )

    # Combined infrastructure vulnerability.
    track_vulnerability_component = (
        condition_component
        + curvature_component
    )

    # =========================================================
    # 3. TRAIN DYNAMIC EXPOSURE
    # =========================================================

    # Current train speed directly contributes to the
    # operational risk.
    #
    # Speed is still treated as a secondary factor compared
    # with thermal loading and track vulnerability.
    #
    # At 0 km/h  -> 0 points
    # At 60 km/h -> 5 points
    # At 90 km/h -> 11.25 points
    # At 120 km/h -> 20 points
    #
    # Values above 120 km/h saturate at 20 points.
    current_speed = max(
        0.0,
        float(train_speed_kmh),
    )

    speed_component = min(
        20.0,
        20.0
        * (
            current_speed / 120.0
        ) ** 2,
    )

    # =========================================================
    # 4. TRACK BUCKLING SUSCEPTIBILITY
    # =========================================================

    # This represents the underlying vulnerability of the
    # track before adding the moving train's dynamic exposure.
    track_susceptibility_score = min(
        100.0,
        thermal_component
        + track_vulnerability_component,
    )

    # =========================================================
    # 5. OVERALL OPERATIONAL RISK
    # =========================================================

    # Current train speed is explicitly part of the final
    # operational risk calculation.
    operational_risk_score = min(
        100.0,
        track_susceptibility_score
        + speed_component,
    )

    # =========================================================
    # 6. RISK CLASSIFICATION
    # =========================================================

    if operational_risk_score >= 70.0:
        level = "CRITICAL"

    elif operational_risk_score >= 50.0:
        level = "HIGH"

    elif operational_risk_score >= 30.0:
        level = "MEDIUM"

    else:
        level = "LOW"

    # =========================================================
    # 7. ADVISORY MAXIMUM SPEED
    # =========================================================

    # IMPORTANT:
    #
    # Advisory speed is an OUTPUT of the calculated risk.
    # It does NOT use the current train speed.
    #
    # Current speed -> affects risk
    # Risk -> determines advisory maximum speed
    advisory_max_speed = advisory_max_speed_from_risk(
        base_speed_kmh,
        operational_risk_score,
    )

    # =========================================================
    # 8. OUTPUT
    # =========================================================

    return {
        # Overall operational buckling-risk score.
        "buckling_score": round(
            operational_risk_score,
            2,
        ),

        # LOW / MEDIUM / HIGH / CRITICAL
        "risk_level": level,

        # Direct rail-temperature sensor value.
        "rail_temperature_c": round(
            rail_temperature_c,
            2,
        ),

        # Segment neutral/stress-free temperature.
        "neutral_temperature_c": round(
            profile.rnt_c,
            2,
        ),

        # Rail temperature above RNT.
        "temperature_excess_c": round(
            temperature_excess,
            2,
        ),

        # Track condition.
        "track_condition": profile.condition,

        # Segment curvature index.
        "curvature_index": round(
            profile.curvature,
            4,
        ),

        # Individual risk contributors.
        "thermal_component": round(
            thermal_component,
            2,
        ),

        "track_vulnerability_component": round(
            track_vulnerability_component,
            2,
        ),

        "speed_component": round(
            speed_component,
            2,
        ),

        # Risk attributable to the track itself,
        # before train dynamic exposure.
        "track_susceptibility_score": round(
            track_susceptibility_score,
            2,
        ),

        # Explicitly expose dynamic train exposure.
        "dynamic_exposure_score": round(
            speed_component,
            2,
        ),

        # Current train speed used in the risk calculation.
        "train_speed_kmh": round(
            current_speed,
            2,
        ),

        # Keep the existing database/Grafana field name so
        # the current setup does not require a schema change.
        #
        # Conceptually this is:
        # "Advisory Maximum Speed"
        "recommended_speed_kmh": advisory_max_speed,
    }
