"""Only bounded ORM filters run here. Text and LLM output never become SQL."""
from datetime import date, datetime, time, timedelta
import re

from django.db.models import Q, Count, CharField
from django.db.models.functions import TruncDate, Coalesce, Cast
from django.utils import timezone
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from .models import PersonProfile, PersonTrack, TrackingFrame, PassageEvent


def date_range(question="", start="", end=""):
    today = timezone.localdate()
    explicit = re.findall(r"(\d{4})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})일?", question)
    if not start and not end:
        try:
            if explicit:
                values = [date(*map(int, parts)) for parts in explicit]
                if len(values) > 2:
                    raise ValueError
                start, end = values[0], values[-1]
            elif "어제" in question:
                start = end = today - timedelta(days=1)
            elif "오늘" in question:
                start = end = today
            elif "지난주" in question:
                end = today - timedelta(days=today.weekday() + 1)
                start = end - timedelta(days=6)
            elif "이번 주" in question or "이번주" in question:
                start, end = today - timedelta(days=today.weekday()), today
            elif re.search(r"\d+\s*(일|월|주|년)", question):
                raise ValidationError("날짜는 YYYY-MM-DD 형식이나 날짜 필터로 지정해주세요.")
        except ValueError:
            raise ValidationError("질문의 날짜를 확인해주세요.") from None
    try:
        start = date.fromisoformat(start) if isinstance(start, str) and start else start or None
        end = date.fromisoformat(end) if isinstance(end, str) and end else end or None
        if start and end and (start > end or (end-start).days > 3660):
            raise ValueError
    except (ValueError, TypeError):
        raise ValidationError("시작일과 종료일을 확인해주세요.") from None
    return start, end


def filtered_frames(params, question=""):
    start, end = date_range(question, params.get("start", ""), params.get("end", ""))
    frames = TrackingFrame.objects.all()
    basis=params.get("date_basis","recorded")
    if basis not in ("recorded","processed"):
        raise ValidationError("시간 기준을 확인해주세요.")
    date_field="processed_at" if basis=="processed" else "observed_at"
    tz = timezone.get_current_timezone()
    if start:
        frames = frames.filter(**{date_field+"__gte":timezone.make_aware(datetime.combine(start,time.min),tz)})
    if end:
        frames = frames.filter(**{date_field+"__lt":timezone.make_aware(datetime.combine(end+timedelta(days=1),time.min),tz)})
    session=params.get("session","")
    if session:
        from uuid import UUID
        try: frames=frames.filter(session_id=UUID(session))
        except (ValueError,TypeError): raise ValidationError("영상 실행 번호를 확인해주세요.") from None
    if params.get("context_sessions"):
        frames = frames.filter(session_id__in=params["context_sessions"])
    key = params.get("profile", "").strip()
    if not key and question:
        profiles = list(PersonProfile.objects.all()[:101])
        mentioned = [p.key for p in profiles if p.display_name in question or p.key in question]
        if len(mentioned) > 1:
            raise ValidationError("한 번에 한 인물 프로필을 선택해주세요.")
        if mentioned:
            key = mentioned[0]
        elif any(word in question for word in ["이 사람", "이사람", "그 사람", "그사람"]):
            raise ValidationError("조회할 인물 프로필을 선택해주세요.")
    if key and not PersonProfile.objects.filter(pk=key).exists():
        raise ValidationError("조회할 인물 프로필을 찾을 수 없습니다.")
    include = params.get("include_candidates", False) in (True, "true", "1", "on")
    tracks = PersonTrack.objects.all()
    if key:
        condition = Q(confirmed_id=key)
        if include:
            condition |= Q(confirmed__isnull=True, reviewed_at__isnull=True, candidate_id=key)
        tracks = tracks.filter(condition)
        frames = frames.filter(observations__track__in=tracks).distinct()
    return frames, tracks, {"start": str(start) if start else None, "end": str(end) if end else None,
                            "profile": key or None, "include_candidates": include,"date_basis":basis}


def frame_payload(frame):
    return {"id": frame.pk, "session_id": str(frame.session_id),
            "source": frame.session.source_label, "source_kind": frame.session.source_kind,
            "frame_index": frame.frame_index, "video_seconds": frame.video_seconds,
            "observed_at": frame.observed_at.isoformat() if frame.observed_at else None,
            "processed_at": frame.processed_at.isoformat(),
            "purpose": frame.session.configuration.get("purpose", "demo" if frame.session.configuration.get("model_versions",{}).get("demo_provenance") else "recording"),
            "source_reference":frame.session.configuration.get("source_reference"),
            "unassigned_face_count":len(frame.unassigned_faces),
            "time_basis": ("live_received" if frame.session.source_kind == "live" else "recorded")
                          if frame.observed_at else "unknown_recording_date",
            "image_url": reverse("history_image", args=[frame.pk]) + "?boxes=1" if frame.image else None,
            "post_url": reverse("post_detail", args=[frame.post_id]) if frame.post_id else None,
            "tracks": [{"id": ob.track_id, "track_id": ob.track.track_id, "bbox": ob.bbox,
                "candidate": ob.candidate_id, "similarity": ob.similarity,
                "confirmed": ob.track.confirmed_id, "reviewed": ob.track.reviewed_at is not None,
                "revision": ob.track.revision,"review_basis":ob.track.review_basis,
                "face_url":reverse("history_image",args=[frame.pk])+f"?track={ob.track_id}" if ob.face_bbox else None} for ob in frame.observations.all()],
            "passages": [{"id": e.pk, "track_id": e.track_id, "direction": e.direction}
                         for e in frame.passages.all()]}


def ready_frames(frames):
    return frames.select_related("session").prefetch_related("observations__track", "passages")


def retrieve(params, question=""):
    frames, tracks, interpretation = filtered_frames(params, question)
    retrieval = {"strategy": "structured", "status": "not_requested", "api_requests": 0}
    if params.get("semantic") is True:
        from .history_embeddings import rank
        retrieval = rank(question, frames, allow_api=params.get("cache_only") is not True)
        if retrieval["status"] in ("ranked", "no_match", "empty"):
            frames = frames.filter(session_id__in=retrieval["session_ids"])
    observed = tracks.filter(observations__frame__in=frames).distinct()
    events = PassageEvent.objects.filter(frame__in=frames, track__in=tracks)
    counts = events.aggregate(total=Count("id"), direction_in=Count("id", filter=Q(direction="in")),
                              direction_out=Count("id", filter=Q(direction="out")))
    date_field="processed_at" if interpretation["date_basis"]=="processed" else "observed_at"
    days = list(frames.filter(**{date_field+"__isnull":False}).annotate(day=TruncDate(date_field))
                .order_by("day").values_list("day", flat=True).distinct()[:3661])
    facts = {"sampled_frames": frames.count(), "observed_tracks": observed.count(),
             "confirmed_tracks": observed.filter(confirmed__isnull=False).count(),
             "candidate_tracks": observed.filter(confirmed__isnull=True, reviewed_at__isnull=True, candidate__isnull=False).count(),
             "confirmed_profiles": observed.exclude(confirmed__isnull=True).values("confirmed_id").distinct().count(),
             "passages": counts["total"], "direction_in": counts["direction_in"],
             "direction_out": counts["direction_out"],
             "unknown_date_frames": frames.filter(observed_at__isnull=True).count(),
             "dates": [str(day) for day in days],
             "date_basis":interpretation["date_basis"],
             "timezone": str(timezone.get_current_timezone())}
    from .monitoring_presenter import session_cards
    if retrieval["status"] == "ranked":
        grouped=[]
        for session_id in retrieval["session_ids"]:
            grouped.extend(session_cards(frames.filter(session_id=session_id),1,basis=interpretation["date_basis"]))
    else:
        grouped=session_cards(frames,12)
    evidence=[{k:v for k,v in row.items() if k!="frames"} for row in grouped]
    facts["source_count"]=frames.annotate(source_key=Coalesce(Cast("session__configuration__source_reference",CharField()),Cast("session_id",CharField()))).values("source_key").distinct().count()
    facts["dataset_confirmed_tracks"]=observed.filter(confirmed__isnull=False,review_basis="dataset").count()
    sources=[{"session_id":row["session_id"],"label":row["source"],"reference":row["source_reference"],"sampled_frames":row["sample_count"]} for row in grouped]
    return {"facts": facts, "interpretation": interpretation, "evidence": evidence,"sources":sources,
            "retrieval": retrieval,
            "intent":"sources" if any(word in question for word in ("영상","출처","어디")) else "summary"}


def answer_records(result):
    f = result["facts"]
    if not f["sampled_frames"]:
        return "조건에 맞는 기록이 없습니다. 기록이 없다는 결과만으로 실제로 아무도 오지 않았다고 판단할 수는 없습니다."
    text = (f'조회 조건에 맞는 기록은 영상 출처 {f["source_count"]}개에 있습니다. ' if result.get("intent")=="sources" else f'조건에 맞는 추적 기록은 {f["observed_tracks"]}개이고 선 통과는 {f["passages"]}건입니다. ')
    if result.get("sources"):
        text += "영상: "+", ".join(s["label"] for s in result["sources"][:4])+". "
    text += f'발견된 영상 출처는 {f["source_count"]}개입니다. '
    text += f'방향 1은 {f["direction_in"]}건, 방향 2는 {f["direction_out"]}건입니다. '
    text += f'확인된 인물 프로필은 {f["confirmed_profiles"]}개입니다. '
    if f.get("dataset_confirmed_tracks"):
        text += f'공개 데이터셋 정답으로 확인한 시연 추적은 {f["dataset_confirmed_tracks"]}개입니다. '
    if f["dates"]:
        shown = f["dates"][:14]
        text += ("분석 날짜는 " if f["date_basis"]=="processed" else "촬영 날짜가 확인된 기록은 ") + ", ".join(shown) + "에 있습니다. "
        if len(f["dates"]) > len(shown):
            text += f'전체 날짜 {len(f["dates"])}개는 조회 결과에서 확인할 수 있습니다. '
    if f["unknown_date_frames"]:
        text += f'촬영 날짜가 없는 확인 사진 {f["unknown_date_frames"]}개는 날짜를 확정하지 않았습니다. '
    text += "추적 번호는 영상 실행마다 달라질 수 있으며 통과 건수는 방문 횟수나 서로 다른 사람 수와 같지 않습니다."
    if result.get("retrieval", {}).get("scope") == "semantic_top_5":
        text += " 의미 검색으로 선택된 최대 5개 영상의 기록 기준입니다."
    return text
