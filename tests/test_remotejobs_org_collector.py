import requests

import remotejobs_org_collector as collector
from src import main as legacy_main


class FakeResponse:
    def __init__(self, payload=None, status_code=200, error=None):
        self.payload = payload or {}
        self.status_code = status_code
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


def test_collect_jobs_returns_empty_frame_when_api_fails(monkeypatch, capsys):
    error = requests.exceptions.HTTPError("500 Server Error")

    def fake_get(url, params, timeout):
        return FakeResponse(status_code=500, error=error)

    monkeypatch.setattr(collector.requests, "get", fake_get)

    df = collector.collect_jobs()

    assert df.empty
    assert df.columns.tolist() == collector.COLUMNS
    output = capsys.readouterr().out
    assert "Warning: remotejobs.org API request failed" in output
    assert "https://remotejobs.org/api/v1/jobs?limit=50&offset=0" in output
    assert "500 Server Error" in output


def test_collect_jobs_maps_successful_response(monkeypatch):
    payload = {
        "data": [
            {
                "title": "Data Analyst",
                "company": {"name": "Acme"},
                "category": {"name": "Data"},
                "location": "Remote",
                "salary_min": 100,
                "salary_max": 200,
                "salary_text": "$100-$200",
                "type": "full-time",
                "url": "https://remotejobs.org/jobs/1",
                "posted_at": "2026-07-01",
                "description": "Analyze data",
            }
        ],
        "pagination": {"has_more": False},
    }

    def fake_get(url, params, timeout):
        return FakeResponse(payload=payload)

    monkeypatch.setattr(collector.requests, "get", fake_get)

    df = collector.collect_jobs()

    assert df.to_dict("records") == [
        {
            "source": "remotejobs_org",
            "title": "Data Analyst",
            "company": "Acme",
            "category": "Data",
            "location": "Remote",
            "salary_min": 100,
            "salary_max": 200,
            "salary_text": "$100-$200",
            "job_type": "full-time",
            "url": "https://remotejobs.org/jobs/1",
            "posted_at": "2026-07-01",
            "description": "Analyze data",
        }
    ]


def test_legacy_run_collectors_continues_after_remotejobs_empty_csv(monkeypatch, tmp_path):
    calls = []

    def fake_run_script(script, env):
        calls.append(script)
        if script == "remotejobs_org_collector.py":
            collector.empty_jobs_frame().to_csv(tmp_path / "remotejobs_org_jobs.csv", index=False)
        else:
            (tmp_path / "next_jobs.csv").write_text("title,url\nNext,https://example.com\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        legacy_main,
        "COLLECTORS",
        [
            ("remotejobs_org", "remotejobs_org_collector.py"),
            ("next", "next_collector.py"),
        ],
    )
    monkeypatch.setattr(
        legacy_main,
        "COLLECTOR_OUTPUT_FILES",
        {
            "remotejobs_org": "remotejobs_org_jobs.csv",
            "next": "next_jobs.csv",
        },
    )
    monkeypatch.setattr(legacy_main, "run_script", fake_run_script)

    counts = legacy_main.run_collectors("configs/queries.yaml")

    assert calls == ["remotejobs_org_collector.py", "next_collector.py"]
    assert counts == {"remotejobs_org": 0, "next": 1}
