"""
The end-to-end journey, exactly as a candidate walks it:

    register -> upload resume -> analyse -> start interview -> answer every
    question -> finalise -> read the report -> get the roadmap -> tick a task

If this file passes, the product works. Everything else is detail.
"""

from __future__ import annotations

import io

STRONG_ANSWER = (
    "At my internship I owned the reporting API. It was averaging 480 milliseconds because "
    "every request did a sequential scan over 2 million rows. I ran EXPLAIN ANALYZE, saw the "
    "planner had stopped using the index, and added a composite index on tenant_id and "
    "created_at, then put a Redis cache in front of the aggregate with a 5 minute TTL. "
    "That took it to 120 milliseconds. I added pytest cases so a regression would be caught "
    "in CI. If I did it again I would measure before adding the cache."
)


def test_full_candidate_journey(client, auth, sample_resume_bytes):
    headers, user = auth

    # --- 1. upload ---------------------------------------------------------
    upload = client.post(
        "/upload-resume", headers=headers,
        files={"file": ("ananya.txt", io.BytesIO(sample_resume_bytes), "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    uploaded = upload.json()
    resume_id = uploaded["resume"]["id"]
    assert "React" in uploaded["detected_skills"]
    assert "FastAPI" in uploaded["detected_skills"]

    # --- 2. analyse --------------------------------------------------------
    analysis = client.post("/analyze-resume", headers=headers, json={
        "resume_id": resume_id,
        "role_key": "full-stack-developer",
        "job_description": "React, TypeScript, Node.js and PostgreSQL. Kubernetes a plus.",
    })
    assert analysis.status_code == 200, analysis.text
    ats = analysis.json()
    assert 0 <= ats["score"] <= 100
    assert ats["role_title"] == "Full Stack Developer"
    assert sum(part["max"] for part in ats["breakdown"]) == 100
    assert ats["review"]["one_line"]

    # --- 3. start the interview -------------------------------------------
    start = client.post("/generate-questions", headers=headers, json={
        "resume_id": resume_id, "role_key": "full-stack-developer",
        "company_key": "product-startup", "mode": "text", "count": 5, "coding_problems": 1,
    })
    assert start.status_code == 201, start.text
    started = start.json()
    interview_id = started["interview"]["id"]
    questions = started["questions"]
    assert len(questions) == 6  # 5 spoken + 1 coding
    assert started["engine"] == "bank"  # offline in tests, and the API says so

    # The mark scheme must not be handed to the candidate mid-interview.
    assert all("expected_points" not in q for q in questions)

    # --- 4. answer every question -----------------------------------------
    for question in questions:
        payload = {"question_id": question["id"], "evaluate_now": True}
        if question["category"] == "coding":
            payload["code"] = (
                "def two_sum(nums, target):\n"
                "    seen = {}\n"
                "    for i, n in enumerate(nums):\n"
                "        if target - n in seen:\n"
                "            return [seen[target - n], i]\n"
                "        seen[n] = i\n"
                "    return []\n"
            )
            payload["language"] = "python"
        else:
            payload["transcript"] = STRONG_ANSWER
            payload["duration_sec"] = 52

        response = client.post("/submit-answer", headers=headers, json=payload)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["answer"]["overall_score"] is not None
        assert body["total"] == 6

    # --- 5. finalise -------------------------------------------------------
    evaluate = client.post("/evaluate", headers=headers,
                           json={"interview_id": interview_id, "finalise": True})
    assert evaluate.status_code == 200, evaluate.text
    summary = evaluate.json()["summary"]
    assert summary["answered"] == 6
    assert 0 <= summary["overall"] <= 100
    assert len(summary["dimension_averages"]) == 5

    # --- 6. report ---------------------------------------------------------
    report = client.get("/report", headers=headers, params={"interview_id": interview_id}).json()
    assert report["overall_score"] == summary["overall"]
    assert len(report["questions"]) == 6
    # Now the mark scheme IS returned - that is the feedback.
    assert any(q["expected_points"] for q in report["questions"])
    assert all(q["transcript"] or q["code"] for q in report["questions"])

    # --- 7. roadmap --------------------------------------------------------
    roadmap = client.post("/roadmap", headers=headers,
                          json={"weeks": 6, "hours_per_week": 8}).json()
    assert roadmap["weeks"]
    assert roadmap["coach_note"]
    assert all(week["hours"] <= 8 for week in roadmap["weeks"])

    # --- 8. tick a task off ------------------------------------------------
    progress = client.patch(f"/roadmap/{roadmap['id']}/progress", headers=headers,
                            json={"task_key": "1-0", "done": True})
    assert progress.status_code == 200
    assert progress.json()["progress"]["1-0"] is True

    # --- 9. the dashboard reflects all of it -------------------------------
    dashboard = client.get("/dashboard", headers=headers).json()
    assert dashboard["resumes"] == 1
    assert dashboard["interviews_completed"] == 1
    assert dashboard["questions_answered"] == 6
    assert dashboard["latest_ats_score"] == ats["score"]
    assert dashboard["has_roadmap"] is True
    assert len(dashboard["score_trend"]) == 1


def test_generate_questions_without_a_resume_still_works(client, auth):
    headers, _ = auth
    response = client.post("/generate-questions", headers=headers,
                           json={"role_key": "data-analyst", "count": 4, "mode": "text"})
    assert response.status_code == 201
    assert len(response.json()["questions"]) == 4


def test_reloading_an_interview_returns_the_same_questions(client, auth):
    headers, _ = auth
    start = client.post("/generate-questions", headers=headers,
                        json={"role_key": "backend-developer", "count": 5, "mode": "text"}).json()
    interview_id = start["interview"]["id"]

    reloaded = client.get(f"/interviews/{interview_id}", headers=headers).json()
    assert [q["text"] for q in reloaded["questions"]] == [q["text"] for q in start["questions"]]


def test_resubmitting_an_answer_overwrites_rather_than_duplicates(client, auth):
    headers, _ = auth
    start = client.post("/generate-questions", headers=headers,
                        json={"role_key": "backend-developer", "count": 3, "mode": "text"}).json()
    question_id = start["questions"][0]["id"]

    first = client.post("/submit-answer", headers=headers,
                        json={"question_id": question_id, "transcript": "A short first attempt."})
    second = client.post("/submit-answer", headers=headers,
                         json={"question_id": question_id, "transcript": STRONG_ANSWER})

    assert first.json()["answered"] == second.json()["answered"] == 1
    assert second.json()["answer"]["overall_score"] > first.json()["answer"]["overall_score"]


def test_answers_can_be_banked_and_scored_at_the_end(client, auth):
    """evaluate_now=false is the slow-connection path: submit fast, score later."""
    headers, _ = auth
    start = client.post("/generate-questions", headers=headers,
                        json={"role_key": "backend-developer", "count": 3, "mode": "text"}).json()

    for question in start["questions"]:
        response = client.post("/submit-answer", headers=headers, json={
            "question_id": question["id"], "transcript": STRONG_ANSWER, "evaluate_now": False})
        assert response.json()["answer"]["overall_score"] is None

    summary = client.post("/evaluate", headers=headers, json={
        "interview_id": start["interview"]["id"], "finalise": True}).json()["summary"]
    assert summary["answered"] == 3
    assert summary["overall"] > 0


def test_spoken_answers_fall_back_to_the_browser_transcript(client, auth):
    """STT_PROVIDER is 'none' in tests, so this exercises the tier-3 path that
    keeps voice interviews working on a machine with no Whisper installed."""
    headers, _ = auth
    start = client.post("/generate-questions", headers=headers,
                        json={"role_key": "backend-developer", "count": 2, "mode": "voice"}).json()

    response = client.post(
        "/submit-answer/audio", headers=headers,
        data={"question_id": start["questions"][0]["id"],
              "browser_transcript": STRONG_ANSWER, "duration_sec": 50},
        files={"audio": ("answer.webm", b"\x1a\x45\xdf\xa3fake-audio", "audio/webm")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer"]["transcript_source"] == "browser-web-speech"
    assert body["answer"]["overall_score"] > 0
    assert body["next_question"]["index"] == 2


def test_roadmap_requires_an_analysed_resume_and_says_so(client, auth):
    headers, _ = auth
    response = client.get("/roadmap", headers=headers)
    assert response.status_code == 409
    assert "Analyse a resume first" in response.json()["detail"]


def test_report_before_any_interview_is_a_clear_404(client, auth):
    headers, _ = auth
    response = client.get("/report", headers=headers)
    assert response.status_code == 404
    assert "No interviews yet" in response.json()["detail"]


def test_rejects_an_unsupported_resume_format(client, auth):
    headers, _ = auth
    response = client.post("/upload-resume", headers=headers,
                           files={"file": ("resume.pages", b"junk", "application/octet-stream")})
    assert response.status_code == 415
    assert "PDF" in response.json()["detail"]


def test_rejects_an_empty_upload(client, auth):
    headers, _ = auth
    response = client.post("/upload-resume", headers=headers,
                           files={"file": ("resume.txt", b"", "text/plain")})
    assert response.status_code == 400


def test_health_reports_which_engines_are_live(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["llm"]["provider"] == "offline"   # honest about running on fallbacks
    assert body["database"] == "sqlite"


def test_roles_and_companies_are_available_for_the_setup_screen(client):
    roles = client.get("/roles").json()
    assert any(role["key"] == "full-stack-developer" for role in roles["roles"])
    assert roles["experience_levels"]

    companies = client.get("/companies").json()
    assert any(company["key"] == "faang" for company in companies["companies"])
