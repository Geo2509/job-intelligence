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
    assert "⭐⭐⭐⭐⭐ Strong match" in body
    assert "<strong>Match:</strong> 95" in body
    assert "<strong>Student:</strong> 90" in body
    assert "<strong>Candidate:</strong> 100" in body
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
    assert "<strong>Recommended to apply today:</strong> 2" in body
    assert "⭐⭐⭐⭐⭐ Strong match" in body
    assert "⭐⭐⭐⭐ Good match" in body
    assert "⭐⭐⭐ Consider" in body


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
