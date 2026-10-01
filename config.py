KAFKA_SERVER = "localhost:9092"

TOPICS = {
    "track": "track-geometry",
    "weather": "weather-events",
    "rail_temperature": "rail-temperature-events",
    "train_movement": "train-movement-events",
    "buckling": "buckling-risk-events",
}

TRACK_SEGMENTS = [
    "SEG-001",
    "SEG-002",
    "SEG-003",
    "SEG-004",
    "SEG-005",
]

# Fixed train identity: train number does not change during the simulation.
TRAINS = [
    # Different starting speeds are inputs to the model, not hardcoded risk labels.
    # Risk is calculated live from current track/environment/train conditions.
    {"train_id": "TRAIN-1001", "train_number": "12919", "initial_distance_m": 400.0, "direction": "FORWARD", "base_speed_kmh": 85.0},
    {"train_id": "TRAIN-1002", "train_number": "12864", "initial_distance_m": 1450.0, "direction": "FORWARD", "base_speed_kmh": 95.0},
    {"train_id": "TRAIN-1003", "train_number": "12431", "initial_distance_m": 2400.0, "direction": "FORWARD", "base_speed_kmh": 105.0},
    {"train_id": "TRAIN-1004", "train_number": "12011", "initial_distance_m": 3300.0, "direction": "FORWARD", "base_speed_kmh": 120.0},
    {"train_id": "TRAIN-1005", "train_number": "12214", "initial_distance_m": 400.0, "direction": "REVERSE", "base_speed_kmh": 75.0},
]
# Short interval so live Kafka + Grafana behaviour is visible during a demo.
PUBLISH_INTERVAL_SECONDS = 5

# Warm daylight regime makes thermal-risk behaviour visible during classroom demos.
DEMO_MODE = True
DEMO_AIR_BASE_C = 35.0
DEMO_AIR_AMPLITUDE_C = 5.0
DEMO_PEAK_HOUR = 14.0
DEMO_CYCLE_SECONDS = 900

# The risk model now computes a train-specific simulated recommended speed from
# the train's normal speed and the calculated operational risk.

# Existing professor-provided MySQL container exposed on localhost:3306.
# Put the password you already use for that MySQL container here.
MYSQL_HOST = "localhost"
MYSQL_PORT = 3306
MYSQL_USER = "root"
MYSQL_PASSWORD = "PUT_YOUR_MYSQL_PASSWORD_HERE"
MYSQL_DATABASE = "railway_safety"
