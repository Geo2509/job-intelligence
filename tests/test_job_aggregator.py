import json

from src import job_aggregator


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
    monkeypatch.setitem(
        job_aggregator.COLLECTORS,
        "duckduckgo",
        lambda **kwargs: [job("Duck result", source="duckduckgo")],
    )
    monkeypatch.setitem(
        job_aggregator.COLLECTORS,
        "indeed",
        lambda **kwargs: [job("Indeed result", source="indeed")],
    )

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

    monkeypatch.setitem(job_aggregator.COLLECTORS, "duckduckgo", broken_collector)
    monkeypatch.setitem(
        job_aggregator.COLLECTORS,
        "indeed",
        lambda **kwargs: [job("Indeed result", source="indeed")],
    )

    jobs = job_aggregator.aggregate_jobs(["duckduckgo", "indeed"])

    assert len(jobs) == 1
    assert jobs[0]["source"] == "indeed"
    assert "Collector failed: duckduckgo" in capsys.readouterr().out


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
