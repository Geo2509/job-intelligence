import json
from dataclasses import replace

from src import job_aggregator
from src.job_collector_registry import get_collector


def job(title, url="", source="duckduckgo", query="data entry Napoli", score=10, **extra):
    data = {
        "title": title,
        "company": extra.pop("company", ""),
        "location": extra.pop("location", ""),
        "url": url,
        "source": source,
        "query": query,
        "remote": extra.pop("remote", False),
        "part_time": extra.pop("part_time", False),
        "category": extra.pop("category", "general"),
        "priority_bucket": extra.pop("priority_bucket", "other"),
        "score": score,
        "found_at": "2026-06-21T00:00:00+00:00",
    }
    data.update(extra)
    return data


def test_aggregate_combines_results(monkeypatch):
    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [job("Duck result", source="duckduckgo")],
        ),
        "indeed": replace(
            get_collector("indeed"),
            callable=lambda **kwargs: [job("Indeed result", source="indeed")],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(["duckduckgo", "indeed"])

    assert {item["source"] for item in jobs} == {"duckduckgo", "indeed"}
    assert len(jobs) == 2


def test_dedup_by_normalized_url():
    jobs = [
        job("First", "https://example.com/jobs/1?utm_source=x"),
        job("Second", "https://example.com/jobs/1"),
    ]

    deduped = job_aggregator.deduplicate_jobs([job_aggregator.normalize_job(item) for item in jobs])

    assert len(deduped) == 1


def test_fallback_dedup_by_title_company_location():
    jobs = [
        job("Back Office", company="Acme", location="Napoli", url="", query="q1"),
        job("Back Office", company="Acme", location="Napoli", url="", query="q2"),
    ]

    deduped = job_aggregator.deduplicate_jobs([job_aggregator.normalize_job(item) for item in jobs])

    assert len(deduped) == 1


def test_sorting_prioritizes_campania_part_time_above_remote_data():
    remote = job(
        "Remote data entry",
        remote=True,
        priority_bucket="remote_data",
        score=100,
        query="remote data entry",
    )
    local_part_time = job(
        "Back office part-time Napoli",
        part_time=True,
        priority_bucket="campania_part_time",
        score=10,
        query="back office Napoli part time",
    )

    sorted_jobs = job_aggregator.sort_jobs([
        job_aggregator.normalize_job(remote),
        job_aggregator.normalize_job(local_part_time),
    ])

    assert sorted_jobs[0]["priority_bucket"] == "campania_part_time"
    assert sorted_jobs[1]["priority_bucket"] == "remote_data"


def test_one_collector_failure_does_not_break_aggregator(monkeypatch, capsys):
    def broken_collector(**kwargs):
        raise RuntimeError("boom")

    plugins = {
        "duckduckgo": replace(get_collector("duckduckgo"), callable=broken_collector),
        "indeed": replace(
            get_collector("indeed"),
            callable=lambda **kwargs: [job("Indeed result", source="indeed")],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(["duckduckgo", "indeed"])

    assert len(jobs) == 1
    assert jobs[0]["source"] == "indeed"
    assert "Collector failed: duckduckgo" in capsys.readouterr().out


def test_unknown_collector_does_not_break_aggregator(capsys):
    jobs = job_aggregator.aggregate_jobs(["unknown"])

    assert jobs == []
    assert "Unknown collector skipped: unknown" in capsys.readouterr().out


def test_without_collectors_uses_enabled_registry_collectors(monkeypatch):
    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [job("Duck result", source="duckduckgo")],
        ),
        "indeed": replace(
            get_collector("indeed"),
            callable=lambda **kwargs: [job("Indeed result", source="indeed")],
        ),
    }
    monkeypatch.setattr(job_aggregator, "enabled_collectors", lambda: ["duckduckgo", "indeed"])
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(None)

    assert {item["source"] for item in jobs} == {"duckduckgo", "indeed"}


def test_export_json_csv_xlsx(tmp_path):
    output_path = tmp_path / "v2_jobs.json"
    jobs = [
        job_aggregator.normalize_job(
            job(
                "Data Entry Napoli",
                "https://example.com/jobs/1",
                company="Acme",
                location="Napoli",
                part_time=True,
                query="data entry Napoli part time",
            )
        )
    ]

    job_aggregator.export_jobs(jobs, output_path)

    assert output_path.exists()
    assert output_path.with_suffix(".csv").exists()
    assert output_path.with_suffix(".xlsx").exists()
    assert json.loads(output_path.read_text(encoding="utf-8"))[0]["title"] == "Data Entry Napoli"


def test_aggregate_with_clean_results_excludes_search_page(monkeypatch, capsys):
    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [
                job("Data Entry Napoli", "https://example.com/job/1"),
                job("Search results", "https://example.com/search/data-entry"),
            ],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(["duckduckgo"], clean_results=True)

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Data Entry Napoli"
    assert jobs[0]["result_type"] == "job"
    output = capsys.readouterr().out
    assert "Total before cleaning: 2" in output
    assert "Removed search_page: 1" in output
    assert "Total after cleaning: 1" in output


def test_export_includes_result_type_when_cleaned(tmp_path):
    output_path = tmp_path / "v2_jobs.json"
    jobs = [
        {
            **job_aggregator.normalize_job(job("Data Entry Napoli", "https://example.com/job/1")),
            "result_type": "job",
        }
    ]

    job_aggregator.export_jobs(jobs, output_path)

    exported_json = json.loads(output_path.read_text(encoding="utf-8"))
    csv_header = output_path.with_suffix(".csv").read_text(encoding="utf-8").splitlines()[0]

    assert exported_json[0]["result_type"] == "job"
    assert "result_type" in csv_header


def test_without_clean_results_keeps_old_behavior(monkeypatch):
    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [job("Search results", "https://example.com/search/data-entry")],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(["duckduckgo"], clean_results=False)

    assert len(jobs) == 1
    assert jobs[0]["url"] == "https://example.com/search/data-entry"
    assert "result_type" not in jobs[0]
