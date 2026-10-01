"""MySQL storage layer for the railway safety Kafka project."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

import mysql.connector
from mysql.connector import Error

from config import MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER


def server_connection():
    return mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
    )


def db_connection():
    return mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
    )


def initialize_database() -> None:
    conn = server_connection()
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}`")
    cur.close()
    conn.close()

    conn = db_connection()
    cur = conn.cursor()
    statements = [
        """CREATE TABLE IF NOT EXISTS track_geometry (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            track_segment_id VARCHAR(20) NOT NULL,
            point_sequence INT NOT NULL,
            latitude DECIMAL(10,6) NOT NULL,
            longitude DECIMAL(10,6) NOT NULL,
            distance_from_start_m DECIMAL(12,2) NOT NULL,
            segment_distance_m DECIMAL(12,2) NOT NULL,
            neutral_temperature_c DECIMAL(6,2) NOT NULL,
            track_condition VARCHAR(10) NOT NULL,
            UNIQUE KEY uq_track_point (track_segment_id, point_sequence),
            INDEX idx_track_segment (track_segment_id)
        )""",
        """CREATE TABLE IF NOT EXISTS weather_events (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            event_timestamp DATETIME NOT NULL,
            weather_reading_id VARCHAR(64) NOT NULL,
            track_segment_id VARCHAR(20) NOT NULL,
            air_temperature_c DECIMAL(7,2) NOT NULL,
            humidity_percent DECIMAL(7,2) NOT NULL,
            wind_speed_kmh DECIMAL(7,2) NOT NULL,
            solar_radiation_w_m2 DECIMAL(9,2) NOT NULL,
            weather_condition VARCHAR(32) NOT NULL,
            INDEX idx_weather_segment_time (track_segment_id, event_timestamp)
        )""",
        """CREATE TABLE IF NOT EXISTS rail_temperature_events (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            event_timestamp DATETIME NOT NULL,
            sensor_id VARCHAR(32) NOT NULL,
            sensor_reading_id VARCHAR(64) NOT NULL,
            track_segment_id VARCHAR(20) NOT NULL,
            rail_temperature_c DECIMAL(7,2) NOT NULL,
            sensor_status VARCHAR(16) NOT NULL,
            INDEX idx_rail_segment_time (track_segment_id, event_timestamp)
        )""",
        """CREATE TABLE IF NOT EXISTS train_movement_events (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            event_timestamp DATETIME NOT NULL,
            movement_id VARCHAR(64) NOT NULL,
            train_id VARCHAR(32) NOT NULL,
            train_number VARCHAR(16) NOT NULL,
            track_segment_id VARCHAR(20) NOT NULL,
            latitude DECIMAL(10,6) NOT NULL,
            longitude DECIMAL(10,6) NOT NULL,
            speed_kmh DECIMAL(7,2) NOT NULL,
            direction VARCHAR(16) NOT NULL,
            train_status VARCHAR(20) NOT NULL,
            INDEX idx_train_time (train_id, event_timestamp),
            INDEX idx_train_segment_time (track_segment_id, event_timestamp)
        )""",
        """CREATE TABLE IF NOT EXISTS buckling_risk_events (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            event_timestamp DATETIME NOT NULL,
            track_segment_id VARCHAR(20) NOT NULL,
            buckling_score DECIMAL(7,2) NOT NULL,
            risk_level VARCHAR(12) NOT NULL,
            rail_temperature_c DECIMAL(7,2) NOT NULL,
            neutral_temperature_c DECIMAL(7,2) NOT NULL,
            temperature_excess_c DECIMAL(7,2) NOT NULL,
            curvature_index DECIMAL(8,4) NOT NULL,
            thermal_component DECIMAL(7,2) NOT NULL DEFAULT 0,
            track_vulnerability_component DECIMAL(7,2) NOT NULL DEFAULT 0,
            speed_component DECIMAL(7,2) NOT NULL DEFAULT 0,
            track_susceptibility_score DECIMAL(7,2) NOT NULL DEFAULT 0,
            dynamic_exposure_score DECIMAL(7,2) NOT NULL DEFAULT 0,
            track_condition VARCHAR(10) NOT NULL,
            air_temperature_c DECIMAL(7,2) NOT NULL,
            humidity_percent DECIMAL(7,2) NOT NULL,
            wind_speed_kmh DECIMAL(7,2) NOT NULL,
            solar_radiation_w_m2 DECIMAL(9,2) NOT NULL,
            train_id VARCHAR(32) NULL,
            train_number VARCHAR(16) NULL,
            train_speed_kmh DECIMAL(7,2) NOT NULL,
            driver_alert TINYINT(1) NOT NULL,
            recommended_speed_kmh DECIMAL(7,2) NULL,
            speed_reduction_active TINYINT(1) NOT NULL DEFAULT 0,
            INDEX idx_risk_segment_time (track_segment_id, event_timestamp),
            INDEX idx_risk_time (event_timestamp),
            INDEX idx_risk_level (risk_level)
        )""",
    ]
    for statement in statements:
        cur.execute(statement)

    # Backward-compatible schema updates for an already-created project.
    cur.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='buckling_risk_events'",
        (MYSQL_DATABASE,),
    )
    existing_columns = {row[0] for row in cur.fetchall()}

    if "speed_reduction_active" not in existing_columns:
        cur.execute(
            "ALTER TABLE buckling_risk_events "
            "ADD COLUMN speed_reduction_active TINYINT(1) NOT NULL DEFAULT 0"
        )

    for column_name, ddl in {
        "thermal_component": "ADD COLUMN thermal_component DECIMAL(7,2) NOT NULL DEFAULT 0",
        "track_vulnerability_component": "ADD COLUMN track_vulnerability_component DECIMAL(7,2) NOT NULL DEFAULT 0",
        "speed_component": "ADD COLUMN speed_component DECIMAL(7,2) NOT NULL DEFAULT 0",
        "track_susceptibility_score": "ADD COLUMN track_susceptibility_score DECIMAL(7,2) NOT NULL DEFAULT 0",
        "dynamic_exposure_score": "ADD COLUMN dynamic_exposure_score DECIMAL(7,2) NOT NULL DEFAULT 0",
    }.items():
        if column_name not in existing_columns:
            cur.execute(f"ALTER TABLE buckling_risk_events {ddl}")

    # The old recommended-speed field is retained only so older dashboards do
    # not fail. It is now nullable and is not produced by the new risk model.
    cur.execute(
        "ALTER TABLE buckling_risk_events "
        "MODIFY COLUMN recommended_speed_kmh DECIMAL(7,2) NULL"
    )

    conn.commit()
    cur.close()
    conn.close()


def reset_event_tables() -> None:
    """Clear only dynamic event tables for a fresh live demo.

    Track geometry is intentionally preserved. This prevents older timestamp
    data from being mixed with the UTC timestamp format used by this version.
    """
    conn = db_connection()
    cur = conn.cursor()
    for table in (
        "buckling_risk_events",
        "train_movement_events",
        "rail_temperature_events",
        "weather_events",
    ):
        cur.execute(f"DELETE FROM `{table}`")
    conn.commit()
    cur.close()
    conn.close()


def load_track_geometry_csv(csv_path: Path) -> int:
    initialize_database()
    conn = db_connection()
    cur = conn.cursor()
    inserted = 0
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            cur.execute(
                """INSERT INTO track_geometry
                (track_segment_id, point_sequence, latitude, longitude, distance_from_start_m,
                 segment_distance_m, neutral_temperature_c, track_condition)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                  latitude=VALUES(latitude), longitude=VALUES(longitude),
                  distance_from_start_m=VALUES(distance_from_start_m),
                  segment_distance_m=VALUES(segment_distance_m),
                  neutral_temperature_c=VALUES(neutral_temperature_c),
                  track_condition=VALUES(track_condition)""",
                (row["track_segment_id"], int(row["point_sequence"]), float(row["latitude"]),
                 float(row["longitude"]), float(row["distance_from_start_m"]),
                 float(row["segment_distance_m"]), float(row["neutral_temperature_c"]),
                 row["track_condition"]),
            )
            inserted += 1
    conn.commit()
    cur.close()
    conn.close()
    return inserted


def _dt(timestamp: str):
    # MySQL DATETIME does not need the ISO T separator.
    return timestamp.replace("T", " ")[:19]


def insert_weather(data: dict) -> None:
    conn = db_connection(); cur = conn.cursor()
    cur.execute("""INSERT INTO weather_events
        (event_timestamp, weather_reading_id, track_segment_id, air_temperature_c, humidity_percent, wind_speed_kmh, solar_radiation_w_m2, weather_condition)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (_dt(data["timestamp"]), data["weather_reading_id"], data["track_segment_id"],
         data["air_temperature_c"], data["humidity_percent"], data["wind_speed_kmh"],
         data["solar_radiation_w_m2"], data["weather_condition"]))
    conn.commit(); cur.close(); conn.close()


def insert_rail_temperature(data: dict) -> None:
    conn = db_connection(); cur = conn.cursor()
    cur.execute("""INSERT INTO rail_temperature_events
        (event_timestamp, sensor_id, sensor_reading_id, track_segment_id, rail_temperature_c, sensor_status)
        VALUES (%s,%s,%s,%s,%s,%s)""",
        (_dt(data["timestamp"]), data["sensor_id"], data["sensor_reading_id"], data["track_segment_id"],
         data["rail_temperature_c"], data["sensor_status"]))
    conn.commit(); cur.close(); conn.close()


def insert_train_movement(data: dict) -> None:
    conn = db_connection(); cur = conn.cursor()
    cur.execute("""INSERT INTO train_movement_events
        (event_timestamp, movement_id, train_id, train_number, track_segment_id, latitude, longitude, speed_kmh, direction, train_status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (_dt(data["timestamp"]), data["movement_id"], data["train_id"], data["train_number"],
         data["track_segment_id"], data["latitude"], data["longitude"], data["speed_kmh"],
         data["direction"], data["train_status"]))
    conn.commit(); cur.close(); conn.close()


def insert_buckling_event(event: dict) -> None:
    conn = db_connection(); cur = conn.cursor()
    cur.execute("""INSERT INTO buckling_risk_events
        (event_timestamp, track_segment_id, buckling_score, risk_level, rail_temperature_c, neutral_temperature_c,
         temperature_excess_c, curvature_index, thermal_component, track_vulnerability_component, speed_component,
         track_susceptibility_score, dynamic_exposure_score, track_condition, air_temperature_c, humidity_percent,
         wind_speed_kmh, solar_radiation_w_m2, train_id, train_number, train_speed_kmh, driver_alert,
         recommended_speed_kmh, speed_reduction_active)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (_dt(event["timestamp"]), event["track_segment_id"], event["buckling_score"], event["risk_level"],
         event["rail_temperature_c"], event["neutral_temperature_c"], event["temperature_excess_c"],
         event["curvature_index"], event["thermal_component"], event["track_vulnerability_component"],
         event["speed_component"], event.get("track_susceptibility_score", 0), event.get("dynamic_exposure_score", event["speed_component"]),
         event["track_condition"], event["air_temperature_c"], event["humidity_percent"], event["wind_speed_kmh"],
         event["solar_radiation_w_m2"], event.get("train_id"), event.get("train_number"), event["train_speed_kmh"],
         1 if event["driver_alert"] else 0, event.get("recommended_speed_kmh"),
         1 if event.get("speed_reduction_active") else 0))
    conn.commit(); cur.close(); conn.close()
