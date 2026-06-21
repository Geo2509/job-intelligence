import json
from urllib.parse import parse_qs, urlsplit

from src.collectors import indeed_jobs
from src.job_matching import deduplicate_jobs, is_bad_job


def test_build_indeed_search_url():
    url = indeed_jobs.build_indeed_search_url("data entry part time", "Napoli, Campania")
    parsed = urlsplit(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "it.indeed.com"
    assert parsed.path == "/jobs"
    assert params["q"] == ["data entry part time"]
    assert params["l"] == ["Napoli, Campania"]


def test_fallback_duckduckgo_does_not_crash_without_ddgs(monkeypatch):
    monkeypatch.setattr(indeed_jobs, "get_ddgs_class", lambda: None)

    jobs = indeed_jobs.collect_fallback_duckduckgo_jobs(limit=1)

    assert jobs == []


def test_normalize_indeed_result():
    job = indeed_jobs.normalize_indeed_result(
        {
            "title": "Data Entry Part Time",
            "company": "Acme",
            "location": "Napoli",
            "url": "https://it.indeed.com/viewjob?jk=123&utm_source=x&fbclid=y",
            "snippet": "Tempo parziale back office",
        },
        "data entry Napoli part time",
        found_at="2026-06-21T00:00:00+00:00",
    )

    assert job["source"] == "indeed"
    assert job["company"] == "Acme"
    assert job["location"] == "Napoli"
    assert job["remote"] is False
    assert job["part_time"] is True
    assert job["category"] == "data_entry"
    assert job["priority_bucket"] == "campania_part_time"
    assert "utm_source" not in job["url"]
    assert "fbclid" not in job["url"]


def test_dedup_works_for_indeed_jobs():
    jobs = [
        {"title": "A", "query": "q1", "url": "https://it.indeed.com/viewjob?jk=1&utm_source=x"},
        {"title": "B", "query": "q2", "url": "https://it.indeed.com/viewjob?jk=1"},
        {"title": "No URL", "query": "q1", "url": ""},
        {"title": "No URL", "query": "q1", "url": ""},
    ]

    assert len(deduplicate_jobs(jobs)) == 2


def test_bad_job_exclusion():
    assert is_bad_job("Agente commerciale", "Solo provvigioni")


def test_campania_part_time_priority():
    job = indeed_jobs.normalize_indeed_result(
        {
            "title": "Back office part time",
            "location": "Pozzuoli",
            "url": "https://it.indeed.com/viewjob?jk=abc",
        },
        "back office Pozzuoli part time",
    )

    assert job["priority_bucket"] == "campania_part_time"
    assert job["score"] >= 75


def test_export_json_csv_xlsx(tmp_path):
    output_path = tmp_path / "indeed_jobs.json"
    jobs = [
        indeed_jobs.normalize_indeed_result(
            {
                "title": "Data Entry",
                "company": "Acme",
                "location": "Napoli",
                "url": "https://it.indeed.com/viewjob?jk=1",
            },
            "data entry Napoli",
            found_at="2026-06-21T00:00:00+00:00",
        )
    ]

    indeed_jobs.export_jobs(jobs, output_path)

    assert output_path.exists()
    assert output_path.with_suffix(".csv").exists()
    assert output_path.with_suffix(".xlsx").exists()
    assert json.loads(output_path.read_text(encoding="utf-8"))[0]["source"] == "indeed"
