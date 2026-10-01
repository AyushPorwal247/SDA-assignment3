import csv
from pathlib import Path

from buckling_model import calculate_risk
from mysql_db import initialize_database, load_track_geometry_csv, reset_event_tables
from track_geometry import build_track_points, TRACK_PROPERTIES, curvature_severity


def write_track_csv():
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    path = data_dir / "track_geometry.csv"

    points = build_track_points(spacing_m=50.0)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "track_segment_id", "point_sequence", "latitude", "longitude",
            "distance_from_start_m", "segment_distance_m",
            "neutral_temperature_c", "track_condition"
        ])
        for p in points:
            props = TRACK_PROPERTIES[p.track_segment_id]
            writer.writerow([
                p.track_segment_id, p.point_sequence, p.latitude, p.longitude,
                p.distance_from_start_m, p.segment_distance_m,
                props["neutral_temperature_c"], props["track_condition"],
            ])
    return path, len(points)


def write_speed_buckling_demo_csv():
    """Controlled scenario: same track/environment, only train speed changes."""
    path = Path("data") / "speed_buckling_demo.csv"
    path.parent.mkdir(exist_ok=True)
    segment_id = "SEG-002"
    rail_temperature_c = 57.5

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "track_segment_id", "rail_temperature_c", "neutral_temperature_c",
            "track_condition", "curvature_index", "train_speed_kmh",
            "track_susceptibility_score", "dynamic_exposure_score",
            "operational_risk_score", "risk_level", "recommended_speed_kmh"
        ])
        for speed in (75, 85, 95, 105, 120):
            risk = calculate_risk(segment_id, rail_temperature_c, speed)
            writer.writerow([
                segment_id,
                rail_temperature_c,
                TRACK_PROPERTIES[segment_id]["neutral_temperature_c"],
                TRACK_PROPERTIES[segment_id]["track_condition"],
                round(curvature_severity(segment_id), 4),
                speed,
                risk["track_susceptibility_score"],
                risk["dynamic_exposure_score"],
                risk["buckling_score"],
                risk["risk_level"],
                risk["recommended_speed_kmh"],
            ])
    return path


if __name__ == "__main__":
    print("1/3 Creating track geometry...")
    path, count = write_track_csv()
    print(f"Created {path} with {count} track points.")

    print("2/3 Creating MySQL database/tables...")
    initialize_database()
    reset_event_tables()
    loaded = load_track_geometry_csv(path)
    print(f"Loaded {loaded} track points into MySQL database 'railway_safety'.")

    print("3/3 Creating controlled speed-effect demo dataset...")
    preview = write_speed_buckling_demo_csv()
    print(f"Created {preview}.")

    print("\nSetup complete. Dynamic event tables were reset for a fresh demo.")
