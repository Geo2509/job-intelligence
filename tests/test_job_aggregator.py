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


def test_sorting_prioritizes_student_score_then_score():
    remote = job(
        "Remote data entry",
        remote=True,
        priority_bucket="remote_data",
        score=100,
        query="remote data entry",
        student_score=80,
    )
    local_part_time = job(
        "Back office part-time Napoli",
        part_time=True,
        priority_bucket="campania_part_time",
        score=10,
        query="back office Napoli part time",
        student_score=95,
    )

    sorted_jobs = job_aggregator.sort_jobs([
        job_aggregator.normalize_job(remote),
        job_aggregator.normalize_job(local_part_time),
    ])

    assert sorted_jobs[0]["title"] == "Back office part-time Napoli"
    assert sorted_jobs[1]["title"] == "Remote data entry"


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

    csv_header = output_path.with_suffix(".csv").read_text(encoding="utf-8").splitlines()[0]

    assert output_path.exists()
    assert output_path.with_suffix(".csv").exists()
    assert output_path.with_suffix(".xlsx").exists()
    assert json.loads(output_path.read_text(encoding="utf-8"))[0]["title"] == "Data Entry Napoli"
    assert "student_score" in csv_header


def test_aggregate_with_clean_results_excludes_search_page(monkeypatch, capsys):
    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [
                job("Data Entry Napoli", "https://it.indeed.com/viewjob?jk=1"),
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
            **job_aggregator.normalize_job(job("Data Entry Napoli", "https://it.indeed.com/viewjob?jk=1")),
            "result_type": "job",
            "url_result_type": "real_job",
        }
    ]

    job_aggregator.export_jobs(jobs, output_path)

    exported_json = json.loads(output_path.read_text(encoding="utf-8"))
    csv_header = output_path.with_suffix(".csv").read_text(encoding="utf-8").splitlines()[0]

    assert exported_json[0]["result_type"] == "job"
    assert exported_json[0]["url_result_type"] == "real_job"
    assert "result_type" in csv_header
    assert "url_result_type" in csv_header


def test_clean_results_scores_only_surviving_jobs(monkeypatch):
    calls = []

    def fake_student_score(job):
        calls.append(job["title"])
        return 77

    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [
                job("Kept job", "https://it.indeed.com/viewjob?jk=1"),
                job("Removed search", "https://www.jobbydoo.it/lavoro-data-entry"),
            ],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))
    monkeypatch.setattr(job_aggregator, "evaluate_student_score", fake_student_score)

    jobs = job_aggregator.aggregate_jobs(["duckduckgo"], clean_results=True)

    assert [item["title"] for item in jobs] == ["Kept job"]
    assert calls == ["Kept job"]
    assert jobs[0]["student_score"] == 77


def test_aggregate_soft_clean_keeps_trusted_pages(monkeypatch):
    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [
                job("Subito offerte lavoro", "https://www.subito.it/annunci-campania/vendita/offerte-lavoro/napoli/"),
                job("Removed search", "https://www.jobbydoo.it/lavoro-data-entry"),
            ],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(["duckduckgo"], clean_results=True)

    assert [item["title"] for item in jobs] == ["Subito offerte lavoro"]
    assert jobs[0]["result_type"] == "search_page"
    assert "student_score" in jobs[0]


def test_aggregate_email_clean_removes_soft_search_pages(monkeypatch):
    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [
                job("Subito offerte lavoro", "https://www.subito.it/annunci-campania/vendita/offerte-lavoro/napoli/"),
                job("Jooble job", "https://it.jooble.org/jdp/123456"),
            ],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(["duckduckgo"], email_clean_results=True)

    assert [item["title"] for item in jobs] == ["Jooble job"]
    assert jobs[0]["url_result_type"] == "real_job"
    assert "student_score" in jobs[0]


def test_aggregate_email_clean_keeps_adecco_real_jobs(monkeypatch):
    plugins = {
        "adecco": replace(
            get_collector("adecco"),
            callable=lambda **kwargs: [
                job(
                    "Adecco back office",
                    "https://www.adecco.it/lavoro/back-office-part-time_napoli_123456/",
                    source="adecco",
                ),
                job(
                    "Adecco search",
                    "https://www.adecco.it/lavoro/?k=napoli",
                    source="adecco",
                ),
            ],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(["adecco"], email_clean_results=True)

    assert [item["title"] for item in jobs] == ["Adecco back office"]
    assert jobs[0]["source"] == "adecco"
    assert jobs[0]["url_result_type"] == "real_job"
    assert "student_score" in jobs[0]


def test_aggregate_strict_clean_keeps_only_real_jobs(monkeypatch):
    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [
                job("Indeed job", "https://it.indeed.com/viewjob?jk=1"),
                job("Subito offerte lavoro", "https://www.subito.it/annunci-campania/vendita/offerte-lavoro/napoli/"),
            ],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(
        ["duckduckgo"],
        clean_results=True,
        strict_job_detail_only=True,
    )

    assert [item["title"] for item in jobs] == ["Indeed job"]
    assert jobs[0]["url_result_type"] == "real_job"


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


def test_balanced_top_keeps_remote_data_when_local_scores_are_higher():
    jobs = [
        job("Local part time high", "https://example.com/local-1", score=900),
        job("Local part time higher", "https://example.com/local-2", score=800),
        job(
            "Remote data analyst",
            "https://example.com/remote-1",
            remote=True,
            priority_bucket="remote_data",
            score=10,
        ),
    ]

    balanced = job_aggregator.balanced_top(jobs, top=2, min_remote=1)

    assert balanced[0]["title"] == "Remote data analyst"
    assert {item["title"] for item in balanced} == {"Remote data analyst", "Local part time high"}


def test_balanced_top_does_not_exceed_top():
    jobs = [
        job(
            f"Remote data {index}",
            f"https://example.com/remote-{index}",
            remote=True,
            priority_bucket="remote_data",
            score=index,
        )
        for index in range(5)
    ]

    balanced = job_aggregator.balanced_top(jobs, top=3, min_remote=20)

    assert len(balanced) == 3


def test_balanced_top_does_not_add_duplicates():
    jobs = [
        job(
            "Remote data duplicate",
            "https://example.com/same?utm_source=x",
            remote=True,
            priority_bucket="remote_data",
            score=100,
        ),
        job(
            "Remote data duplicate copy",
            "https://example.com/same",
            remote=True,
            priority_bucket="remote_data",
            score=90,
        ),
        job("Fallback", "https://example.com/fallback", score=80),
    ]

    balanced = job_aggregator.balanced_top(jobs, top=3, min_remote=20)

    assert len(balanced) == 2
    assert [item["url"] for item in balanced] == [
        "https://example.com/same?utm_source=x",
        "https://example.com/fallback",
    ]


def test_balanced_top_takes_available_remote_when_less_than_min_remote():
    jobs = [
        job(
            "Only remote",
            "https://example.com/remote",
            remote=True,
            priority_bucket="remote_data",
            score=30,
        ),
        job("Local one", "https://example.com/local-1", score=90),
        job("Local two", "https://example.com/local-2", score=80),
    ]

    balanced = job_aggregator.balanced_top(jobs, top=3, min_remote=20)

    assert [item["title"] for item in balanced] == ["Only remote", "Local one", "Local two"]


def test_balanced_top_fallback_fills_remaining_by_score():
    jobs = [
        job(
            "Remote low",
            "https://example.com/remote",
            remote=True,
            priority_bucket="remote_data",
            score=10,
        ),
        job("Fallback high", "https://example.com/high", score=100),
        job("Fallback medium", "https://example.com/medium", score=70),
        job("Fallback low", "https://example.com/low", score=20),
    ]

    balanced = job_aggregator.balanced_top(jobs, top=3, min_remote=1)

    assert [item["title"] for item in balanced] == [
        "Remote low",
        "Fallback high",
        "Fallback medium",
    ]
