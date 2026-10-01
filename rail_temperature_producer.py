import json
import time
import uuid
from datetime import datetime

from kafka import KafkaProducer

from config import KAFKA_SERVER, PUBLISH_INTERVAL_SECONDS, TOPICS, TRACK_SEGMENTS
from simulation import rail_temperature_sensor_for_segment, simulation_timestamp

producer = KafkaProducer(
    bootstrap_servers=KAFKA_SERVER,
    value_serializer=lambda value: json.dumps(value).encode("utf-8"),
)

print("Rail temperature sensor producer started. Press Ctrl+C to stop.")

try:
    while True:
        now = datetime.now()
        for i, segment in enumerate(TRACK_SEGMENTS, start=1):
            data = {
                "timestamp": simulation_timestamp(now),
                "sensor_id": f"RTS-{i:03d}",
                "sensor_reading_id": str(uuid.uuid4()),
                "track_segment_id": segment,
                "rail_temperature_c": rail_temperature_sensor_for_segment(segment, now),
                "sensor_status": "OK",
            }
            producer.send(TOPICS["rail_temperature"], key=segment.encode(), value=data)
            print("Rail Temp Sent:", data)

        producer.flush()
        time.sleep(PUBLISH_INTERVAL_SECONDS)
finally:
    producer.close()
