"""Person-first, bounded presentation over real sessions and explicit identity states."""
from django.db.models import Q, Max, Count, F
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils import timezone
from .models import PersonTrack, TrackingFrame, PersonProfile
from .history_queries import ready_frames, frame_payload


def stamp(value):
    return timezone.localtime(value).strftime("%m.%d %H:%M") if value else None


def person_tracks(profile):
    return PersonTrack.objects.filter(Q(confirmed=profile) | Q(confirmed__isnull=True, reviewed_at__isnull=True, candidate=profile))


def source_key(session):
    return session.configuration.get("source_reference") or str(session.pk)


def dated_frames(frames, basis):
    field="processed_at" if basis=="processed" else "observed_at"
    return frames.annotate(calendar_day=TruncDate(field,tzinfo=timezone.get_current_timezone()))


def date_label(day):
    return day.strftime("%Y년 %-m월 %-d일") if day else "촬영 날짜 미상"


def daily_summary(frames, basis="processed"):
    return [{"date_key":r["calendar_day"].isoformat() if r["calendar_day"] else None,
             "date_label":date_label(r["calendar_day"]),"session_count":r["sessions"],"sample_count":r["samples"]}
            for r in dated_frames(frames,basis).order_by().values("calendar_day")
            .annotate(sessions=Count("session_id",distinct=True),samples=Count("pk",distinct=True))
            .order_by(F("calendar_day").desc(nulls_last=True))[:3661]]


def session_cards(frames, limit=12, *, basis="processed", offset=0):
    # A session spanning midnight appears once per local calendar day. Bound SQL groups first.
    field="processed_at" if basis=="processed" else "observed_at"
    grouped=dated_frames(frames,basis)
    unique=list(grouped.order_by().values("session_id","calendar_day").annotate(last=Max(field))
                .order_by(F("calendar_day").desc(nulls_last=True),F("last").desc(nulls_last=True),"session_id")[offset:offset+limit])
    result=[]
    for group in unique:
        day=group["calendar_day"]
        selected=grouped.filter(session_id=group["session_id"],calendar_day=day)
        rows=list(ready_frames(selected).order_by("-processed_at","-frame_index")[:100])
        if not rows: continue
        def score(row):
            return sum(5 if ob.track.confirmed_id else 3 if ob.candidate_id and not ob.track.reviewed_at else 0 for ob in row.observations.all())
        best=max(rows,key=score)
        payload=frame_payload(best)
        payload.update(sample_count=selected.count(),analysis_label=stamp(best.processed_at),
                       date_key=day.isoformat() if day else None,date_label=date_label(day),date_basis=basis,
                       group_time=group["last"].isoformat() if group["last"] else None,
                       frames=[frame_payload(f) for f in reversed(rows)])
        result.append(payload)
    return result


def profile_payload(profile, with_timeline=False):
    tracks=person_tracks(profile).select_related("session","candidate_frame")
    confirmed=tracks.filter(confirmed=profile)
    candidates=tracks.filter(confirmed__isnull=True)
    sources={source_key(t.session) for t in tracks}
    frames=TrackingFrame.objects.filter(observations__track__in=tracks).distinct()
    latest=frames.order_by("-processed_at").first()
    earliest=frames.order_by("processed_at").first()
    best=tracks.order_by("-similarity","pk").first()
    representative=best.candidate_frame if best and best.candidate_frame_id else latest
    portrait=(reverse("history_image",args=[representative.pk])+(f"?track={best.pk}" if best and best.candidate_frame_id==representative.pk else "")) if representative else None
    data={"key":profile.pk,"name":profile.display_name,"confirmed_tracks":confirmed.count(),
          "candidate_tracks":candidates.count(),"source_count":len(sources),"session_count":tracks.values("session_id").distinct().count(),
          "sampled_frames":frames.count(),"last_observed_at":None,
          "first_analysis_at":earliest.processed_at.isoformat() if earliest else None,
          "last_analysis_at":latest.processed_at.isoformat() if latest else None,
          "last_analysis_label":stamp(latest.processed_at) if latest else "관측 기록 없음",
          "reference_available":bool(profile.reference_image),
          "reference_url":reverse("history_reference",args=[profile.pk]) if profile.reference_image else None,
          "portrait_url":reverse("history_reference",args=[profile.pk]) if profile.reference_image else portrait,
          "observation_url":portrait,
          "detail_url":reverse("person_detail",args=[profile.pk]),"active":bool(latest),
          "status":"확인된 이력 있음" if confirmed.exists() else "얼굴 후보 검토 필요" if candidates.exists() else "관측 기록 없음"}
    observed=frames.exclude(observed_at=None).order_by("-observed_at").first()
    if observed: data["last_observed_at"]=observed.observed_at.isoformat()
    if with_timeline:
        data["timeline"]=session_cards(frames,24)
        data["days"]=daily_summary(frames)
        data["pending"]=[{"id":t.pk,"revision":t.revision,"candidate":t.candidate_id,"similarity":t.similarity,
                          "source":t.session.source_label,"image_url":reverse("history_image",args=[t.candidate_frame_id])+f"?track={t.pk}",
                          "frame_id":t.candidate_frame_id} for t in candidates if t.candidate_frame_id][:12]
    return data
