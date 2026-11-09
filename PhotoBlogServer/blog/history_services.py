"""Persist sampled observations atomically, with explicit time and identity provenance."""
from datetime import timedelta
import hashlib
from io import BytesIO
import json

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import APIException, ValidationError

from .models import (PersonProfile, PersonTrack, TrackingSession, TrackingFrame,
                     PersonObservation, PassageEvent, Post)
from .ownership import require_blog_owner
from .services import lock_owner


class HistoryConflict(APIException):
    status_code = 409
    default_detail = "동일한 기록 번호에 다른 내용이 있습니다."


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     default=str, allow_nan=False).encode()).hexdigest()


def clean_image(upload):
    if upload is None:
        return b"", None
    if upload.size > 2 * 1024 * 1024:
        raise ValidationError({"image": "확인 사진은 2 MiB 이하로 전송하세요."})
    raw = upload.read()
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.width * image.height > 4_000_000:
                raise ValueError
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((1280, 1280))
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=85)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError({"image": "올바른 확인 사진이 필요합니다."}) from None
    return raw, buffer.getvalue()


def ingest(*, actor, packet, upload=None):
    require_blog_owner(actor)
    raw, sanitized = clean_image(upload)
    config, row = packet["session"], packet["frame"]
    digest = checksum({"packet": packet, "image_sha256": hashlib.sha256(raw).hexdigest()})
    frame_id = hashlib.sha256(f'{config["id"].hex}:{row["frame_index"]}'.encode()).hexdigest()
    saved_file = None
    try:
        with transaction.atomic():
            lock_owner(actor.pk)
            session, created = TrackingSession.objects.get_or_create(pk=config["id"], defaults={
                "source_label": config["source_label"], "source_kind": config["source_kind"],
                "recording_started_at": config["recording_started_at"],
                "configuration": json.loads(json.dumps(config, default=str)),
                "configuration_sha256": checksum(config)})
            if session.configuration_sha256 != checksum(config):
                raise HistoryConflict("실행 세션의 설정은 변경할 수 없습니다.")
            previous = TrackingFrame.objects.filter(pk=frame_id).first()
            if previous:
                if previous.payload_sha256 != digest:
                    raise HistoryConflict()
                return previous, False
            post = None
            if packet.get("post_id"):
                post = Post.objects.filter(pk=packet["post_id"], author=actor).first()
                if post is None:
                    raise ValidationError({"post_id": "연결할 사진글을 찾을 수 없습니다."})
            profiles = {}
            for ref in config["profiles"]:
                profiles[ref["id"]], _ = PersonProfile.objects.get_or_create(
                    pk=ref["id"], defaults={"display_name": ref["name"]})
            if session.source_kind == "live":
                observed_at = row["captured_at"]
            else:
                try:
                    observed_at = (session.recording_started_at + timedelta(seconds=row["video_seconds"])
                                   if session.recording_started_at else None)
                except OverflowError:
                    raise ValidationError("영상 촬영 시각을 확인하세요.") from None
            frame = TrackingFrame(id=frame_id, session=session, frame_index=row["frame_index"],
                video_seconds=row["video_seconds"], observed_at=observed_at,
                processed_at=row["processed_at_utc"], payload_sha256=digest, post=post,
                unassigned_faces=[face for face in row["faces"] if face["body_track_id"] is None],
                image_size=row.get("image_size", []))
            if sanitized:
                frame.image.save("frame.jpg", ContentFile(sanitized), save=False)
                saved_file = frame.image
            frame.save(force_insert=True)
            tracks = {}
            for body in row["tracks"]:
                track, _ = PersonTrack.objects.get_or_create(session=session, track_id=body["track_id"],
                    defaults={"first_frame": row["frame_index"], "last_frame": row["frame_index"]})
                track.first_frame = min(track.first_frame, row["frame_index"])
                track.last_frame = max(track.last_frame, row["frame_index"])
                matches = [face for face in row["faces"] if face["body_track_id"] == body["track_id"]]
                # Two faces inside one body cannot establish which face belongs to that track.
                face = matches[0] if len(matches) == 1 else None
                candidate = profiles.get(face["candidate_profile_id"]) if face else None
                score = face["similarity"] if face else None
                if candidate and (track.similarity is None or score > track.similarity):
                    track.candidate, track.similarity, track.candidate_frame = candidate, score, frame
                track.save(update_fields=["first_frame", "last_frame", "candidate", "similarity", "candidate_frame"])
                PersonObservation.objects.create(frame=frame, track=track, bbox=body["bbox"],
                    candidate=candidate, similarity=score, margin=face["margin"] if face else None,
                    face_bbox=face["bbox"] if face else None)
                tracks[body["track_id"]] = track
            for event in row["crossings"]:
                PassageEvent.objects.create(id=event["event_id"], frame=frame,
                    track=tracks[event["track_id"]], direction=event["direction"])
            return frame, True
    except Exception:
        if saved_file:
            saved_file.storage.delete(saved_file.name)
        raise


def review_track(*, actor, track_id, revision, profile_key, basis="operator"):
    require_blog_owner(actor)
    with transaction.atomic():
        lock_owner(actor.pk)
        track = PersonTrack.objects.get(pk=track_id)
        if basis not in ("operator", "dataset"):
            raise ValidationError("확인 근거를 확인해주세요.")
        if basis == "dataset" and (track.session.configuration.get("purpose") != "demo" or not profile_key or profile_key != track.candidate_id):
            raise ValidationError("데이터셋 정답 확인은 시연 영상의 해당 얼굴 후보에만 적용할 수 있습니다.")
        if track.revision != revision:
            raise HistoryConflict("다른 확인 내용이 저장되었습니다. 최신 기록을 다시 불러오세요.")
        profile = PersonProfile.objects.filter(pk=profile_key).first() if profile_key else None
        if profile_key and profile is None:
            raise ValidationError({"profile": "프로필을 찾을 수 없습니다."})
        track.confirmed, track.reviewed_at = profile, timezone.now()
        track.review_basis = basis
        track.revision += 1
        track.save(update_fields=["confirmed", "reviewed_at", "revision", "review_basis"])
        return track
