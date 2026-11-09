"""One-time, manifest-scoped correction of our own v1 demonstration records."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import sys
from uuid import UUID
from zipfile import ZipFile


def repair(bundle_path, backup_dir, state):
    sys.path.insert(0, state["source"])
    from deploy.production import load_environment
    load_environment(Path("/home/daejinha/.config/common01-auto/production.json"), Path(state["source"]))
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.files.base import ContentFile
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.db import transaction
    from django.db.models import Q
    from blog.history_serializers import PacketSerializer
    from blog.history_services import checksum, clean_image
    from blog.models import TrackingSession, TrackingFrame, PersonTrack, PersonProfile, PersonObservation, Post
    from blog.services import lock_owner

    backup = Path(backup_dir)
    backup.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup.chmod(0o700)
    receipt = backup / "completed.json"
    if receipt.exists():
        return json.loads(receipt.read_text())
    bundle = ZipFile(bundle_path)
    manifest = json.loads(bundle.read("manifest.json"))
    real = [e for e in manifest["entries"] if e["kind"] == "actual_model_validation"]
    simulated = [e for e in manifest["entries"] if e["kind"] == "labelled_simulation"]
    assert len(real) == 37 and len(simulated) == 16
    real_ids = {e["id"] for e in real}
    fake_ids = {e["id"] for e in simulated}
    fake_sessions = {UUID(e["packet"]["session"]["id"]) for e in simulated}
    fake_profiles = {"demo-v1-person-a", "demo-v1-person-b", "demo-v1-person-c"}
    assert len(fake_sessions) == 8
    assert TrackingFrame.objects.filter(pk__in=real_ids).count() == 37
    assert TrackingFrame.objects.filter(session_id__in=fake_sessions).count() == 16
    assert set(TrackingFrame.objects.filter(session_id__in=fake_sessions).values_list("pk", flat=True)) == fake_ids
    assert not TrackingFrame.objects.filter(session_id__in=fake_sessions, post__isnull=False).exists()
    for session in TrackingSession.objects.filter(pk__in=fake_sessions):
        assert session.configuration["model_versions"]["pipeline"] == "diagram_timeline_simulation_v1"
        assert session.source_label.startswith("[시연]")
    outside = PersonTrack.objects.exclude(session_id__in=fake_sessions)
    assert not outside.filter(Q(candidate_id__in=fake_profiles) | Q(confirmed_id__in=fake_profiles)).exists()
    assert not PersonObservation.objects.exclude(frame__session_id__in=fake_sessions).filter(candidate_id__in=fake_profiles).exists()
    assert not PersonProfile.objects.filter(pk__in=fake_profiles).exclude(display_name__startswith="[시연]").exists()
    owner = get_user_model().objects.get(username="daejinha")

    def state_hash(query):
        return checksum(list(query))
    def public_state():
        rows = list(Post.objects.order_by("pk").values())
        media = {str(p.pk): sha256(p.image.read()).hexdigest() for p in Post.objects.order_by("pk") if p.image}
        return {"posts": checksum(rows), "images": media,
                "users": state_hash(get_user_model().objects.order_by("pk").values())}

    before = public_state()
    tracks_before = state_hash(outside.order_by("pk").values())
    with sqlite3.connect(str(settings.DATABASES["default"]["NAME"])) as source:
        with sqlite3.connect(backup / "before.sqlite3") as target:
            source.backup(target)
    (backup / "before.sqlite3").chmod(0o600)
    old_images = []
    with transaction.atomic():
        lock_owner(owner.pk)
        for entry in real:
            serializer = PacketSerializer(data=entry["packet"])
            serializer.is_valid(raise_exception=True)
            packet = serializer.validated_data
            frame = TrackingFrame.objects.select_for_update().get(pk=entry["id"])
            assert frame.post_id is None and frame.observed_at is None
            assert frame.session.configuration["model_versions"]["demo_provenance"] == "actual_inference_replay_v1"
            old_digest = checksum({"packet": packet, "image_sha256": entry["old_upload_sha256"]})
            raw = bundle.read(entry["id"] + ".jpg")
            assert sha256(raw).hexdigest() == entry["clean_upload_sha256"]
            new_digest = checksum({"packet": packet, "image_sha256": sha256(raw).hexdigest()})
            assert frame.payload_sha256 == old_digest, "Record changed since v1 import; stop without touching it"
            _, sanitized = clean_image(SimpleUploadedFile("frame.jpg", raw, "image/jpeg"))
            old_images.append({"id": frame.pk, "image": frame.image.name, "payload_sha256": frame.payload_sha256})
            frame.image.save("frame.jpg", ContentFile(sanitized), save=False)
            frame.payload_sha256 = new_digest
            frame.save(update_fields=["image", "payload_sha256"])
        TrackingSession.objects.filter(pk__in=fake_sessions).delete()
        PersonProfile.objects.filter(pk__in=fake_profiles).delete()
        assert TrackingFrame.objects.filter(pk__in=real_ids).count() == 37
        assert not TrackingFrame.objects.filter(pk__in=fake_ids).exists()
        assert state_hash(PersonTrack.objects.exclude(session_id__in=fake_sessions).order_by("pk").values()) == tracks_before
        assert public_state() == before
    (backup / "old-image-paths.json").write_text(json.dumps(old_images))
    (backup / "old-image-paths.json").chmod(0o600)
    outcome = {"pass": True, "actual_frames_restored": 37, "synthetic_frames_removed": 16,
               "synthetic_sessions_removed": 8, "synthetic_profiles_removed": 3,
               "actual_track_reviews_preserved": True, "posts_accounts_and_public_media_preserved": True,
               "database_backup_created": True, "old_private_images_retained": True,
               "unknown_recording_dates_preserved": True}
    receipt.write_text(json.dumps(outcome))
    receipt.chmod(0o600)
    return outcome
