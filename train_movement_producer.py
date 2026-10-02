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

from track_geometry import (
    build_track_points,
    point_at_distance,
)

from simulation import simulation_timestamp


# =========================================================
# Train state
# =========================================================


class TrainState:

    def __init__(self, settings, route_length_m):
        self.train_id = settings["train_id"]
        self.train_number = settings["train_number"]
        self.direction = settings["direction"]

        # Normal/base operating speed of the train.
        self.base_speed_kmh = settings["base_speed_kmh"]

        # Current simulated speed.
        self.speed_kmh = settings["base_speed_kmh"]

        # Current position on the route.
        self.distance_m = (
            settings["initial_distance_m"] % route_length_m
        )

        self.route_length_m = route_length_m

        # Advisory maximum received from the
        # buckling-risk engine.
        #
        # None means there is currently no
        # active safety restriction.
        self.speed_cap = None

        self.last_update = time.monotonic()
        self.last_speed = self.speed_kmh

    # -----------------------------------------------------
    # Apply risk response
    # -----------------------------------------------------

    def apply_risk(
        self,
        risk_level: str,
        advisory_max_speed_kmh: float | None,
    ):
        """
        Apply the simulated advisory maximum speed.

        The advisory maximum is an upper limit.

        If the train is already faster than the advisory
        maximum, it will gradually slow down.

        If the train is already below the advisory maximum,
        the safety event does NOT accelerate the train.

        LOW risk releases the safety restriction.
        """

        # LOW risk or missing advisory:
        # release the active safety restriction.
        if (
            risk_level == "LOW"
            or advisory_max_speed_kmh is None
        ):
            self.speed_cap = None
            return

        advisory_max_speed = max(
            0.0,
            float(advisory_max_speed_kmh),
        )

        # Store the advisory maximum directly.
        #
        # This is the operational ceiling.
        #
        # We do NOT replace it with current speed.
        #
        # The step() function decides whether the train
        # actually needs to slow down.
        self.speed_cap = advisory_max_speed

    # -----------------------------------------------------
    # Advance simulation
    # -----------------------------------------------------

    def step(self, now_monotonic: float):
        """Advance train position and speed by one simulation step."""

        elapsed = max(
            0.0,
            now_monotonic - self.last_update,
        )

        self.last_update = now_monotonic

        # -------------------------------------------------
        # Determine target speed
        # -------------------------------------------------

        if self.speed_cap is None:

            # -------------------------------------------------
            # No active safety restriction
            # -------------------------------------------------
            #
            # Train naturally returns toward its normal/base
            # operating speed.
            #
            # A small variation is used to make the time series
            # look realistic.
            #
            # IMPORTANT:
            # The target is capped at base speed so that normal
            # simulation noise cannot push the train above its
            # base speed and create false overspeed conditions
            # when the advisory maximum equals the base speed.

            noise = 1.2 * math.sin(
                now_monotonic / 7.0
                + hash(self.train_id) % 17
            )

            target = self.base_speed_kmh + noise

            target = max(
                5.0,
                min(
                    self.base_speed_kmh,
                    target,
                ),
            )

        else:

            # -------------------------------------------------
            # Active safety restriction
            # -------------------------------------------------
            #
            # Advisory maximum is an UPPER LIMIT.
            #
            # Case 1:
            # Current speed > advisory maximum
            #     -> target becomes advisory maximum
            #     -> train slows down
            #
            # Case 2:
            # Current speed <= advisory maximum
            #     -> target remains current speed
            #     -> train does NOT accelerate toward
            #        the advisory maximum
            #
            # This ensures that the safety event can never
            # cause acceleration.

            target = min(
                self.speed_kmh,
                self.speed_cap,
            )

            target = max(
                5.0,
                target,
            )

        # -------------------------------------------------
        # Smooth acceleration / deceleration
        # -------------------------------------------------
        #
        # Normal operation:
        #     train can gradually return toward base speed.
        #
        # Safety restriction:
        #     train can gradually decelerate toward the
        #     advisory maximum.
        #
        # Maximum change per simulation step:
        #     +/- 5 km/h
        #

        delta = max(
            -5.0,
            min(
                5.0,
                target - self.speed_kmh,
            ),
        )

        # Extra safety condition:
        # Never allow positive acceleration while a safety
        # restriction is active.
        if self.speed_cap is not None:
            delta = min(
                0.0,
                delta,
            )

        self.last_speed = self.speed_kmh

        self.speed_kmh += delta

        # Final lower bound.
        self.speed_kmh = max(
            5.0,
            self.speed_kmh,
        )

        # Final upper bound under normal operation.
        #
        # This prevents normal simulation noise from causing
        # the train to exceed its configured base speed.
        if self.speed_cap is None:
            self.speed_kmh = min(
                self.base_speed_kmh,
                self.speed_kmh,
            )

        # Final safety upper bound.
        #
        # Normally the train approaches the advisory maximum
        # gradually. This prevents numerical edge cases from
        # crossing the advisory ceiling.
        else:
            self.speed_kmh = min(
                self.speed_kmh,
                self.speed_cap,
            )

        # -------------------------------------------------
        # Update distance travelled
        # -------------------------------------------------

        distance_change = (
            self.speed_kmh
            * 1000.0
            * elapsed
            / 3600.0
        )

        if self.direction == "FORWARD":

            self.distance_m = (
                self.distance_m
                + distance_change
            ) % self.route_length_m

        else:

            self.distance_m = (
                self.distance_m
                - distance_change
            ) % self.route_length_m


# =========================================================
# Risk-event listener
# =========================================================


def risk_listener(
    states: dict,
    lock: threading.Lock,
):
    """
    Consume buckling-risk events from Kafka and update
    train speed restrictions.
    """

    consumer = KafkaConsumer(
        TOPICS["buckling"],
        bootstrap_servers=KAFKA_SERVER,
        auto_offset_reset="latest",
        enable_auto_commit=True,
        group_id="train-safety-controller",
        value_deserializer=lambda value: json.loads(
            value.decode("utf-8")
        ),
    )

    print(
        "Train safety listener started."
    )

    try:

        for message in consumer:

            event = message.value

            train_id = event.get(
                "train_id"
            )

            risk_level = event.get(
                "risk_level"
            )

            if not train_id:
                continue

            if risk_level not in {
                "LOW",
                "MEDIUM",
                "HIGH",
                "CRITICAL",
            }:
                continue

            with lock:

                state = states.get(
                    train_id
                )

                if state is None:
                    continue

                previous_cap = state.speed_cap

                advisory_max_speed = event.get(
                    "recommended_speed_kmh"
                )

                state.apply_risk(
                    risk_level,
                    advisory_max_speed,
                )

                new_cap = state.speed_cap

                # -------------------------------------------------
                # Log change in safety restriction
                # -------------------------------------------------

                if previous_cap != new_cap:

                    if new_cap is None:

                        print(
                            f"Safety response: {train_id} "
                            f"risk returned to LOW; "
                            f"speed restriction released."
                        )

                    else:

                        print(
                            f"Safety response: {train_id} "
                            f"received {risk_level} risk on "
                            f"{event.get('track_segment_id')}; "
                            f"advisory max speed="
                            f"{new_cap:.1f} km/h"
                        )

    finally:

        consumer.close()


# =========================================================
# Route setup
# =========================================================


route_length_m = build_track_points(
    50.0
)[-1].distance_from_start_m


states = {
    train["train_id"]: TrainState(
        train,
        route_length_m,
    )
    for train in TRAINS
}


lock = threading.Lock()


# =========================================================
# Start Kafka risk-event consumer thread
# =========================================================


threading.Thread(
    target=risk_listener,
    args=(
        states,
        lock,
    ),
    daemon=True,
).start()


# =========================================================
# Kafka producer
# =========================================================


producer = KafkaProducer(
    bootstrap_servers=KAFKA_SERVER,
    value_serializer=lambda value: json.dumps(
        value
    ).encode("utf-8"),
)


print(
    "Train movement producer started. "
    "Press Ctrl+C to stop."
)


# =========================================================
# Main simulation loop
# =========================================================


try:

    while True:

        tick = time.monotonic()
        timestamp = simulation_timestamp()

        with lock:

            for state in states.values():

                # -------------------------------------------------
                # Update speed and position
                # -------------------------------------------------

                state.step(
                    tick
                )

                # -------------------------------------------------
                # Get current geographic position
                # -------------------------------------------------

                point = point_at_distance(
                    state.distance_m,
                    state.direction,
                    50.0,
                )

                # -------------------------------------------------
                # Calculate speed change for status
                # -------------------------------------------------

                speed_change = (
                    state.speed_kmh
                    - state.last_speed
                )

                # -------------------------------------------------
                # Determine train status
                # -------------------------------------------------

                if state.speed_kmh < 5:

                    status = "STOPPED"

                elif speed_change < -1.0:

                    status = "SLOWING"

                elif speed_change > 1.0:

                    status = "ACCELERATING"

                else:

                    status = "RUNNING"

                # -------------------------------------------------
                # Build movement event
                # -------------------------------------------------

                data = {
                    "timestamp": timestamp,

                    "movement_id": (
                        f"{state.train_id}-"
                        f"{time.time_ns()}"
                    ),

                    "train_id": state.train_id,

                    "train_number": (
                        state.train_number
                    ),

                    "track_segment_id": (
                        point.track_segment_id
                    ),

                    "latitude": point.latitude,

                    "longitude": point.longitude,

                    "speed_kmh": round(
                        state.speed_kmh,
                        2,
                    ),

                    "direction": (
                        state.direction
                    ),

                    "train_status": status,
                }

                # -------------------------------------------------
                # Send movement event to Kafka
                # -------------------------------------------------

                producer.send(
                    TOPICS["train_movement"],
                    key=state.train_id.encode(),
                    value=data,
                )

                print(
                    "Train Sent:",
                    data,
                )

        # ---------------------------------------------------------
        # Push messages to Kafka
        # ---------------------------------------------------------

        producer.flush()

        # ---------------------------------------------------------
        # Wait until next simulation cycle
        # ---------------------------------------------------------

        time.sleep(
            PUBLISH_INTERVAL_SECONDS
        )

finally:

    producer.close()
