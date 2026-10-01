import json
from kafka import KafkaProducer

from config import KAFKA_SERVER, TOPICS
from track_geometry import build_track_points, TRACK_PROPERTIES

producer = KafkaProducer(
    bootstrap_servers=KAFKA_SERVER,
    value_serializer=lambda value: json.dumps(value).encode("utf-8"),
)

points = build_track_points(spacing_m=50.0)
for point in points:
    props = TRACK_PROPERTIES[point.track_segment_id]
    data = {
        "track_segment_id": point.track_segment_id,
        "point_sequence": point.point_sequence,
        "latitude": point.latitude,
        "longitude": point.longitude,
        "distance_from_start_m": point.distance_from_start_m,
        "segment_distance_m": point.segment_distance_m,
        "neutral_temperature_c": props["neutral_temperature_c"],
        "track_condition": props["track_condition"],
    }
    producer.send(TOPICS["track"], key=point.track_segment_id.encode(), value=data)

producer.flush()
producer.close()
print(f"Published {len(points)} track geometry points to '{TOPICS['track']}'.")
