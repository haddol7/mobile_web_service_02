"""Assessment E03/E05: independent rules, transaction and API acceptance tests."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from blog.content_rules import ContentError, normalize, query_terms, validate_packet, validate_quad
from blog.content_services import update_content
from blog.models import PhotoContent, PhotoTag, PhotoTextLine, Post
from blog.services import create_post, update_post
from .helpers import TemporaryMediaMixin, photo_bytes, uploaded_photo


def packet(*, text="바다 라멘 Cafe 100%", revision=None, size=(48, 32)):
    result = {"schema_version": 1, "image_sha256": hashlib.sha256(photo_bytes(size)).hexdigest(),
              "width": size[0], "height": size[1], "model_versions": {"label": "17.0.9", "ocr_ko": "16.0.1"},
              "mapping_version": "theme_mapping_v1", "theme": "food", "theme_status": "classified", "theme_origin": "user",
              "tags": [{"display": "라멘", "origin": "user"}], "ocr_status": "ready",
              "lines": [{"line_id": str(uuid4()), "text": text, "quad": [[.1,.1],[.8,.1],[.8,.4],[.1,.4]], "origin": "user"}]}
    if revision is not None:
        result["expected_revision"] = revision
    return result


class ContentRuleTests(SimpleTestCase):
    def test_normalization_nfkc_casefold_spaces_and_korean(self):
        self.assertEqual(normalize("  ＣＡＦＥ\t바다  라멘  "), "cafe 바다 라멘")
        self.assertEqual(normalize("Straße"), "strasse")

    def test_query_deduplicates_terms_and_preserves_literal_wildcards(self):
        self.assertEqual(query_terms("CAFE cafe 100% _간판"), ["cafe", "100%", "_간판"])

    def test_query_rejects_empty_short_long_many_and_controls(self):
        for value in ("", "가", "가"*81, "aa bb cc dd ee ff", "ca\x00fe", None):
            with self.subTest(value=value), self.assertRaises(ContentError):
                query_terms(value)

    def test_packet_normalizes_and_deduplicates_tags_without_mutating_input(self):
        value = packet()
        value["tags"] = [{"display":"ＣＡＦＥ", "origin":"auto"}, {"display":"cafe", "origin":"user"}]
        original = deepcopy(value)
        result = validate_packet(value)
        self.assertEqual(value, original)
        self.assertEqual(len(result["tags"]), 1)
        self.assertEqual(result["tags"][0]["normalized"], "cafe")
        self.assertEqual(result["lines"][0]["compact_text"], "바다라멘cafe100%")

    def test_packet_rejects_missing_and_unapproved_fields(self):
        for edit in (lambda p:p.pop("width"), lambda p:p.update(face_boxes=[]), lambda p:p["lines"][0].update(included=False)):
            value=packet(); edit(value)
            with self.subTest(edit=edit), self.assertRaises(ContentError): validate_packet(value)

    def test_dimensions_schema_hash_and_revision_are_strict(self):
        for key, value in (("width",True),("width",8193),("height",0),("schema_version",2),
                           ("image_sha256","0"*63),("expected_revision",-1),("expected_revision",False)):
            data=packet(); data[key]=value
            with self.subTest(key=key,value=value), self.assertRaises(ContentError): validate_packet(data)
        data=packet(); data.update(width=8192,height=8192)
        with self.assertRaises(ContentError): validate_packet(data)

    def test_classification_cross_field_rules_and_empty_selection(self):
        data=packet(); data.update(theme=None,theme_status="unclassified",theme_origin="unclassified")
        self.assertIsNone(validate_packet(data)["theme"])
        for changes in ({"theme":"unknown"},{"theme":None},{"theme_status":"invalid"},
                        {"theme_status":"not_analyzed"},{"theme_origin":"unknown"}):
            value=packet(); value.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ContentError): validate_packet(value)

    def test_quad_rejects_nan_infinity_boolean_crossed_reversed_and_degenerate(self):
        for quad in ([[[0,0],[1,1],[1,0],[0,1]], [[0,0],[0,1],[1,1],[1,0]],
                      [[0,0],[1,0],[1,0],[0,0]], [[False,0],[1,0],[1,1],[0,1]],
                      [[float("nan"),0],[1,0],[1,1],[0,1]], [[0,0],[1,0],[1,float("inf")],[0,1]],
                      [[-.1,0],[1,0],[1,1],[0,1]], [[0,0],[1,0],[1,1]]]):
            with self.subTest(quad=quad), self.assertRaises(ContentError): validate_quad(quad,"lines")

    def test_duplicate_invalid_id_and_invalid_origin_rejected(self):
        for change in (lambda p:p["lines"].append(deepcopy(p["lines"][0])),
                       lambda p:p["lines"][0].update(line_id="bad"),
                       lambda p:p["lines"][0].update(origin="raw")):
            data=packet(); change(data)
            with self.assertRaises(ContentError): validate_packet(data)

    def test_limits_for_tags_lines_text_and_versions(self):
        edits=[lambda p:p.update(tags=[{"display":str(i),"origin":"user"} for i in range(11)]),
               lambda p:p.update(lines=[dict(p["lines"][0],line_id=str(uuid4())) for _ in range(101)]),
               lambda p:p["lines"][0].update(text="가"*201),
               lambda p:p["tags"][0].update(display="가"*31),
               lambda p:p.update(model_versions={"unsupported":"1"}),
               lambda p:p.update(model_versions={"label": None}),
               lambda p:p.update(mapping_version="x"*41)]
        for edit in edits:
            data=packet(); edit(data)
            with self.subTest(edit=edit), self.assertRaises(ContentError): validate_packet(data)

    def test_total_text_limit_and_utf8_payload_limit(self):
        data=packet(); data["lines"]=[dict(data["lines"][0],line_id=str(uuid4()),text="한"*200) for _ in range(42)]
        with self.assertRaises(ContentError): validate_packet(data)
        data["lines"]=data["lines"]*10
        with self.assertRaises(ContentError) as error: validate_packet(data)
        self.assertEqual(error.exception.status, 413)

    def test_ocr_statuses_and_excluded_all_lines(self):
        data=packet(); data["lines"]=[]
        self.assertEqual(validate_packet(data)["lines"],[])
        for status in ("no_text","skipped","failed","not_analyzed"):
            data["ocr_status"]=status
            self.assertEqual(validate_packet(data)["ocr_status"],status)
            invalid=packet(); invalid["ocr_status"]=status
            with self.assertRaises(ContentError): validate_packet(invalid)

    def test_non_json_values_surrogates_controls_and_invalid_container(self):
        for edit in (lambda p:p.update(width=float("nan")), lambda p:p.update(width={1}),
                     lambda p:p["lines"][0].update(text="\ud800"),lambda p:p["lines"][0].update(text="hello\x00")):
            value=packet(); edit(value)
            with self.assertRaises(ContentError): validate_packet(value)
        for value in ([],None,"{}"):
            with self.assertRaises(ContentError): validate_packet(value)


class ContentAPITests(TemporaryMediaMixin, TestCase):
    def setUp(self):
        from django.test import override_settings
        publisher = override_settings(BLOG_OWNER_USERNAME="content-owner")
        publisher.enable()
        self.addCleanup(publisher.disable)
        super().setUp()
        self.owner=get_user_model().objects.create_user("content-owner",password="content-fixture-48")
        self.other=get_user_model().objects.create_user("content-visitor",password="other-fixture-48")
        self.api=APIClient(); self.api.force_authenticate(self.owner)

    def create(self, data=None, title="제목에 가게 문구 없음", size=(48,32)):
        body={"title":title,"text":"본문에도 검색어 없음","image":uploaded_photo(size=size)}
        if data is not None: body["photo_content"]=json.dumps(data,ensure_ascii=False)
        response=self.api.post("/api_root/Post/",body,format="multipart")
        self.assertEqual(response.status_code,201,response.data)
        return Post.objects.get(pk=response.data["id"])

    def url(self,post): return f"/api/v1/posts/{post.pk}/content/"
    def search(self,q,**params): return self.api.get("/api/v1/photo-text-search/",{"q":q,**params})

    def test_upload_keeps_legacy_array_and_exact_seven_read_fields(self):
        post=self.create(packet())
        response=self.api.get("/api_root/Post/")
        self.assertIsInstance(response.data,list)
        self.assertEqual(set(response.data[0]),{"id","author","title","text","created_date","published_date","image"})
        detail=self.api.get(self.url(post)).data
        self.assertEqual((detail["revision"],detail["theme"],detail["lines"][0]["text"]),(1,"food","바다 라멘 Cafe 100%"))

    def test_old_upload_has_unanalyzed_content_and_first_correction(self):
        post=self.create()
        self.assertEqual(self.api.get(self.url(post)).data["revision"],0)
        response=self.api.patch(self.url(post),packet(revision=0),format="json")
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data["revision"],1)

    def test_browsable_multipart_optional_analysis_can_be_empty_or_null(self):
        for value in ("", "null"):
            response = self.api.post("/api_root/Post/", {"title": "기본 API 게시", "text": "사진 게시", "image": uploaded_photo(), "photo_content": value}, format="multipart")
            self.assertEqual(response.status_code, 201, response.data)

    def test_hash_or_size_mismatch_rolls_back_post_and_new_file(self):
        for changes in ({"image_sha256":"0"*64},{"width":49}):
            bad=packet(); bad.update(changes)
            response=self.api.post("/api_root/Post/",{"title":"bad","text":"body","image":uploaded_photo(),"photo_content":json.dumps(bad)},format="multipart")
            self.assertEqual(response.status_code,400,response.data)
            self.assertEqual(Post.objects.count(),0)
            self.assertEqual(list(Path(self.media_root).rglob("*.png")),[])

    def test_database_failure_cleans_new_file_and_all_metadata(self):
        with patch("blog.content_services.PhotoTextLine.objects.bulk_create",side_effect=RuntimeError("simulated storage failure")):
            with self.assertRaises(RuntimeError):
                create_post(actor=self.owner,values={"title":"rollback","text":"body","image":uploaded_photo(),"photo_content":packet()})
        self.assertEqual((Post.objects.count(),PhotoContent.objects.count(),PhotoTag.objects.count()),(0,0,0))
        self.assertEqual(list(Path(self.media_root).rglob("*.png")),[])

    def test_correction_replaces_search_terms_and_preserves_locations(self):
        post=self.create(packet(text="틀린가게"))
        data=packet(text="바른가게",revision=1)
        response=self.api.patch(self.url(post),data,format="json")
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data["lines"][0]["quad"],data["lines"][0]["quad"])
        self.assertEqual(self.search("틀린가게").data["results"],[])
        self.assertEqual(len(self.search("바른가게").data["results"]),1)
        data["expected_revision"]=2; data["lines"]=[]
        self.assertEqual(self.api.patch(self.url(post),data,format="json").status_code,200)
        self.assertEqual(self.search("바른가게").data["results"],[])

    def test_owner_only_correction_and_anonymous_public_search(self):
        post=self.create(packet())
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.patch(self.url(post),packet(revision=1),format="json").status_code,403)
        self.api.force_authenticate(None)
        self.assertIn(self.api.patch(self.url(post),packet(revision=1),format="json").status_code,(401,403))
        self.assertEqual(self.search("바다라멘").status_code,200)
        self.assertIn(self.search("바다라멘",author="me").status_code,(401,403))

    def test_stale_revision_missing_revision_and_stale_digest_do_not_write(self):
        post=self.create(packet())
        for data,status in ((packet(revision=0),409),(packet(),400),(dict(packet(revision=1),image_sha256="0"*64),400)):
            response=self.api.patch(self.url(post),data,format="json")
            self.assertEqual(response.status_code,status,response.data)
            self.assertEqual(PhotoContent.objects.get(post=post).revision,1)

    def test_image_replacement_invalidates_search_and_monotonically_increases_revision(self):
        post=self.create(packet())
        response=self.api.patch(f"/api_root/Post/{post.pk}/",{"image":uploaded_photo(size=(24,16))},format="multipart")
        self.assertEqual(response.status_code,200,response.data)
        detail=self.api.get(self.url(post)).data
        self.assertEqual((detail["revision"],detail["ocr_status"],detail["theme"]),(2,"not_analyzed",None))
        self.assertEqual(self.search("바다라멘").data["results"],[])
        self.assertEqual(self.api.patch(self.url(post),packet(revision=1),format="json").status_code,409)

    def test_same_bytes_replacement_also_invalidates_and_title_only_preserves(self):
        post=self.create(packet())
        update_post(actor=self.owner,post_id=post.pk,values={"title":"수정 제목"})
        self.assertEqual(PhotoContent.objects.get(post=post).revision,1)
        update_post(actor=self.owner,post_id=post.pk,values={"image":uploaded_photo()})
        self.assertEqual(PhotoContent.objects.get(post=post).revision,2)

    def test_atomic_image_and_fresh_content_replacement(self):
        post=self.create(packet())
        data=packet(text="새메뉴",revision=1,size=(24,16))
        response=self.api.patch(f"/api_root/Post/{post.pk}/",{"image":uploaded_photo(size=(24,16)),"photo_content":json.dumps(data)},format="multipart")
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(self.search("바다라멘").data["results"],[])
        self.assertEqual(len(self.search("새메뉴").data["results"]),1)

    def test_failed_replacement_keeps_old_image_and_content(self):
        post=self.create(packet()); original=post.image.name
        data=packet(revision=1); data["image_sha256"]="0"*64
        response=self.api.patch(f"/api_root/Post/{post.pk}/",{"image":uploaded_photo(size=(24,16)),"photo_content":json.dumps(data)},format="multipart")
        self.assertEqual(response.status_code,400,response.data)
        post.refresh_from_db()
        self.assertEqual(post.image.name,original)
        self.assertTrue(Path(post.image.path).exists())
        self.assertEqual(len(list(Path(self.media_root).rglob("*.png"))),1)
        self.assertEqual(PhotoContent.objects.get(post=post).revision,1)

    def test_literal_percent_underscore_and_sql_like_text(self):
        self.create(packet(text="CAFE １００% a_b ' OR 1=1 --"))
        self.create(packet(text="unrelated 100x axb"))
        for q in ("cafe","100%","a_b","' OR"):
            response=self.search(q)
            self.assertEqual(response.status_code,200,response.data)
            self.assertEqual(len(response.data["results"]),1)

    def test_and_terms_across_different_lines_and_filter_intersection(self):
        data=packet(text="바다 라멘"); data["lines"].append(dict(data["lines"][0],line_id=str(uuid4()),text="CAFE"))
        self.create(data)
        self.assertEqual(len(self.search("바다라멘 CAFE",theme="food",tag="라멘").data["results"]),1)
        self.assertEqual(self.search("바다라멘 CAFE",theme="animal").data["results"],[])
        self.assertEqual(self.search("바다라멘 없는단어").data["results"],[])

    def test_multiword_highlight_ignores_lines_containing_only_common_words(self):
        data = packet(text="This is a lot of 12 point text to test the")
        wanted = data["lines"][0]["line_id"]
        for text in ("of file format.", "The quick brown dog jumped over the", "lazy fox jumped over"):
            data["lines"].append(dict(data["lines"][0], line_id=str(uuid4()), text=text))
        post = self.create(data)
        result = self.search("This is a lot").data["results"][0]
        self.assertEqual([line["line_id"] for line in result["matched_lines"]], [wanted])
        page = self.client.get(f"/post/{post.pk}/", {"q": "This is a lot"})
        self.assertEqual(page.context["detail_config"]["matched_ids"], [wanted])

    def test_split_line_highlight_covers_terms_without_duplicate_common_lines(self):
        from blog.content_queries import matching_line_ids
        lines = [{"line_id": "a", "text": "바다 라멘"},
                 {"line_id": "b", "text": "CAFE MENU"},
                 {"line_id": "c", "text": "CAFE OTHER"}]
        self.assertEqual(matching_line_ids(lines, ["바다라멘", "cafe"]), ["a", "b"])
        self.assertEqual(matching_line_ids(lines, ["바다라멘", "없는단어"]), [])
        self.assertEqual(matching_line_ids(lines, []), [])

    def test_future_publication_is_hidden_from_all_content_endpoints(self):
        post=self.create(packet()); Post.objects.filter(pk=post.pk).update(published_date=timezone.now()+timezone.timedelta(days=1))
        self.assertEqual(self.api.get(self.url(post)).status_code,404)
        self.assertEqual(self.search("바다라멘").data["results"],[])
        self.assertEqual(self.api.get("/api/v1/content-posts/").data["results"],[])
        self.assertEqual(self.api.get("/api/v1/post-contents/",{"ids":str(post.pk)}).data["results"],[])

    def test_pagination_binds_query_and_excludes_newer_insertions(self):
        for i in range(3): self.create(packet(),title=str(i))
        first=self.search("바다라멘",limit=1).data
        self.create(packet(),title="later")
        second=self.search("바다라멘",limit=1,cursor=first["next_cursor"])
        self.assertEqual(second.status_code,200,second.data)
        self.assertNotEqual(second.data["results"][0]["post"]["id"],first["results"][0]["post"]["id"])
        self.assertEqual(self.search("다른검색",limit=1,cursor=first["next_cursor"]).status_code,400)
        self.assertEqual(self.search("바다라멘",cursor="bad").status_code,400)

    def test_summary_batch_unclassified_and_own_filter(self):
        analyzed=self.create(packet()); legacy=self.create()
        response=self.api.get("/api/v1/post-contents/",{"ids":f"{analyzed.pk},{legacy.pk},{analyzed.pk}"})
        self.assertEqual(len(response.data["results"]),2)
        self.assertNotIn("lines",response.data["results"][0])
        result=self.api.get("/api/v1/content-posts/",{"theme":"unclassified","author":"me"})
        self.assertEqual([r["post"]["id"] for r in result.data["results"]],[legacy.pk])

    def test_bad_queries_and_batches_return_clear_400(self):
        for args in ({"theme":"bad"},{"author":"all"},{"limit":"0"},{"limit":"999"},{"q":"x"},{"tag":"x"*31},{"unknown":"x"}):
            query = args.get("q", "테스트")
            params = {k:v for k,v in args.items() if k != "q"}
            with self.subTest(args=args):
                self.assertEqual(self.search(query, **params).status_code,400)
        for ids in ("", "0", "1,-2", "x", ",".join(str(i+1) for i in range(51))):
            self.assertEqual(self.api.get("/api/v1/post-contents/",{"ids":ids}).status_code,400)

    def test_delete_cascades_content_and_search_rows(self):
        post=self.create(packet())
        self.assertEqual(self.api.delete(f"/api_root/Post/{post.pk}/").status_code,204)
        self.assertEqual((PhotoContent.objects.count(),PhotoTag.objects.count(),PhotoTextLine.objects.count()),(0,0,0))

    def test_session_correction_requires_real_csrf_token(self):
        post=self.create(packet())
        browser=APIClient(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        csrf=browser.get("/api/v1/auth/me/").data["csrf_token"]
        data=packet(revision=1)
        self.assertEqual(browser.patch(self.url(post),data,format="json").status_code,403)
        result=browser.patch(self.url(post),data,format="json",HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(result.status_code,200,result.data)
