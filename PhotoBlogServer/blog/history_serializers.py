"""Bounded Edge packets. Reference features and executable queries are never accepted."""
import hashlib
import math
import re
from rest_framework import serializers


class FiniteFloat(serializers.FloatField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if not math.isfinite(value):
            self.fail("invalid")
        return value


class AwareDateTime(serializers.DateTimeField):
    def to_internal_value(self, value):
        from django.utils.dateparse import parse_datetime
        from django.utils.timezone import is_aware
        try:
            parsed = parse_datetime(value) if isinstance(value, str) else value
            if not parsed or not is_aware(parsed):
                raise ValueError
        except (ValueError, TypeError):
            raise serializers.ValidationError("시간대가 포함된 ISO 시각이 필요합니다.") from None
        return super().to_internal_value(value)


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["지원하지 않는 항목이 있습니다."]})
        return super().to_internal_value(data)


class ReferenceSerializer(StrictSerializer):
    id = serializers.RegexField(r"^[A-Za-z0-9_.-]{1,64}$")
    name = serializers.CharField(max_length=80)


class SessionSerializer(StrictSerializer):
    id = serializers.UUIDField()
    source_label = serializers.CharField(max_length=80)
    source_kind = serializers.ChoiceField(choices=["video", "live"])
    recording_started_at = AwareDateTime(allow_null=True, default=None)
    model_versions = serializers.DictField(child=serializers.CharField(max_length=80))
    profiles = ReferenceSerializer(many=True, max_length=100, default=list)
    purpose = serializers.ChoiceField(choices=["recording", "demo"], required=False)
    source_reference = serializers.CharField(max_length=240, required=False)

    def validate_model_versions(self, values):
        if len(values) > 10 or any(len(key) > 80 for key in values):
            raise serializers.ValidationError("모델 정보가 너무 큽니다.")
        return values

    def validate_profiles(self, values):
        if len({p["id"] for p in values}) != len(values):
            raise serializers.ValidationError("프로필 ID가 중복되었습니다.")
        return values


class BodySerializer(StrictSerializer):
    track_id = serializers.IntegerField(min_value=1, max_value=2**53-1)
    bbox = serializers.ListField(child=FiniteFloat(min_value=-10000, max_value=100000), min_length=4, max_length=4)

    def validate_bbox(self, box):
        if box[2] <= box[0] or box[3] <= box[1]:
            raise serializers.ValidationError("영역의 크기를 확인하세요.")
        return box


class FaceSerializer(BodySerializer):
    track_id = None
    body_track_id = serializers.IntegerField(min_value=1, max_value=2**53-1, allow_null=True)
    status = serializers.ChoiceField(choices=["candidate", "unresolved"])
    candidate_profile_id = serializers.RegexField(r"^[A-Za-z0-9_.-]{1,64}$", allow_null=True)
    similarity = FiniteFloat(min_value=-1.001, max_value=1.001)
    margin = FiniteFloat(min_value=0, max_value=2.001)
    detection_score = FiniteFloat(min_value=0, max_value=1, required=False)

    def validate(self, data):
        if (data["status"] == "candidate") != (data["candidate_profile_id"] is not None):
            raise serializers.ValidationError("얼굴 후보 상태가 일치하지 않습니다.")
        return data


class CrossingSerializer(StrictSerializer):
    event_id = serializers.RegexField(r"^[a-f0-9]{64}$")
    track_id = serializers.IntegerField(min_value=1, max_value=2**53-1)
    direction = serializers.ChoiceField(choices=["in", "out"])


class FrameSerializer(StrictSerializer):
    frame_index = serializers.IntegerField(min_value=0, max_value=2**53-1)
    video_seconds = FiniteFloat(min_value=0, max_value=315576000, allow_null=True)
    processed_at_utc = AwareDateTime()
    captured_at = AwareDateTime(allow_null=True, default=None)
    tracks = BodySerializer(many=True, max_length=100)
    faces = FaceSerializer(many=True, max_length=100)
    crossings = CrossingSerializer(many=True, max_length=100)
    image_size = serializers.ListField(child=serializers.IntegerField(min_value=1, max_value=100000), min_length=2, max_length=2, required=False)


class PacketSerializer(StrictSerializer):
    schema_version = serializers.IntegerField(min_value=1, max_value=1)
    session = SessionSerializer()
    frame = FrameSerializer()
    post_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)

    def validate(self, data):
        session, frame = data["session"], data["frame"]
        if session["source_kind"] == "live" and frame["captured_at"] is None:
            raise serializers.ValidationError("실시간 기록에는 수신 시각이 필요합니다.")
        if session["source_kind"] == "video" and frame["video_seconds"] is None:
            raise serializers.ValidationError("영상 기록에는 상대 시각이 필요합니다.")
        ids = [t["track_id"] for t in frame["tracks"]]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("한 프레임의 추적 번호가 중복되었습니다.")
        profiles = {p["id"] for p in session["profiles"]}
        for face in frame["faces"]:
            if face["body_track_id"] is not None and face["body_track_id"] not in ids:
                raise serializers.ValidationError("얼굴에 대응하는 추적 기록이 없습니다.")
            if face["candidate_profile_id"] is not None and face["candidate_profile_id"] not in profiles:
                raise serializers.ValidationError("등록하지 않은 얼굴 후보입니다.")
        events = set()
        for event in frame["crossings"]:
            key = f'{session["id"].hex}:{event["track_id"]}:{frame["frame_index"]}:{event["direction"]}'
            expected = hashlib.sha256(key.encode()).hexdigest()
            if event["track_id"] not in ids or event["event_id"] != expected or expected in events:
                raise serializers.ValidationError("통과 사건의 추적 번호 또는 고유 번호가 잘못되었습니다.")
            events.add(expected)
        return data
