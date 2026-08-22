from datetime import datetime, timezone

from google.protobuf.timestamp_pb2 import Timestamp


def datetime_to_timestamp(value: datetime | None) -> Timestamp:
    timestamp = Timestamp()
    if value is not None:
        timestamp.FromDatetime(value.astimezone(timezone.utc))
    return timestamp


def timestamp_to_datetime(value: Timestamp) -> datetime:
    return value.ToDatetime(tzinfo=timezone.utc)
