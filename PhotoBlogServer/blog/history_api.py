import json
from django.core.cache import cache
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import ValidationError, Throttled
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PersonProfile, PersonTrack, TrackingFrame
from .ownership import is_blog_owner
from .history_access import ReadOrHistoryOwner, PublicQuestionPermission, conversation_owner
from .history_serializers import PacketSerializer, StrictSerializer
from .history_services import ingest, review_track
from .history_queries import retrieve, ready_frames, filtered_frames, frame_payload, answer_records
from .history_llm import generate


class IsHistoryOwner(BasePermission):
    def has_permission(self, request, view):
        return is_blog_owner(request.user)


class HistoryAPI(APIView):
    permission_classes = [IsHistoryOwner]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class HistoryIngest(HistoryAPI):
    def post(self, request):
        packet = request.data.get("packet") if "packet" in request.data else request.data
        if isinstance(packet, str):
            if len(packet) > 150000:
                raise ValidationError("기록 데이터가 너무 큽니다.")
            try:
                packet = json.loads(packet)
            except ValueError:
                raise ValidationError("기록 데이터를 확인해주세요.") from None
        serializer = PacketSerializer(data=packet)
        serializer.is_valid(raise_exception=True)
        frame, created = ingest(actor=request.user, packet=serializer.validated_data, upload=request.FILES.get("image"))
        return Response({"id": frame.pk, "created": created}, status=201 if created else 200)


class PublicReadHistoryAPI(HistoryAPI):
    permission_classes = [ReadOrHistoryOwner]


class PublicQuestionAPI(HistoryAPI):
    permission_classes = [PublicQuestionPermission]


class HistoryOverview(PublicReadHistoryAPI):
    def get(self, request):
        from .monitoring import overview
        return Response(overview())


class HistoryProfiles(PublicReadHistoryAPI):
    def get(self, request):
        return Response({"results": [{"key": p.key, "name": p.display_name}
                         for p in PersonProfile.objects.order_by("display_name", "key")[:100]]})

    def patch(self, request):
        class Rename(StrictSerializer):
            key = serializers.CharField(max_length=64)
            name = serializers.CharField(max_length=80)
        form = Rename(data=request.data)
        form.is_valid(raise_exception=True)
        profile = get_object_or_404(PersonProfile, pk=form.validated_data["key"])
        profile.display_name = form.validated_data["name"]
        profile.save(update_fields=["display_name"])
        return Response({"key": profile.pk, "name": profile.display_name})


class HistoryPerson(PublicReadHistoryAPI):
    def get(self, request, profile_key):
        from .monitoring_presenter import profile_payload
        return Response(profile_payload(get_object_or_404(PersonProfile,pk=profile_key),with_timeline=True))


class HistorySessions(PublicReadHistoryAPI):
    def get(self, request):
        from .monitoring_presenter import session_cards,daily_summary
        frames,_,interpretation=filtered_frames(request.query_params)
        try: page=int(request.query_params.get("page",1))
        except (ValueError,TypeError): raise ValidationError("페이지를 확인해주세요.") from None
        if not 1<=page<=10000: raise ValidationError("페이지를 확인해주세요.")
        basis=interpretation["date_basis"]
        cards=session_cards(frames,13,basis=basis,offset=(page-1)*12)
        # Day navigation retains other available dates while the content uses the selected day/range.
        navigation={key:value for key,value in request.query_params.items() if key not in ("start","end","page")}
        available,_,_=filtered_frames(navigation)
        return Response({"results":cards[:12],"page":page,"days":daily_summary(available,basis),
                         "next_page":page+1 if len(cards)>12 else None,"interpretation":interpretation})


class HistoryReference(PublicReadHistoryAPI):
    def get(self,request,profile_key):
        from rest_framework.exceptions import NotFound
        profile=get_object_or_404(PersonProfile,pk=profile_key)
        if not profile.reference_image: raise NotFound()
        try: response=FileResponse(profile.reference_image.open("rb"),content_type="image/jpeg")
        except FileNotFoundError: raise NotFound() from None
        response["X-Content-Type-Options"]="nosniff"
        return response

    def post(self,request,profile_key):
        from django.core.files.base import ContentFile
        from django.db import transaction
        from .history_services import clean_image
        from .services import lock_owner
        profile=get_object_or_404(PersonProfile,pk=profile_key)
        raw,sanitized=clean_image(request.FILES.get("image"))
        if not sanitized: raise ValidationError("등록 얼굴 사진이 필요합니다.")
        saved=None
        try:
            with transaction.atomic():
                lock_owner(request.user.pk)
                profile.reference_image.save("reference.jpg",ContentFile(sanitized),save=False)
                saved=profile.reference_image.name
                profile.save(update_fields=["reference_image"])
        except Exception:
            if saved: profile.reference_image.storage.delete(saved)
            raise
        return Response({"key":profile.pk,"reference_available":True})


class HistoryFrames(PublicReadHistoryAPI):
    def get(self, request):
        class Paging(serializers.Serializer):
            page = serializers.IntegerField(min_value=1, max_value=100000, default=1)
            limit = serializers.IntegerField(min_value=1, max_value=24, default=12)
        form = Paging(data=request.query_params)
        form.is_valid(raise_exception=True)
        page, limit = form.validated_data["page"], form.validated_data["limit"]
        frames, _, interpretation = filtered_frames(request.query_params)
        offset = (page-1)*limit
        rows = list(ready_frames(frames).order_by("-processed_at", "-frame_index", "id")[offset:offset+limit+1])
        return Response({"results": [frame_payload(f) for f in rows[:limit]], "page": page,
                         "next_page": page+1 if len(rows)>limit else None, "interpretation": interpretation})


class TrackReview(HistoryAPI):
    def patch(self, request, track_id):
        class Review(StrictSerializer):
            revision = serializers.IntegerField(min_value=1)
            profile = serializers.CharField(max_length=64, allow_null=True)
            basis = serializers.ChoiceField(choices=["operator","dataset"],default="operator")
        form = Review(data=request.data)
        form.is_valid(raise_exception=True)
        get_object_or_404(PersonTrack, pk=track_id)
        track = review_track(
            actor=request.user, track_id=track_id, revision=form.validated_data["revision"],
            profile_key=form.validated_data["profile"],basis=form.validated_data["basis"])
        return Response({"id": track.pk, "confirmed": track.confirmed_id, "revision": track.revision,"review_basis":track.review_basis})


class HistoryImage(PublicReadHistoryAPI):
    def get(self, request, frame_id):
        frame = get_object_or_404(TrackingFrame, pk=frame_id)
        if not frame.image:
            from rest_framework.exceptions import NotFound
            raise NotFound()
        try:
            if request.query_params.get("track"):
                from io import BytesIO
                from PIL import Image
                from django.http import HttpResponse
                try: track_id=int(request.query_params["track"])
                except (ValueError,TypeError): raise ValidationError("추적 번호를 확인해주세요.") from None
                observation=get_object_or_404(frame.observations,track_id=track_id)
                if observation.face_bbox and len(frame.image_size)==2:
                    with frame.image.open("rb") as source, Image.open(source) as original:
                        image=original.convert("RGB");width,height=frame.image_size
                        x1,y1,x2,y2=observation.face_bbox
                        padding=max(x2-x1,y2-y1)*.32;cx=(x1+x2)/2;cy=(y1+y2)/2
                        half=max(x2-x1,y2-y1)/2+padding
                        box=(max(0,int((cx-half)*image.width/width)),max(0,int((cy-half)*image.height/height)),
                             min(image.width,int((cx+half)*image.width/width)),min(image.height,int((cy+half)*image.height/height)))
                        if box[2]>box[0] and box[3]>box[1]: image=image.crop(box)
                        image.thumbnail((320,320));buffer=BytesIO();image.save(buffer,"JPEG",quality=85)
                        response=HttpResponse(buffer.getvalue(),content_type="image/jpeg")
                        response["X-Content-Type-Options"]="nosniff"
                        return response
            if request.query_params.get("boxes") == "1":
                from django.http import HttpResponse
                from .history_annotations import annotated_image
                content, count = annotated_image(frame)
                response = HttpResponse(content, content_type="image/jpeg")
                response["X-Detection-Overlay"] = "1"
                response["X-Detection-Boxes"] = str(count)
            else:
                response = FileResponse(frame.image.open("rb"), content_type="image/jpeg")
        except FileNotFoundError:
            from rest_framework.exceptions import NotFound
            raise NotFound()
        response["X-Content-Type-Options"] = "nosniff"
        return response


class HistoryEmbeddingDocuments(HistoryAPI):
    def get(self, request):
        from .history_embeddings import documents, header, EmbeddingError
        try:
            return Response({**header(), "documents": documents()})
        except EmbeddingError:
            return Response({"detail": "의미 검색 색인에 사용할 기록을 준비하지 못했습니다."}, status=503)


class HistoryUsage(HistoryAPI):
    def get(self, request):
        from .request_limits import usage_status, LimitStoreUnavailable
        try:
            return Response(usage_status())
        except LimitStoreUnavailable:
            return Response({"detail": "사용량을 확인하지 못했습니다. 잠시 후 다시 시도해주세요."}, status=503)


class HistoryQuestion(PublicQuestionAPI):
    def post(self, request):
        class Question(StrictSerializer):
            question = serializers.CharField(max_length=400)
            start = serializers.CharField(max_length=10, allow_blank=True, default="")
            end = serializers.CharField(max_length=10, allow_blank=True, default="")
            profile = serializers.CharField(max_length=64, allow_blank=True, default="")
            include_candidates = serializers.BooleanField(default=False)
            generate = serializers.BooleanField(default=False)
            semantic = serializers.BooleanField(default=False)
            cache_only = serializers.BooleanField(default=False)
            conversation_id = serializers.UUIDField(required=False)
            request_id = serializers.UUIDField(required=False)
            date_basis = serializers.ChoiceField(choices=["recorded","processed"],default="recorded")
            session = serializers.CharField(max_length=36,allow_blank=True,default="")
        form = Question(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data
        if ("conversation_id" in data) != ("request_id" in data):
            raise ValidationError("대화와 질문 요청 번호를 함께 지정해주세요.")
        if data["cache_only"] and data["generate"]:
            raise ValidationError("캐시 검증 모드에서는 AI 설명을 생성하지 않습니다.")
        from . import chat_store
        owner = conversation_owner(request)
        conversation_id = str(data.pop("conversation_id")) if "conversation_id" in data else None
        request_id = str(data.pop("request_id")) if "request_id" in data else None
        turn_id, messages = None, []
        chat_lock = None
        if conversation_id:
            turn_id, replay = chat_store.reserve(owner, conversation_id, request_id, data["question"], data)
            if replay is not None:
                return Response({**replay, "replayed": True})
        try:
            if conversation_id and (data["semantic"] or data["generate"]):
                key = f"history-chat-{owner}"
                if not cache.add(key, True, 120):
                    raise Throttled(detail="이전 질문을 처리 중입니다. 대화 기록을 확인해주세요.", wait=5)
                chat_lock = key
            if conversation_id:
                messages, sessions = chat_store.previous_context(owner, conversation_id, turn_id)
                if sessions and data["question"].lstrip().startswith(("그중", "그 중", "그 영상", "해당 영상", "방금", "거기")):
                    data["context_sessions"] = sessions
                    data["semantic"] = False
            if data["semantic"] and not conversation_id and not cache.add(f"history-embedding-{owner}", True, 5):
                raise Throttled(wait=5)
            result = retrieve(data, data["question"])
            result.update(answer=answer_records(result), mode="records",
                          llm={"status": "not_requested", "text": None, "evidence_ids": []})
            semantic_ok = not data["semantic"] or result["retrieval"]["status"] in ("ranked", "no_match", "empty")
            if data["generate"] and semantic_ok:
                if not conversation_id and not cache.add(f"history-llm-{owner}", True, 5):
                    raise Throttled(wait=5)
                result["llm"] = generate(data["question"], {**result, "conversation_context": messages})
                if result["llm"]["status"] == "generated":
                    result["mode"] = "rag"
            if conversation_id:
                result["chat"] = {"conversation_id": conversation_id, "request_id": request_id, "turn_id": turn_id}
                chat_store.finish(owner, conversation_id, turn_id, result)
            return Response(result)
        except Exception:
            if conversation_id:
                chat_store.finish(owner, conversation_id, turn_id)
            raise
        finally:
            if chat_lock:
                cache.delete(chat_lock)
