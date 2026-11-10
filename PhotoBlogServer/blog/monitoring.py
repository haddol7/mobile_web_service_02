"""Read-only presentation of stored observations; no inferred occupancy or online status."""
from datetime import datetime
from django.db.models import Count, Q, Max
from django.utils import timezone
from .models import Post, PersonProfile, PersonTrack, TrackingFrame, TrackingSession, PassageEvent
from .history_queries import ready_frames, frame_payload


def overview():
    tracks = PersonTrack.objects.all()
    pending = Q(confirmed__isnull=True, reviewed_at__isnull=True, candidate__isnull=False)
    facts = tracks.aggregate(observed_tracks=Count("pk"), pending_tracks=Count("pk", filter=pending),
                             confirmed_tracks=Count("pk", filter=Q(confirmed__isnull=False)))
    facts.update(sampled_frames=TrackingFrame.objects.count(), passages=PassageEvent.objects.count(),
                 profiles=PersonProfile.objects.count(), sessions=TrackingSession.objects.count(),
                 detection_posts=TrackingFrame.objects.filter(post__published_date__lte=timezone.now()).values("post_id").distinct().count(),
                 unknown_date_frames=TrackingFrame.objects.filter(observed_at__isnull=True).count())
    latest = TrackingFrame.objects.order_by("-processed_at", "-pk").first()
    profiles = PersonProfile.objects.annotate(
        confirmed_count=Count("confirmed_tracks", distinct=True),
        candidate_count=Count("candidate_tracks", distinct=True, filter=Q(
            candidate_tracks__confirmed__isnull=True, candidate_tracks__reviewed_at__isnull=True)),
        last_observed=Max("confirmed_tracks__observations__frame__observed_at"),
    ).order_by("display_name", "pk")[:100]
    from .monitoring_presenter import profile_payload,session_cards
    cards=[profile_payload(p) for p in profiles]
    cards.sort(key=lambda p:(p["key"]!="self-daejinha",not p["active"],-p["source_count"],not p["reference_available"],p["name"]))
    scenes=session_cards(TrackingFrame.objects.all(),8)
    frames=[{k:v for k,v in s.items() if k!="frames"} for s in scenes[:4]]
    for frame in frames:
        frame["time_label"] = timezone.localtime(datetime.fromisoformat(frame["observed_at"])).strftime("%m.%d %H:%M") if frame["observed_at"] else "촬영 날짜 미상"
    return {"facts": facts, "last_received_at": latest.processed_at.isoformat() if latest else None,
            "last_received_label": timezone.localtime(latest.processed_at).strftime("%m.%d %H:%M") if latest else None,
            "recent_frames": frames,
            "profiles":cards,"recent_sessions":scenes,
            "active_profiles":[p for p in cards if p["active"]],
            "visible_profiles":[p for p in cards if p["active"] or p["reference_available"]],
            "repeated_people_count":sum(p["source_count"]>1 for p in cards),
            "pending_people":[p for p in cards if p["candidate_tracks"]][:3],
            "repeated_people":[p for p in cards if p["source_count"]>1][:4],
            "demo_mode":bool(scenes) and all(s["purpose"]=="demo" for s in scenes)}
