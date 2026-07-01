from dataclasses import replace

import requests

from src import candidate_pool, job_aggregator
from src.collectors import github_jobs
from src.job_collector_registry import get_collector


def issue(title, body="", **extra):
    data = {
        "title": title,
        "body": body,
        "html_url": extra.pop("html_url", "https://github.com/acme/jobs/issues/1"),
        "repository_url": extra.pop("repository_url", "https://api.github.com/repos/acme/jobs"),
        "state": extra.pop("state", "open"),
        "created_at": extra.pop("created_at", "2026-06-01T00:00:00Z"),
        "labels": extra.pop("labels", []),
        "user": extra.pop("user", {"login": "acme"}),
    }
    data.update(extra)
    return data


class FakeResponse:
    def __init__(self, payload=None, status_code=200, error=None):
        self.payload = payload or {"items": []}
        self.status_code = status_code
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, response):
        self.response = response

    def get(self, *args, **kwargs):
        return self.response


def test_ai_annotator_remote_issue_passes():
    item = issue(
        "AI annotator needed remote",
        "Paid contract role. Apply by email for data annotation work from home.",
    )

    assert github_jobs.rejection_reason(item, 'is:issue "AI annotator" remote') == ""
    row = github_jobs.normalize_issue(item, 'is:issue "AI annotator" remote')

    assert row["source"] == "github"
    assert row["remote"] is True
    assert row["category"] == "ai_data"
    assert row["company"] == "acme"
    assert row["github_score"] >= 80


def test_virtual_assistant_remote_issue_passes():
    item = issue(
        "Virtual assistant remote operations support",
        "Freelance hourly role, worldwide. Application form included.",
    )

    row = github_jobs.normalize_issue(item, 'is:issue "virtual assistant" remote')

    assert github_jobs.rejection_reason(item, row["query"]) == ""
    assert row["category"] == "back_office_va"
    assert "hourly" in row["payment_signals"]


def test_senior_backend_engineer_issue_is_rejected():
    item = issue(
        "Senior software engineer remote",
        "Backend developer with Kubernetes and DevOps experience. Paid contract.",
    )

    assert github_jobs.rejection_reason(item, "is:issue remote") == "developer_heavy"


def test_help_wanted_without_job_payment_is_rejected():
    item = issue(
        "Help wanted remote",
        "Open source contribution for a feature request.",
    )

    assert github_jobs.rejection_reason(item, "is:issue remote") == "non_job_issue"


def test_ukrainian_russian_remote_task_gets_bonus():
    ukrainian = issue(
        "Ukrainian transcription remote task",
        "Paid weekly payment. Apply by email for language evaluator transcription.",
    )
    russian = issue(
        "Russian language evaluator remote",
        "Freelance compensation available. Application form included.",
        html_url="https://github.com/acme/jobs/issues/2",
    )

    ukrainian_row = github_jobs.normalize_issue(ukrainian, "is:issue Ukrainian remote")
    russian_row = github_jobs.normalize_issue(russian, "is:issue Russian remote")

    assert "ukrainian" in ukrainian_row["language_signals"]
    assert "russian" in russian_row["language_signals"]
    assert "+20 Ukrainian/Russian" in ukrainian_row["score_reason"]
    assert "+20 Ukrainian/Russian" in russian_row["score_reason"]


def test_unpaid_volunteer_task_is_rejected_or_heavily_penalized():
    item = issue(
        "AI annotator remote volunteer",
        "Unpaid volunteer data annotation work from home.",
    )

    row = github_jobs.normalize_issue(item, 'is:issue "AI annotator" remote')

    assert row["github_score"] <= 0
    assert github_jobs.rejection_reason(item, row["query"]) == "low_github_score"


def test_closed_issue_is_penalized_or_excluded():
    item = issue(
        "AI evaluator remote",
        "Paid contract. Apply by email.",
        state="closed",
    )

    row = github_jobs.normalize_issue(item, 'is:issue "AI evaluator" remote')

    assert "-20 closed issue" in row["score_reason"]


def test_rate_limit_does_not_crash_collector(capsys):
    jobs = github_jobs.collect_jobs(
        github_limit=1,
        top=1,
        session=FakeSession(FakeResponse(status_code=403)),
    )

    assert jobs == []
    assert "Warning: GitHub search rate-limited or blocked" in capsys.readouterr().out


def test_request_error_returns_partial_results(capsys):
    class PartialSession:
        def __init__(self):
            self.calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return FakeResponse({
                    "items": [
                        issue(
                            "AI trainer remote",
                            "Paid contract. Apply by email.",
                        )
                    ]
                })
            raise requests.exceptions.RequestException("network down")

    jobs = github_jobs.collect_jobs(github_limit=1, top=10, session=PartialSession())

    assert len(jobs) == 1
    assert "Warning: GitHub search failed" in capsys.readouterr().out


def test_github_rows_can_enter_candidate_pool(monkeypatch):
    row = github_jobs.normalize_issue(
        issue(
            "AI annotator remote",
            "Paid contract data annotation. Apply by email.",
        ),
        'is:issue "AI annotator" remote',
    )
    plugin = replace(
        get_collector("github"),
        callable=lambda **kwargs: [row],
    )

    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugin if name == "github" else None)

    jobs, stats, artifacts = job_aggregator.aggregate_jobs(
        ["github"],
        search_profile="remote",
        return_stats=True,
        return_artifacts=True,
        email_min_match=0,
    )

    assert jobs
    assert artifacts["candidate_pool"]
    pool_row = artifacts["candidate_pool"][0]
    assert pool_row["source"] == "github"
    assert pool_row["category"]
    assert pool_row["remote"] is True
    assert pool_row["score_reason"]
    assert pool_row["payment_signals"]
    assert ("Payment Signal", "payment_signals") in candidate_pool.POOL_FIELDS
