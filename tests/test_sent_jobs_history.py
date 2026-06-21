import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from src.main import (
    job_history_key,
    load_sent_jobs_history,
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
        history = {job_history_key(sent_job): {"sent_at": "2026-06-21"}}

        found_rows, rows_to_send, skipped = unsent_email_rows(FakeTopJobs([new_job]), history)

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
        history = {job_history_key(sent_job): {"sent_at": "2026-06-21"}}

        found_rows, rows_to_send, skipped = unsent_email_rows(FakeTopJobs([new_job]), history)

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
        history = {job_history_key(sent_job): {"sent_at": "2026-06-21"}}

        _, rows_to_send, skipped = unsent_email_rows(FakeTopJobs([new_job]), history)

        self.assertEqual(1, skipped)
        self.assertEqual([], rows_to_send)

    def test_history_ttl_removes_entries_older_than_90_days(self):
        now = datetime(2026, 6, 21, tzinfo=ZoneInfo("Europe/Rome"))
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "sent_jobs_history.json"
            history_path.write_text(
                json.dumps(
                    {
                        "recent": {"sent_at": "2026-04-01"},
                        "old": {"sent_at": "2026-03-01"},
                    }
                ),
                encoding="utf-8",
            )

            history = load_sent_jobs_history(history_path, now=now, ttl_days=90)
            save_sent_jobs_history(history, history_path)
            saved_history = json.loads(history_path.read_text(encoding="utf-8"))

        self.assertIn("recent", saved_history)
        self.assertNotIn("old", saved_history)

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
                json.dumps({job_history_key(sent_job): {"sent_at": "2026-06-20"}}),
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


if __name__ == "__main__":
    unittest.main()
