import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from src.main import (
    build_email_html,
    job_history_key,
    load_sent_jobs_history,
    remote_content_hash,
    save_sent_jobs_history,
    send_email_report,
    unsent_email_rows,
)


class FakeTopJobs:
    def __init__(self, rows):
        self._rows = rows
        self.empty = not rows

    def head(self, limit):
        return FakeTopJobs(self._rows[:limit])

    def to_dict(self, orient):
        if orient != "records":
            raise ValueError(f"Unsupported orient: {orient}")
        return list(self._rows)


class SentJobsHistoryTest(unittest.TestCase):
    def test_same_url_is_skipped(self):
        sent_job = {"url": "https://example.com/jobs/123"}
        new_job = {"url": "https://example.com/jobs/123/"}
        history = {
            job_history_key(sent_job): {
                "sent_at": "2026-06-21",
                "content_hash": remote_content_hash(new_job),
            }
        }

        found_rows, rows_to_send, skipped = unsent_email_rows(
            FakeTopJobs([new_job]),
            history,
            now=datetime(2026, 6, 22, tzinfo=ZoneInfo("Europe/Rome")),
        )

        self.assertEqual(1, len(found_rows))
        self.assertEqual(1, skipped)
        self.assertEqual([], rows_to_send)

    def test_url_with_tracking_params_is_same_job(self):
        sent_job = {
            "url": (
                "https://Example.com/jobs/123?"
                "utm_source=newsletter&utm_campaign=x&fbclid=fb&gclid=google&ref=feed"
            )
        }
        new_job = {
            "job_url": "https://example.com/jobs/123/?ref=feed&utm_medium=email&utm_term=data",
            "title": "Operations Analyst",
        }
        history = {
            job_history_key(sent_job): {
                "sent_at": "2026-06-21",
                "content_hash": remote_content_hash(new_job),
            }
        }

        found_rows, rows_to_send, skipped = unsent_email_rows(
            FakeTopJobs([new_job]),
            history,
            now=datetime(2026, 6, 22, tzinfo=ZoneInfo("Europe/Rome")),
        )

        self.assertEqual(1, len(found_rows))
        self.assertEqual(1, skipped)
        self.assertEqual([], rows_to_send)

    def test_same_title_company_location_is_skipped_without_url(self):
        sent_job = {
            "title": "Data Operations Analyst",
            "company": "Acme",
            "location": "Remote",
        }
        new_job = {
            "title": "DATA OPERATIONS ANALYST",
            "company": "ACME",
            "location": "REMOTE",
        }
        history = {
            job_history_key(sent_job): {
                "sent_at": "2026-06-21",
                "content_hash": remote_content_hash(new_job),
            }
        }

        _, rows_to_send, skipped = unsent_email_rows(
            FakeTopJobs([new_job]),
            history,
            now=datetime(2026, 6, 22, tzinfo=ZoneInfo("Europe/Rome")),
        )

        self.assertEqual(1, skipped)
        self.assertEqual([], rows_to_send)

    def test_history_ttl_removes_entries_older_than_90_days(self):
        now = datetime(2026, 6, 21, tzinfo=ZoneInfo("Europe/Rome"))
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "sent_jobs_history.json"
            history_path.write_text(
                json.dumps(
                    {
                        "recent": {"sent_at": "2026-04-01", "content_hash": "abc"},
                        "old": {"sent_at": "2026-03-01", "content_hash": "def"},
                    }
                ),
                encoding="utf-8",
            )

            history = load_sent_jobs_history(history_path, now=now, ttl_days=90)
            save_sent_jobs_history(history, history_path)
            saved_history = json.loads(history_path.read_text(encoding="utf-8"))

        self.assertIn("recent", saved_history)
        self.assertEqual("abc", saved_history["recent"]["content_hash"])
        self.assertNotIn("old", saved_history)

    def test_all_seen_jobs_with_fallback_style_selection_send_zero_by_default(self):
        now = datetime(2026, 6, 22, tzinfo=ZoneInfo("Europe/Rome"))
        rows = [
            {"url": f"https://example.com/jobs/{index}", "title": f"Seen {index}", "job_score": 100 - index}
            for index in range(50)
        ]
        history = {
            job_history_key(row): {
                "sent_at": "2026-06-21",
                "content_hash": remote_content_hash(row),
            }
            for row in rows
        }

        _, rows_to_send, skipped = unsent_email_rows(FakeTopJobs(rows), history, send_limit=20, now=now)

        self.assertEqual([], rows_to_send)
        self.assertEqual(50, skipped)

    def test_seen_high_score_is_skipped_for_never_sent_lower_score(self):
        seen_job = {"url": "https://example.com/jobs/seen", "title": "Seen high", "job_score": 100}
        new_job = {"url": "https://example.com/jobs/new", "title": "Never sent lower", "job_score": 70}
        history = {
            job_history_key(seen_job): {
                "sent_at": "2026-06-21",
                "content_hash": remote_content_hash(seen_job),
            }
        }

        _, rows_to_send, skipped = unsent_email_rows(
            FakeTopJobs([seen_job, new_job]),
            history,
            now=datetime(2026, 6, 22, tzinfo=ZoneInfo("Europe/Rome")),
        )

        self.assertEqual(1, skipped)
        self.assertEqual(["Never sent lower"], [row["title"] for row in rows_to_send])
        self.assertEqual("NEW", rows_to_send[0]["history_status"])

    def test_seen_can_be_selected_only_when_include_seen_true(self):
        seen_job = {"url": "https://example.com/jobs/seen", "title": "Seen high", "job_score": 100}
        history = {
            job_history_key(seen_job): {
                "sent_at": "2026-06-21",
                "content_hash": remote_content_hash(seen_job),
            }
        }

        _, rows_without_flag, _ = unsent_email_rows(
            FakeTopJobs([seen_job]),
            history,
            now=datetime(2026, 6, 22, tzinfo=ZoneInfo("Europe/Rome")),
        )
        _, rows_with_flag, _ = unsent_email_rows(
            FakeTopJobs([seen_job]),
            history,
            include_seen=True,
            now=datetime(2026, 6, 22, tzinfo=ZoneInfo("Europe/Rome")),
        )

        self.assertEqual([], rows_without_flag)
        self.assertEqual(["Seen high"], [row["title"] for row in rows_with_flag])
        self.assertEqual("SEEN", rows_with_flag[0]["history_status"])

    def test_seen_resurfaces_after_rotation_days(self):
        seen_job = {"url": "https://example.com/jobs/seen", "title": "Seen old", "job_score": 100}
        history = {
            job_history_key(seen_job): {
                "sent_at": "2026-06-20",
                "content_hash": remote_content_hash(seen_job),
            }
        }

        _, rows_to_send, skipped = unsent_email_rows(
            FakeTopJobs([seen_job]),
            history,
            rotation_days=7,
            now=datetime(2026, 6, 27, tzinfo=ZoneInfo("Europe/Rome")),
        )

        self.assertEqual(0, skipped)
        self.assertEqual(["Seen old"], [row["title"] for row in rows_to_send])
        self.assertEqual("RESURFACED", rows_to_send[0]["history_status"])
        self.assertEqual("RESURFACED", rows_to_send[0]["selection_reason"])
        self.assertEqual("selected", rows_to_send[0]["selection_rejection_reason"])
        self.assertEqual(7, rows_to_send[0]["days_since_last_sent"])
        self.assertTrue(rows_to_send[0]["rotation_eligible"])

    def test_changed_seen_job_is_selected_as_updated(self):
        old_job = {
            "url": "https://example.com/jobs/updated",
            "title": "Remote Analyst",
            "description": "Old description",
        }
        changed_job = {
            "url": "https://example.com/jobs/updated",
            "title": "Remote Analyst",
            "description": "New description",
        }
        history = {
            job_history_key(old_job): {
                "sent_at": "2026-06-21",
                "content_hash": remote_content_hash(old_job),
            }
        }

        _, rows_to_send, skipped = unsent_email_rows(FakeTopJobs([changed_job]), history)

        self.assertEqual(0, skipped)
        self.assertEqual(["Remote Analyst"], [row["title"] for row in rows_to_send])
        self.assertEqual("UPDATED", rows_to_send[0]["history_status"])

    def test_remote_email_body_shows_rotation_fields(self):
        run_started = datetime(2026, 6, 27, tzinfo=ZoneInfo("Europe/Rome"))
        body = build_email_html(
            run_started,
            {},
            {
                "collected": 1,
                "after_deduplication": 1,
                "after_filtering": 1,
                "after_scoring_threshold": 1,
                "top_jobs_emailed": 1,
                "priority_counts": {"HIGH": 1, "MEDIUM": 0, "LOW": 0},
                "top_jobs_score_stats": {"min": 500, "max": 500, "average": 500},
            },
            email_rows=[
                {
                    "title": "Remote Analyst",
                    "job_score": 500,
                    "source": "remote",
                    "apply_priority": "HIGH",
                    "history_status": "RESURFACED",
                    "selection_reason": "RESURFACED",
                    "days_since_last_sent": 7,
                    "url": "https://example.com/jobs/remote",
                }
            ],
        )

        self.assertIn("<strong>Status:</strong> RESURFACED", body)
        self.assertIn("<strong>Selection:</strong> RESURFACED", body)
        self.assertIn("<strong>Days since last sent:</strong> 7", body)

    def test_remote_email_uses_dynamic_jobs_sent_heading(self):
        run_started = datetime(2026, 6, 27, tzinfo=ZoneInfo("Europe/Rome"))
        body = build_email_html(
            run_started,
            {},
            {
                "collected": 3,
                "after_deduplication": 3,
                "after_filtering": 3,
                "after_scoring_threshold": 3,
                "top_jobs_emailed": 3,
                "priority_counts": {"HIGH": 3, "MEDIUM": 0, "LOW": 0},
                "top_jobs_score_stats": {"min": 500, "max": 590, "average": 550},
            },
            email_rows=[
                {
                    "title": f"Remote Ukrainian Specialist {index}",
                    "job_score": 500 + index,
                    "source": "duckduckgo",
                    "apply_priority": "HIGH",
                    "url": f"https://example.com/jobs/{index}",
                    "remote_match_summary": ["Remote", "Ukrainian language"],
                }
                for index in range(3)
            ],
            email_stats={
                "found_total": 50,
                "skipped_already_sent": 47,
                "quality_rejected": 0,
                "rejected_search_pages": 0,
                "rejected_language_mismatch": 0,
                "rejected_low_quality": 0,
                "sent_total": 3,
            },
        )

        self.assertIn("Jobs sent today: 3", body)
        self.assertNotIn("Top 20 jobs", body)
        self.assertIn("Matched because:", body)
        self.assertNotIn("<strong>Reasons:</strong>", body)

    def test_email_is_not_sent_when_no_new_jobs(self):
        run_started = datetime(2026, 6, 21, tzinfo=ZoneInfo("Europe/Rome"))
        sent_job = {
            "url": "https://example.com/jobs/123",
            "title": "Data Analyst",
        }
        scoring_result = {
            "top_jobs": FakeTopJobs([sent_job]),
            "top_jobs_emailed": 1,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "sent_jobs_history.json"
            history_path.write_text(
                json.dumps(
                    {
                        job_history_key(sent_job): {
                            "sent_at": "2026-06-20",
                            "content_hash": remote_content_hash(sent_job),
                        }
                    }
                ),
                encoding="utf-8",
            )
            with patch("src.main.SENT_JOBS_HISTORY_PATH", history_path), patch.dict(
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
            ), patch("src.main.smtplib.SMTP") as smtp:
                was_sent = send_email_report(run_started, {}, scoring_result)

        self.assertFalse(was_sent)
        smtp.assert_not_called()

    def test_rejected_remote_email_jobs_are_not_added_to_history(self):
        run_started = datetime(2026, 6, 21, tzinfo=ZoneInfo("Europe/Rome"))
        rejected_job = {
            "url": "https://www.indeed.com/jobs?q=data+annotation+remote",
            "title": "Top 97 Data Annotation Remote Jobs (Hiring Now) | Indeed.com",
            "description": "Remote jobs found.",
            "job_score": 700,
            "apply_priority": "HIGH",
            "source": "duckduckgo",
        }
        accepted_job = {
            "url": "https://example.com/jobs/ukrainian-specialist",
            "title": "Ukrainian Language Specialist",
            "description": "Remote data annotation role.",
            "job_score": 690,
            "apply_priority": "HIGH",
            "source": "duckduckgo",
        }
        scoring_result = {
            "top_jobs": FakeTopJobs([rejected_job, accepted_job]),
            "collected": 2,
            "after_deduplication": 2,
            "after_filtering": 2,
            "after_scoring_threshold": 2,
            "top_jobs_emailed": 2,
            "priority_counts": {"HIGH": 2, "MEDIUM": 0, "LOW": 0},
            "top_jobs_score_stats": {"min": 690, "max": 700, "average": 695},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "sent_jobs_history.json"
            with patch("src.main.SENT_JOBS_HISTORY_PATH", history_path), patch.dict(
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
            ), patch("src.main.smtplib.SMTP"):
                was_sent = send_email_report(run_started, {}, scoring_result)

            saved_history = json.loads(history_path.read_text(encoding="utf-8"))

        self.assertTrue(was_sent)
        self.assertIn(job_history_key(accepted_job), saved_history)
        self.assertNotIn(job_history_key(rejected_job), saved_history)


if __name__ == "__main__":
    unittest.main()
