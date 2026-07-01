from dataclasses import replace
from datetime import datetime, timezone

import requests

from src import candidate_pool, job_aggregator
from src.collectors import reddit_jobs
from src.job_collector_registry import get_collector


NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)


def post(title, body="", **extra):
    data = {
        "title": title,
        "body": body,
        "summary": body,
        "url": extra.pop("url", "https://www.reddit.com/r/WorkOnline/comments/1/job"),
        "created_at": extra.pop("created_at", "2026-06-20T00:00:00+00:00"),
        "published_at": extra.pop("published_at", "2026-06-20T00:00:00+00:00"),
        "subreddit": extra.pop("subreddit", "WorkOnline"),
        "author": extra.pop("author", "poster"),
    }
    data.update(extra)
    return data


class FakeResponse:
    def __init__(self, content=b"", payload=None, status_code=200, error=None):
        self.content = content
        self.payload = payload or {}
        self.status_code = status_code
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        if self.error:
            raise self.error
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def get(self, url, headers, timeout):
        self.urls.append(url)
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        return FakeResponse(status_code=404)


def rss_feed(entries):
    body = "\n".join(entries)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
{body}
</feed>""".encode("utf-8")


def rss_entry(title, content, url="https://www.reddit.com/r/WorkOnline/comments/1/job", author="poster"):
    return f"""
<entry>
  <title>{title}</title>
  <author><name>{author}</name></author>
  <link rel="alternate" href="{url}" />
  <updated>2026-06-20T00:00:00+00:00</updated>
  <content type="html">{content}</content>
</entry>
"""


def test_remote_data_entry_post_passes():
    item = post(
        "Remote data entry assistant needed",
        "Paid hourly online data entry task. Apply by email with resume. Clear spreadsheet work from home.",
    )

    assert reddit_jobs.rejection_reason(item, "remote data entry", now=NOW) == ""
    row = reddit_jobs.normalize_post(item, "remote data entry", now=NOW)

    assert row["source"] == "reddit"
    assert row["remote"] is True
    assert row["category"] == "ai_data"
    assert row["company"] == "WorkOnline"
    assert row["reddit_score"] >= 80


def test_ai_annotation_post_passes():
    item = post(
        "AI annotation remote contract",
        "Paid data annotation project. Apply via Google Form. Fully remote task evaluating LLM outputs.",
    )

    row = reddit_jobs.normalize_post(item, "AI annotation", now=NOW)

    assert reddit_jobs.rejection_reason(item, row["query"], now=NOW) == ""
    assert row["category"] == "ai_data"
    assert "+25 AI annotation/evaluator" in row["score_reason"]


def test_virtual_assistant_post_passes():
    item = post(
        "Virtual assistant remote operations role",
        "Freelance hourly admin operations work from home. Send CV by email for application.",
    )

    row = reddit_jobs.normalize_post(item, "virtual assistant", now=NOW)

    assert reddit_jobs.rejection_reason(item, row["query"], now=NOW) == ""
    assert row["category"] == "back_office_va"
    assert "hourly" in row["payment_signals"]


def test_ukrainian_russian_language_task_gets_bonus():
    ukrainian = post(
        "Ukrainian transcription remote task",
        "Paid weekly payment. Apply by email for language evaluator transcription.",
    )
    russian = post(
        "Russian language evaluator online",
        "Freelance compensation available worldwide. Application form included.",
        url="https://www.reddit.com/r/WorkOnline/comments/2/job",
    )

    ukrainian_row = reddit_jobs.normalize_post(ukrainian, "Ukrainian", now=NOW)
    russian_row = reddit_jobs.normalize_post(russian, "Russian", now=NOW)

    assert "ukrainian" in ukrainian_row["language_signals"]
    assert "russian" in russian_row["language_signals"]
    assert "+20 Ukrainian/Russian" in ukrainian_row["score_reason"]
    assert "+20 Ukrainian/Russian" in russian_row["score_reason"]


def test_crypto_investment_post_is_rejected():
    item = post(
        "Remote paid crypto assistant",
        "Investment trading bot work from home. Apply by email.",
    )

    assert reddit_jobs.rejection_reason(item, "paid task", now=NOW) == "scam_signal"


def test_telegram_only_post_is_rejected_or_heavily_penalized():
    item = post(
        "Remote data entry paid task",
        "Telegram only. Easy money for online data entry.",
    )

    row = reddit_jobs.normalize_post(item, "remote data entry", now=NOW)

    assert row["reddit_score"] < 40
    assert reddit_jobs.rejection_reason(item, row["query"], now=NOW) == "scam_signal"


def test_dm_only_vague_post_is_rejected_or_heavily_penalized():
    item = post(
        "Remote assistant needed",
        "DM me. Online task. Details later.",
    )

    row = reddit_jobs.normalize_post(item, "remote assistant", now=NOW)

    assert row["reddit_score"] <= 0
    assert reddit_jobs.rejection_reason(item, row["query"], now=NOW) == "vague_dm_only"


def test_unpaid_volunteer_post_is_rejected_or_heavily_penalized():
    item = post(
        "AI annotation remote volunteer",
        "Unpaid volunteer data annotation work from home for exposure.",
    )

    row = reddit_jobs.normalize_post(item, "AI annotation", now=NOW)

    assert row["reddit_score"] <= 0
    assert reddit_jobs.rejection_reason(item, row["query"], now=NOW) == "unpaid"


def test_old_post_is_penalized_or_excluded():
    old = post(
        "Remote web research assistant",
        "Paid hourly web research work from home. Apply by email.",
        created_at="2026-05-20T00:00:00+00:00",
        published_at="2026-05-20T00:00:00+00:00",
    )
    very_old = post(
        "Remote web research assistant",
        "Paid hourly web research work from home.",
        created_at="2026-02-01T00:00:00+00:00",
        published_at="2026-02-01T00:00:00+00:00",
    )

    old_row = reddit_jobs.normalize_post(old, "web research", now=NOW)

    assert "-20 old post" in old_row["score_reason"]
    assert reddit_jobs.rejection_reason(very_old, "web research", now=NOW) == "too_old"


def test_429_403_does_not_crash_collector(capsys):
    jobs = reddit_jobs.collect_jobs(
        reddit_limit=1,
        top=1,
        session=FakeSession([
            FakeResponse(status_code=429),
            FakeResponse(status_code=403),
        ]),
        subreddits=["WorkOnline"],
        queries=["remote data entry"],
    )

    assert jobs == []
    output = capsys.readouterr().out
    assert "Warning: Reddit RSS unavailable" in output
    assert "Warning: Reddit JSON unavailable" in output


def test_rss_parse_error_does_not_crash_collector(capsys):
    jobs = reddit_jobs.collect_jobs(
        reddit_limit=1,
        top=1,
        session=FakeSession([
            FakeResponse(content=b"<not xml"),
            FakeResponse(payload={"data": {"children": []}}),
        ]),
        subreddits=["WorkOnline"],
        queries=["remote data entry"],
    )

    assert jobs == []
    assert "Warning: Reddit RSS parse failed" in capsys.readouterr().out


def test_duplicate_posts_are_deduplicated():
    jobs = [
        reddit_jobs.normalize_post(post("Remote data entry", "Paid hourly data entry online. Apply by email."), "remote data entry"),
        reddit_jobs.normalize_post(post("Remote data entry", "Paid hourly data entry online. Apply by email."), "remote data entry"),
        reddit_jobs.normalize_post(
            post(
                "Remote data entry",
                "Paid hourly data entry online. Apply by email.",
                url="",
                author="poster",
                subreddit="WorkOnline",
            ),
            "remote data entry",
        ),
    ]

    assert len(reddit_jobs.deduplicate_jobs(jobs)) == 1


def test_rss_posts_are_collected_and_json_fallback_can_return_partial_results(capsys):
    good_entry = rss_entry(
        "Remote data entry assistant",
        "Paid hourly online data entry. Apply by email with resume.",
    )
    json_post = {
        "data": {
            "children": [
                {
                    "data": {
                        "title": "AI trainer remote",
                        "selftext": "Paid contract AI trainer role. Apply by email.",
                        "url": "https://www.reddit.com/r/WorkOnline/comments/2/job",
                        "created_utc": 1781913600,
                        "subreddit": "WorkOnline",
                        "author": "jsonposter",
                    }
                }
            ]
        }
    }

    jobs = reddit_jobs.collect_jobs(
        reddit_limit=1,
        top=10,
        session=FakeSession([
            FakeResponse(content=rss_feed([good_entry])),
            requests.exceptions.RequestException("rss down"),
            FakeResponse(payload=json_post),
        ]),
        subreddits=["WorkOnline"],
        queries=["remote data entry", "AI trainer"],
    )

    assert len(jobs) == 2
    assert {job["author"] for job in jobs} == {"poster", "jsonposter"}
    assert "Warning: Reddit RSS request failed" in capsys.readouterr().out


def test_reddit_rows_can_enter_candidate_pool(monkeypatch):
    row = reddit_jobs.normalize_post(
        post(
            "Remote data entry assistant",
            "Paid hourly online data entry. Apply by email with resume.",
        ),
        "remote data entry",
        now=NOW,
    )
    plugin = replace(
        get_collector("reddit"),
        callable=lambda **kwargs: [row],
    )

    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugin if name == "reddit" else None)

    jobs, stats, artifacts = job_aggregator.aggregate_jobs(
        ["reddit"],
        search_profile="remote",
        return_stats=True,
        return_artifacts=True,
        email_min_match=0,
    )

    assert jobs
    assert artifacts["candidate_pool"]
    pool_row = artifacts["candidate_pool"][0]
    assert pool_row["source"] == "reddit"
    assert pool_row["subreddit"] == "WorkOnline"
    assert pool_row["author"] == "poster"
    assert pool_row["score_reason"]
    assert pool_row["payment_signals"]
    assert ("Subreddit", "subreddit") in candidate_pool.POOL_FIELDS
    assert ("Author", "author") in candidate_pool.POOL_FIELDS
