"""Combine completed registration evidence without any remote or model calls."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def main():
    assert os.environ.get("WSL_DISTRO_NAME"), "Use the WSL project virtualenv"
    enrollment = read("evidence/history/chokepoint-people-enrollment.json")
    analysis = read("evidence/history/chokepoint-people-analysis.json")
    cloud = read("evidence/history/chokepoint-people-cloud.json")
    embedding = read("evidence/history/chokepoint-people-embedding-cloud.json")
    review = read("evidence/history/chokepoint-people-enrollment-review.json")
    deployment = read("evidence/ui-audit/enrollment-ui-deployment.json")
    server = read("evidence/content/server/verification.json")
    web = read("evidence/mobile-web/unit-verification.json")
    android = read("evidence/content/android/verification.json")
    ui = read("evidence/ui-audit/after.json")
    for proof in (enrollment, analysis, cloud, embedding, review, deployment, server, web):
        assert proof["pass"]
    assert enrollment["new_profiles"] == 29 and enrollment["accepted_stills"] == 58
    assert review["visually_reviewed_all_portrait_pairs"]
    assert len(cloud["profiles"]) == 29
    assert all(p["reference_available"] and p["active"] for p in cloud["profiles"])
    assert cloud["new_dataset_track_confirmations"] == 61
    assert cloud["current_facts"]["sampled_frames"] == 500
    assert cloud["current_facts"]["sessions"] == 40
    assert embedding["actual_embedding_api_calls"] == 1
    assert embedding["actual_llm_api_calls"] == embedding["verification_paid_api_calls"] == 0
    assert embedding["index_documents"] == 40 and embedding["previous_vectors_reused"] == 35
    assert web["tests"] == 76
    assert android["status"] == "passed" and android["sourceStable"]
    assert android["unitTests"]["passed"] and android["unitTests"]["tests"] == 40
    assert android["lint"]["passed"] and android["lint"]["errors"] == 0
    assert all(row["pass"] and row["composer_flow_pass"] for row in ui["results"])
    assert {row["size"] for row in ui["results"]} == {"small", "regular"}
    assert "Ran 245 tests" in (ROOT / "evidence/content/server/tests-coverage.txt").read_text()
    assert "Ran 15 tests" in (ROOT / "evidence/content/server/http-api-engine.txt").read_text()
    identity_log = (ROOT / "evidence/history/chokepoint-people-unit-tests.txt").read_text()
    assert "Ran 4 tests" in identity_log and "\nOK" in identity_log
    cases = []
    for case in analysis["cases"]:
        rows = read(f'evidence/private/cctv-walking/people/analysis/{case["camera"]}/groundtruth-check.json')
        correct_ids = {row["identity"] for row in rows if row["identity"]
                       and row["candidate"] == "chokepoint-" + row["identity"]
                       and row["track_id"] is not None}
        cases.append({key: case[key] for key in (
            "camera", "frames_analyzed", "face_detections", "scored_face_matches",
            "correct_candidates", "wrong_candidates", "unresolved_labeled_faces")}
                     | {"groundtruth_available": bool(case["groundtruth"]),
                        "correctly_linked_unique_ids": len(correct_ids)})
    assert [row["correctly_linked_unique_ids"] for row in cases[:3]] == [11, 25, 25]
    screenshots = []
    for name in ("production-people.jpg", "production-person.jpg", "production-comparison.jpg"):
        path = ROOT / "evidence/private/cctv-walking/people" / name
        raw = path.read_bytes()
        assert raw.startswith(b"\xff\xd8\xff")
        screenshots.append({"path": path.relative_to(ROOT).as_posix(),
                            "sha256": hashlib.sha256(raw).hexdigest()})
    proof = {
        "pass": True, "verified_utc": datetime.now(timezone.utc).isoformat(),
        "new_profiles": 29, "reference_stills": 58,
        "gallery_profiles_in_actual_analysis": enrollment["gallery_profiles"],
        "profiles_with_multiple_sources_including_candidates": sum(p["source_count"] >= 2 for p in cloud["profiles"]),
        "reanalyzed_existing_video_sources": 5, "new_original_video_sources": 0,
        "frames_analyzed": sum(row["frames_analyzed"] for row in cases),
        "face_detections_including_repeats": sum(row["face_detections"] for row in cases),
        "model_evaluation": cases,
        "accuracy_scope": "Only uniquely eye-coordinate-matched detected faces in annotated normal clips; crowd unscored",
        "dataset_concordant_track_reviews": 61,
        "new_observation_images": cloud["newly_created_images"],
        "production_facts": cloud["current_facts"],
        "existing_posts_preserved": cloud["existing_posts_preserved"],
        "existing_chats_preserved": cloud["existing_chats_preserved"],
        "production_release": deployment["release"],
        "production_people_and_comparison_visually_verified": True,
        "embedding_documents": embedding["index_documents"],
        "previous_vectors_reused": embedding["previous_vectors_reused"],
        "actual_embedding_api_calls": 1, "actual_llm_api_calls": 0,
        "embedding_usage": embedding["usage"],
        "photos_or_face_features_sent_to_embedding_api": False,
        "tests": {"WSL_Django": 245, "WSL_HTTP": 15, "WSL_identity_unit": 4,
                  "Windows_Node": 76, "Windows_Android": android["unitTests"],
                  "Android_UI_sizes": [row["size"] for row in ui["results"]]},
        "screenshots": screenshots,
    }
    target = ROOT / "evidence/history/chokepoint-people-summary.json"
    target.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: proof[key] for key in ("pass", "new_profiles", "frames_analyzed", "embedding_documents", "actual_embedding_api_calls")}), flush=True)


if __name__ == "__main__":
    main()
