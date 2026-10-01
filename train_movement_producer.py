import json
import math
import threading
import time

from kafka import KafkaConsumer, KafkaProducer

from config import (
    KAFKA_SERVER,
    PUBLISH_INTERVAL_SECONDS,
    TOPICS,
    TRAINS,
)
from track_geometry import build_track_points, point_at_distance
from simulation import simulation_timestamp


class TrainState:
    def __init__(self, settings, route_length_m):
        self.train_id = settings["train_id"]
        self.train_number = settings["train_number"]
        self.direction = settings["direction"]
        self.base_speed_kmh = settings["base_speed_kmh"]
        self.speed_kmh = settings["base_speed_kmh"]
        self.distance_m = settings["initial_distance_m"] % route_length_m
        self.route_length_m = route_length_m
        self.speed_cap = None
        self.last_update = time.monotonic()
        self.last_speed = self.speed_kmh

    def apply_risk(self, risk_level: str, recommended_speed_kmh: float | None):
        """Apply the model's train-specific simulated speed recommendation."""
        if risk_level == "LOW" or recommended_speed_kmh is None:
            self.speed_cap = None
            return

        self.speed_cap = float(recommended_speed_kmh)

    def step(self, now_monotonic: float):
        elapsed = max(0.0, now_monotonic - self.last_update)
        self.last_update = now_monotonic

        target = self.base_speed_kmh if self.speed_cap is None else self.speed_cap
        noise = 1.2 * math.sin(now_monotonic / 7.0 + hash(self.train_id) % 17)
        target = max(5.0, target + noise)

        # Smooth acceleration/deceleration so speed behaves as a time series.
        delta = max(-5.0, min(5.0, target - self.speed_kmh))
        self.last_speed = self.speed_kmh
        self.speed_kmh += delta

        distance_change = self.speed_kmh * 1000.0 * elapsed / 3600.0
        if self.direction == "FORWARD":
            self.distance_m = (self.distance_m + distance_change) % self.route_length_m
        else:
            self.distance_m = (self.distance_m - distance_change) % self.route_length_m


def risk_listener(states: dict, lock: threading.Lock):
    consumer = KafkaConsumer(
        TOPICS["buckling"],
        bootstrap_servers=KAFKA_SERVER,
        auto_offset_reset="latest",
        enable_auto_commit=True,
        # A stable group avoids creating a brand-new consumer group on every run.
        group_id="train-safety-controller",
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
    )
    print("Train safety listener started.")
    try:
        for message in consumer:
            event = message.value
            train_id = event.get("train_id")
            risk_level = event.get("risk_level")
            if not train_id or risk_level not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
                continue

            with lock:
                state = states.get(train_id)
                if state is None:
                    continue

                previous_cap = state.speed_cap
                recommended_speed = event.get("recommended_speed_kmh")
                state.apply_risk(risk_level, recommended_speed)
                new_cap = state.speed_cap

                if previous_cap != new_cap:
                    if new_cap is None:
                        print(
                            f"Safety response: {train_id} risk returned to LOW; "
                            f"speed cap released."
                        )
                    else:
                        print(
                            f"Safety response: {train_id} received {risk_level} risk on "
                            f"{event.get('track_segment_id')}; speed cap={new_cap} km/h"
                        )
    finally:
        consumer.close()


route_length_m = build_track_points(50.0)[-1].distance_from_start_m
states = {train["train_id"]: TrainState(train, route_length_m) for train in TRAINS}
lock = threading.Lock()

threading.Thread(target=risk_listener, args=(states, lock), daemon=True).start()

producer = KafkaProducer(
    bootstrap_servers=KAFKA_SERVER,
    value_serializer=lambda value: json.dumps(value).encode("utf-8"),
)

print("Train movement producer started. Press Ctrl+C to stop.")

try:
    while True:
        tick = time.monotonic()
        timestamp = simulation_timestamp()

        with lock:
            for state in states.values():
                state.step(tick)
                point = point_at_distance(state.distance_m, state.direction, 50.0)
                speed_change = state.speed_kmh - state.last_speed

                if state.speed_kmh < 5:
                    status = "STOPPED"
                elif speed_change < -1.0:
                    status = "SLOWING"
                elif speed_change > 1.0:
                    status = "ACCELERATING"
                else:
                    status = "RUNNING"

                data = {
                    "timestamp": timestamp,
                    "movement_id": f"{state.train_id}-{time.time_ns()}",
                    "train_id": state.train_id,
                    "train_number": state.train_number,
                    "track_segment_id": point.track_segment_id,
                    "latitude": point.latitude,
                    "longitude": point.longitude,
                    "speed_kmh": round(state.speed_kmh, 2),
                    "direction": state.direction,
                    "train_status": status,
                }
                producer.send(
                    TOPICS["train_movement"],
                    key=state.train_id.encode(),
                    value=data,
                )
                print("Train Sent:", data)

        producer.flush()
        time.sleep(PUBLISH_INTERVAL_SECONDS)
finally:
    producer.close()
