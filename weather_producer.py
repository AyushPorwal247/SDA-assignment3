import json
import time
import uuid
from datetime import datetime

from kafka import KafkaProducer

from config import KAFKA_SERVER, PUBLISH_INTERVAL_SECONDS, TOPICS, TRACK_SEGMENTS
from simulation import simulation_timestamp, weather_for_segment

producer = KafkaProducer(
    bootstrap_servers=KAFKA_SERVER,
    value_serializer=lambda value: json.dumps(value).encode("utf-8"),
)

print("Weather producer started. Press Ctrl+C to stop.")

try:
    while True:
        now = datetime.now()
        for segment in TRACK_SEGMENTS:
            weather = weather_for_segment(segment, now)
            data = {
                **weather,
                "timestamp": simulation_timestamp(now),
                "weather_reading_id": str(uuid.uuid4()),
            }
            producer.send(TOPICS["weather"], key=segment.encode(), value=data)
            print("Weather Sent:", data)

        producer.flush()
        time.sleep(PUBLISH_INTERVAL_SECONDS)
finally:
    producer.close()
