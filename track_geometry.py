"""Track geometry and track-master definitions for the railway simulation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple


# Local East/North coordinates in metres. The segments are intentionally
# connected and have different shapes so that curvature is visible.
SEGMENT_CONTROL_POINTS = {
    "SEG-001": [(0, 0), (1000, 0)],
    "SEG-002": [(1000, 0), (1250, 0), (1500, 50), (1750, 150), (2000, 300)],
    "SEG-003": [(2000, 300), (2150, 450), (2250, 650), (2200, 850), (2050, 1000)],
    "SEG-004": [(2050, 1000), (2150, 1080), (2350, 1100), (2550, 1000), (2700, 850)],
    "SEG-005": [(2700, 850), (3050, 780), (3400, 780)],
}

TRACK_PROPERTIES = {
    "SEG-001": {"neutral_temperature_c": 46.0, "track_condition": "GOOD"},
    "SEG-002": {"neutral_temperature_c": 45.5, "track_condition": "FAIR"},
    "SEG-003": {"neutral_temperature_c": 44.5, "track_condition": "FAIR"},
    "SEG-004": {"neutral_temperature_c": 42.0, "track_condition": "POOR"},
    "SEG-005": {"neutral_temperature_c": 45.0, "track_condition": "GOOD"},
}

ORIGIN_LAT = 28.620000
ORIGIN_LON = 77.180000
METERS_PER_DEG_LAT = 111_320.0


@dataclass(frozen=True)
class TrackPoint:
    track_segment_id: str
    point_sequence: int
    latitude: float
    longitude: float
    distance_from_start_m: float
    segment_distance_m: float


def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _bearing_degrees(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    angle = math.degrees(math.atan2(b[0] - a[0], b[1] - a[1]))
    return angle % 360


def _interpolate(a: Tuple[float, float], b: Tuple[float, float], fraction: float) -> Tuple[float, float]:
    return (
        a[0] + (b[0] - a[0]) * fraction,
        a[1] + (b[1] - a[1]) * fraction,
    )


def resample_polyline(control_points: Sequence[Tuple[float, float]], spacing_m: float = 50.0) -> List[Tuple[float, float, float]]:
    """Return approximately equally spaced points as (x, y, distance)."""
    if len(control_points) < 2:
        raise ValueError("A polyline needs at least two points")

    cumulative = [0.0]
    for left, right in zip(control_points, control_points[1:]):
        cumulative.append(cumulative[-1] + _distance(left, right))

    total = cumulative[-1]
    target_distances = list(range(0, int(total), int(spacing_m)))
    if not target_distances or target_distances[-1] != int(total):
        target_distances.append(total)

    result = []
    segment_index = 0
    for target in target_distances:
        while segment_index < len(cumulative) - 2 and target > cumulative[segment_index + 1]:
            segment_index += 1

        left_dist = cumulative[segment_index]
        right_dist = cumulative[segment_index + 1]
        fraction = 0.0 if right_dist == left_dist else (target - left_dist) / (right_dist - left_dist)
        point = _interpolate(control_points[segment_index], control_points[segment_index + 1], fraction)
        result.append((point[0], point[1], target))

    return result


def local_to_latlon(x_m: float, y_m: float) -> Tuple[float, float]:
    lat = ORIGIN_LAT + y_m / METERS_PER_DEG_LAT
    meters_per_deg_lon = METERS_PER_DEG_LAT * math.cos(math.radians(ORIGIN_LAT))
    lon = ORIGIN_LON + x_m / meters_per_deg_lon
    return lat, lon


def build_track_points(spacing_m: float = 50.0) -> List[TrackPoint]:
    records: List[TrackPoint] = []
    route_distance = 0.0

    for segment_id in SEGMENT_CONTROL_POINTS:
        samples = resample_polyline(SEGMENT_CONTROL_POINTS[segment_id], spacing_m)
        for idx, (x, y, segment_distance) in enumerate(samples, start=1):
            lat, lon = local_to_latlon(x, y)
            records.append(
                TrackPoint(
                    track_segment_id=segment_id,
                    point_sequence=idx,
                    latitude=round(lat, 6),
                    longitude=round(lon, 6),
                    distance_from_start_m=round(route_distance + segment_distance, 2),
                    segment_distance_m=round(segment_distance, 2),
                )
            )
        route_distance += samples[-1][2]

    return records


def segment_lengths(spacing_m: float = 50.0) -> dict:
    return {segment: resample_polyline(points, spacing_m)[-1][2] for segment, points in SEGMENT_CONTROL_POINTS.items()}


def total_route_length(spacing_m: float = 50.0) -> float:
    return sum(segment_lengths(spacing_m).values())


def point_at_distance(distance_m: float, direction: str = "FORWARD", spacing_m: float = 50.0) -> TrackPoint:
    """Interpolate an approximate coordinate at a route distance.

    For REVERSE movement, the returned location is mirrored along the same
    route so the train physically travels the geometry in the opposite direction.
    """
    points = build_track_points(spacing_m)
    total = points[-1].distance_from_start_m
    logical_distance = distance_m % total
    if direction == "REVERSE":
        logical_distance = (total - logical_distance) % total

    for left, right in zip(points, points[1:]):
        if left.distance_from_start_m <= logical_distance <= right.distance_from_start_m:
            span = right.distance_from_start_m - left.distance_from_start_m
            f = 0.0 if span == 0 else (logical_distance - left.distance_from_start_m) / span
            return TrackPoint(
                track_segment_id=left.track_segment_id,
                point_sequence=left.point_sequence,
                latitude=round(left.latitude + (right.latitude - left.latitude) * f, 6),
                longitude=round(left.longitude + (right.longitude - left.longitude) * f, 6),
                distance_from_start_m=round(logical_distance, 2),
                segment_distance_m=round(left.segment_distance_m + (right.segment_distance_m - left.segment_distance_m) * f, 2),
            )

    return points[-1]


def curvature_severity(segment_id: str) -> float:
    """Return a normalized 0..1 curve severity derived from heading changes."""
    samples = resample_polyline(SEGMENT_CONTROL_POINTS[segment_id], 50.0)
    headings = [
        _bearing_degrees(samples[i], samples[i + 1])
        for i in range(len(samples) - 1)
    ]
    if len(headings) < 2:
        return 0.0

    total_turn = 0.0
    for a, b in zip(headings, headings[1:]):
        turn = abs((b - a + 180) % 360 - 180)
        total_turn += turn

    average_turn = total_turn / (len(headings) - 1)
    return min(1.0, average_turn / 12.0)
