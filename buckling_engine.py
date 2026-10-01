import json
from kafka import KafkaConsumer, KafkaProducer

from buckling_model import calculate_risk
from config import KAFKA_SERVER, TOPICS, TRAINS
from mysql_db import (
    initialize_database,
    insert_buckling_event,
    insert_rail_temperature,
    insert_train_movement,
    insert_weather,
)


latest_weather = {}
latest_rail = {}
BASE_SPEED_BY_TRAIN = {t["train_id"]: float(t["base_speed_kmh"]) for t in TRAINS}


def safe_db_call(fn, data):
    try:
        fn(data)
    except Exception as exc:
        print(f"MySQL write failed: {exc}")


def evaluate_train(train: dict):
    """Evaluate buckling risk for this exact train using its current segment."""
    segment_id = train["track_segment_id"]
    weather = latest_weather.get(segment_id)
    rail = latest_rail.get(segment_id)

    # Risk can only be evaluated once the latest environmental inputs for the
    # train's current section are available.
    if not weather or not rail:
        return

    train_speed = float(train["speed_kmh"])
    base_speed = BASE_SPEED_BY_TRAIN.get(train["train_id"], train_speed)
    risk = calculate_risk(
        segment_id,
        float(rail["rail_temperature_c"]),
        train_speed,
        base_speed,
    )

    speed_reduction_active = risk["risk_level"] in {"MEDIUM", "HIGH", "CRITICAL"}

    event = {
        # Use the same timestamp as the triggering train movement so the live
        # event, train position and risk record refer to the same observation.
        "timestamp": train["timestamp"],
        "track_segment_id": segment_id,
        **risk,
        "air_temperature_c": float(weather["air_temperature_c"]),
        "humidity_percent": float(weather["humidity_percent"]),
        "wind_speed_kmh": float(weather["wind_speed_kmh"]),
        "solar_radiation_w_m2": float(weather["solar_radiation_w_m2"]),
        "weather_condition": weather["weather_condition"],
        "train_id": train["train_id"],
        "train_number": train["train_number"],
        "latitude": float(train["latitude"]),
        "longitude": float(train["longitude"]),
        "driver_alert": risk["risk_level"] in {"HIGH", "CRITICAL"},
        "speed_reduction_active": speed_reduction_active,
    }

    producer.send(
        TOPICS["buckling"],
        key=train["train_id"].encode(),
        value=event,
    )
    producer.flush()
    safe_db_call(insert_buckling_event, event)

    print(
        f"Risk | train={train['train_id']} | {segment_id} | "
        f"{risk['risk_level']:<8} | score={risk['buckling_score']:>5.1f} | "
        f"rail={risk['rail_temperature_c']:>5.1f}°C | "
        f"RNT={risk['neutral_temperature_c']:>4.1f}°C | "
        f"speed={train_speed:>5.1f} km/h | "
        f"recommended={risk['recommended_speed_kmh']:>5.1f} km/h | "
        f"speed_reduction={'YES' if speed_reduction_active else 'NO'}"
    )


initialize_database()

producer = KafkaProducer(
    bootstrap_servers=KAFKA_SERVER,
    value_serializer=lambda value: json.dumps(value).encode("utf-8"),
)

consumer = KafkaConsumer(
    TOPICS["weather"],
    TOPICS["rail_temperature"],
    TOPICS["train_movement"],
    bootstrap_servers=KAFKA_SERVER,
    auto_offset_reset="latest",
    enable_auto_commit=True,
    group_id="buckling-engine",
    value_deserializer=lambda value: json.loads(value.decode("utf-8")),
)

print("Buckling engine started. Kafka -> MySQL -> train-specific risk stream")

try:
    for message in consumer:
        data = message.value

        if message.topic == TOPICS["weather"]:
            latest_weather[data["track_segment_id"]] = data
            safe_db_call(insert_weather, data)

        elif message.topic == TOPICS["rail_temperature"]:
            latest_rail[data["track_segment_id"]] = data
            safe_db_call(insert_rail_temperature, data)

        elif message.topic == TOPICS["train_movement"]:
            safe_db_call(insert_train_movement, data)
            evaluate_train(data)

except KeyboardInterrupt:
    print("Buckling engine stopped.")
finally:
    consumer.close()
    producer.close()
