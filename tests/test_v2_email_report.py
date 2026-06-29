import json
from email import message_from_string
from pathlib import Path
from unittest.mock import patch

from src import v2_email_report


def job(title, **extra):
    data = {
        "title": title,
        "company": extra.pop("company", "Acme"),
        "location": extra.pop("location", "Napoli"),
        "score": extra.pop("score", 75),
        "category": extra.pop("category", "general"),
        "source": extra.pop("source", "duckduckgo"),
        "url": extra.pop("url", "https://example.com/job"),
        "query": extra.pop("query", ""),
        "remote": extra.pop("remote", False),
        "remote_reason": extra.pop("remote_reason", "none"),
        "part_time": extra.pop("part_time", False),
        "priority_bucket": extra.pop("priority_bucket", "other"),
        "student_score": extra.pop("student_score", 90),
        "candidate_score": extra.pop("candidate_score", 100),
        "match_score": extra.pop("match_score", 95),
        "location_fit": extra.pop("location_fit", "allowed_local"),
    }
    data.update(extra)
    return data


def write_jobs(tmp_path, jobs):
    path = Path(tmp_path) / "v2_jobs.json"
    path.write_text(json.dumps(jobs), encoding="utf-8")
    return path


def test_grouping_by_blocks():
    jobs = [
        job("Back office part-time", priority_bucket="campania_part_time"),
        job("Hotel receptionist"),
        job("Addetto pulizie", category="cleaning"),
        job("Tecnico manutenzione"),
        job("Magazziniere GDO"),
        job("Remote AI data annotator", remote=True),
        job("Generic role"),
    ]

    groups = v2_email_report.grouped_jobs(jobs)

    assert groups["Campania part-time"][0]["title"] == "Back office part-time"
    assert groups["Hospitality / Hotel / Restaurant"][0]["title"] == "Hotel receptionist"
    assert groups["Cleaning / Pulizie"][0]["title"] == "Addetto pulizie"
    assert groups["Maintenance / Manutenzione"][0]["title"] == "Tecnico manutenzione"
    assert groups["Warehouse / GDO"][0]["title"] == "Magazziniere GDO"
    assert groups["Remote / Data / AI"][0]["title"] == "Remote AI data annotator"
    assert groups["Other"][0]["title"] == "Generic role"


def test_empty_list_is_not_sent(tmp_path, capsys):
    input_path = write_jobs(tmp_path, [])

    with patch("src.v2_email_report.send_html_email") as send_html_email:
        was_sent = v2_email_report.send_v2_email_report(input_path)

    assert was_sent is False
    send_html_email.assert_not_called()
    assert "No V2 jobs to email" in capsys.readouterr().out


def test_top_limit_is_applied(tmp_path):
    input_path = write_jobs(
        tmp_path,
        [
            job("First", url="https://example.com/1"),
            job("Second", url="https://example.com/2"),
        ],
    )

    with patch.dict(
        "os.environ",
        {
            "EMAIL_ENABLED": "true",
            "EMAIL_SMTP_HOST": "smtp.example.com",
            "EMAIL_SMTP_PORT": "587",
            "EMAIL_SMTP_USER": "user",
            "EMAIL_SMTP_PASSWORD": "password",
            "EMAIL_FROM": "from@example.com",
            "EMAIL_TO": "to@example.com",
        },
        clear=False,
    ), patch("src.v2_email_report.send_html_email") as send_html_email:
        was_sent = v2_email_report.send_v2_email_report(input_path, top=1)

    assert was_sent is True
    body = send_html_email.call_args.args[1]
    assert "First" in body
    assert "Second" not in body


def test_top_limit_is_applied_after_match_sort(tmp_path):
    input_path = write_jobs(
        tmp_path,
        [
            job("Lower match", match_score=70, student_score=99, candidate_score=99),
            job("Higher match", match_score=95, student_score=80, candidate_score=80),
        ],
    )

    with patch.dict(
        "os.environ",
        {
            "EMAIL_ENABLED": "true",
            "EMAIL_SMTP_HOST": "smtp.example.com",
            "EMAIL_SMTP_PORT": "587",
            "EMAIL_SMTP_USER": "user",
            "EMAIL_SMTP_PASSWORD": "password",
            "EMAIL_FROM": "from@example.com",
            "EMAIL_TO": "to@example.com",
        },
        clear=False,
    ), patch("src.v2_email_report.send_html_email") as send_html_email:
        was_sent = v2_email_report.send_v2_email_report(input_path, top=1)

    assert was_sent is True
    body = send_html_email.call_args.args[1]
    assert "Higher match" in body
    assert "Lower match" not in body


def test_email_preserves_selection_priority_before_match_sort():
    body = v2_email_report.build_email_html([
        job("Never sent higher", match_score=100, selection_reason="NEVER_SENT_FILL"),
        job("Fresh lower", match_score=70, selection_reason="NEW"),
    ])

    assert body.index("Fresh lower") < body.index("Never sent higher")
    assert "<strong>Selection:</strong> NEW" in body
    assert "<strong>Selection:</strong> NEVER_SENT_FILL" in body


def test_email_body_does_not_include_seen_status_when_seen_jobs_are_not_selected():
    body = v2_email_report.build_email_html([
        job("Fresh lower", match_score=70, history_status="NEW", selection_reason="NEW"),
        job("Never sent higher", match_score=100, history_status="ARCHIVED", selection_reason="NEVER_SENT_FILL"),
    ])

    assert "<strong>Status:</strong> SEEN" not in body
    assert "Fresh lower" in body
    assert "Never sent higher" in body


def test_email_body_shows_days_since_last_sent():
    body = v2_email_report.build_email_html([
        job(
            "Old resurfaced",
            history_status="RESURFACED",
            selection_reason="RESURFACED",
            days_since_last_sent=7,
        ),
    ])

    assert "<strong>Status:</strong> ↩️ RESURFACED" in body
    assert "<strong>Selection:</strong> RESURFACED" in body
    assert "<strong>Days since last sent:</strong> 7" in body


def test_email_report_loads_only_selected_jobs_from_wide_export(tmp_path, monkeypatch):
    input_path = tmp_path / "v2_jobs.json"
    input_path.write_text(
        json.dumps(
            [
                job("Selected", selection_rejection_reason="selected"),
                job("Export only", selection_rejection_reason="not_selected_due_to_limit"),
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("EMAIL_ENABLED", "false")

    jobs = v2_email_report.email_selected_jobs(v2_email_report.load_jobs(input_path))

    assert [item["title"] for item in jobs] == ["Selected"]


def test_email_body_contains_required_job_fields():
    body = v2_email_report.build_email_html(
        [
            job(
                "Data Entry Napoli",
                score=91,
                source="indeed",
                url="https://example.com/data-entry",
                location_fit="allowed_local",
            )
        ]
    )

    assert "Data Entry Napoli" in body
    assert "https://example.com/data-entry" in body
    assert "★★★★★ Apply today" in body
    assert "Match: 95 | Student: 90 | Candidate: 100" in body
    assert "<strong>Remote:</strong> False" in body
    assert "<strong>Remote reason:</strong> none" not in body
    assert "<strong>Location fit:</strong> allowed_local" in body
    assert "<strong>Source:</strong> indeed" in body
    assert "<strong>Category:</strong> general" in body
    assert "91" in body
    assert "indeed" in body


def test_email_body_contains_summary_metrics():
    body = v2_email_report.build_email_html(
        [
            job("Strong", match_score=91),
            job("Good", match_score=80),
            job("Consider", match_score=79),
        ]
    )

    assert "<strong>Total jobs in email:</strong> 3" in body
    assert "<strong>Top match score:</strong> 91" in body
    assert "<strong>Recommended to apply today:</strong> 3" in body
    assert "★★★★★ Apply today" in body


def test_email_body_contains_collector_health():
    body = v2_email_report.build_email_html(
        [job("Data Entry Napoli")],
        run_stats={
            "collector_health": [
                {
                    "collector": "gigroup",
                    "collector_health_status": "healthy",
                    "new": 37,
                    "updated": 0,
                    "seen": 0,
                    "resurfaced": 0,
                    "email": 37,
                    "real_jobs": 37,
                    "candidate_pool": 37,
                },
                {
                    "collector": "indeed",
                    "collector_health_status": "needs_detail_extraction",
                    "real_jobs": 0,
                },
            ]
        },
    )

    assert "Collector Health" in body
    assert "<strong>gigroup</strong> (healthy) - 37 email / 37 real jobs / 37 candidate pool" in body
    assert "<strong>indeed</strong> (needs_detail_extraction) - 0 real jobs" in body


def test_email_action_plan_block():
    body = v2_email_report.build_email_html(
        [
            job("Apply", match_score=80, location_fit="allowed_local"),
            job("Watch", match_score=50, location_fit="unknown"),
        ]
    )

    assert "Today's Action Plan" in body
    assert "<strong>Apply today:</strong>" in body
    assert "<strong>Watch:</strong>" in body
    assert "<strong>Best match:</strong> 80" in body


def test_email_hides_empty_fields():
    body = v2_email_report.build_email_html(
        [
            job(
                "No company",
                company="",
                salary_text="",
                salary="",
            )
        ]
    )

    assert "<strong>Company:</strong>" not in body
    assert "<strong>Salary:</strong>" not in body


def test_recommendation_level_apply_today():
    level = v2_email_report.recommendation_level(
        job("Back Office Napoli", match_score=75, location_fit="allowed_local")
    )

    assert level == "apply_today"


def test_recommended_cv_data_entry():
    cv = v2_email_report.recommended_cv(
        job("Data Entry Excel", category="data_entry")
    )

    assert cv in {"Data Entry CV", "Back Office CV"}


def test_recommended_cv_ai():
    cv = v2_email_report.recommended_cv(
        job("AI trainer data annotation", category="ai_annotation", remote=True)
    )

    assert cv == "AI / Data Annotation CV"


def test_empty_block_explains_reason():
    body = v2_email_report.build_email_html(
        [job("Remote AI data annotator", remote=True)],
        run_stats={
            "candidate_pool_jobs": 12,
            "seen_skipped": 3,
            "removed_far": 2,
            "collector_stats": [
                {
                    "collector": "gigroup",
                    "collected": 20,
                    "after_cleaner": 15,
                    "history_seen": 4,
                }
            ],
        },
    )

    assert "No jobs in this block." not in body
    assert "No new jobs selected." in body
    assert "Found in candidate pool: 12" in body
    assert "Rejected by history:" in body


def test_email_body_contains_history_status_label():
    body = v2_email_report.build_email_html([
        job("Fresh job", history_status="NEW")
    ])

    assert "🔥 NEW" in body


def test_subject_is_correct(tmp_path):
    input_path = write_jobs(tmp_path, [job("Data Entry Napoli")])

    with patch.dict(
        "os.environ",
        {
            "EMAIL_ENABLED": "true",
            "EMAIL_SMTP_HOST": "smtp.example.com",
            "EMAIL_SMTP_PORT": "587",
            "EMAIL_SMTP_USER": "user",
            "EMAIL_SMTP_PASSWORD": "password",
            "EMAIL_FROM": "from@example.com",
            "EMAIL_TO": "to@example.com",
        },
        clear=False,
    ), patch("src.v2_email_report.smtplib.SMTP") as smtp:
        was_sent = v2_email_report.send_v2_email_report(input_path)

    assert was_sent is True
    sent_message = smtp.return_value.__enter__.return_value.sendmail.call_args.args[2]
    parsed = message_from_string(sent_message)
    assert parsed["Subject"] == v2_email_report.SUBJECT
