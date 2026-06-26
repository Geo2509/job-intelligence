import json
import zipfile
from dataclasses import replace

from src import candidate_pool, job_aggregator
from src.job_collector_registry import get_collector


def job(title="Back office Napoli", url="https://it.indeed.com/viewjob?jk=1", **extra):
    data = {
        "title": title,
        "company": extra.pop("company", "Acme"),
        "location": extra.pop("location", "Napoli"),
        "url": url,
        "source": extra.pop("source", "gigroup"),
        "collector": extra.pop("collector", "gigroup"),
        "query": extra.pop("query", "back office Napoli"),
        "remote": extra.pop("remote", False),
        "part_time": extra.pop("part_time", True),
        "category": extra.pop("category", "data_entry"),
        "priority_bucket": extra.pop("priority_bucket", "campania_part_time"),
        "score": extra.pop("score", 80),
        "student_score": extra.pop("student_score", 90),
        "candidate_score": extra.pop("candidate_score", 90),
        "match_score": extra.pop("match_score", 90),
        "location_fit": extra.pop("location_fit", "allowed_local"),
        "found_at": extra.pop("found_at", "2026-06-24T00:00:00+00:00"),
    }
    data.update(extra)
    return data


def pool_candidate(item):
    normalized = job_aggregator.normalize_job(item, include_profile_scores=False)
    for field in ["student_score", "candidate_score", "match_score", "location_fit"]:
        if field in item:
            normalized[field] = item[field]
    classified = candidate_pool.classify_candidates([normalized])[0]
    annotated = job_aggregator.annotate_history_status([classified], {})[0]
    return annotated


def test_pool_contains_all_real_jobs_without_email_limit():
    candidates = [
        pool_candidate(job("First", match_score=95)),
        pool_candidate(job("Second", url="https://it.indeed.com/viewjob?jk=2", match_score=75)),
    ]
    pool = candidate_pool.build_candidate_pool(candidates, email_jobs=[candidates[0]], history={})

    assert [item["title"] for item in pool] == ["First", "Second"]
    assert pool[0]["rejection_reason"] == "passed"
    assert pool[1]["rejection_reason"] == "email_limit"


def test_candidate_pool_excel_is_created_with_action_column(tmp_path):
    output_path = tmp_path / "v2_candidate_pool.json"
    pool = [pool_candidate(job())]

    candidate_pool.export_candidate_pool(pool, output_path)

    assert output_path.exists()
    assert output_path.with_suffix(".xlsx").exists()
    with zipfile.ZipFile(output_path.with_suffix(".xlsx")) as xlsx:
        sheet = xlsx.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "Action" in sheet
    assert "autoFilter" in sheet
    assert "state=\"frozen\"" in sheet
    assert "conditionalFormatting" in sheet


def test_collector_stats_are_counted():
    real = pool_candidate(job())
    search = pool_candidate(job("Search", url="https://example.com/search?q=data"))
    stats = candidate_pool.build_collector_stats(
        {"gigroup": 2},
        [real, search],
        email_jobs=[real],
    )

    row = stats[0]
    assert row["collector"] == "gigroup"
    assert row["collected"] == 2
    assert row["real_jobs"] == 1
    assert row["allowed_local"] == 1
    assert row["search_pages"] == 1
    assert row["history_new"] == 1
    assert row["email_jobs"] == 1


def test_rejection_reason_is_filled_for_location_and_low_match():
    far = pool_candidate(job("Milano", location="Milano", location_fit="excluded_far"))
    low = pool_candidate(job("Low", url="https://it.indeed.com/viewjob?jk=3", match_score=55))

    pool = candidate_pool.build_candidate_pool([far, low], email_jobs=[], history={})

    reasons = {item["title"]: item["rejection_reason"] for item in pool}
    assert reasons["Milano"] == "excluded_far"
    assert reasons["Low"] == "low_match"


def test_cli_filters_source_location_reason_and_top(tmp_path, capsys):
    path = tmp_path / "v2_candidate_pool.json"
    rows = [
        {**pool_candidate(job("Gi Unknown", location_fit="unknown")), "rejection_reason": "unknown_location"},
        {**pool_candidate(job("Randstad", source="randstad", collector="randstad")), "rejection_reason": "passed"},
    ]
    path.write_text(json.dumps(rows), encoding="utf-8")

    candidate_pool.main([
        "--input",
        str(path),
        "--source",
        "gigroup",
        "--location",
        "unknown",
        "--reason",
        "unknown_location",
        "--top",
        "1",
    ])

    output = capsys.readouterr().out
    assert "Gi Unknown" in output
    assert "Randstad" not in output


def test_action_is_preserved_between_exports(tmp_path):
    output_path = tmp_path / "v2_candidate_pool.json"
    item = pool_candidate(job())
    headers = [label for label, _ in candidate_pool.POOL_FIELDS]
    row = [
        item.get(field, "")
        for _, field in candidate_pool.POOL_FIELDS[:-1]
    ] + ["Applied"]
    candidate_pool.write_xlsx([row], headers, output_path.with_suffix(".xlsx"))

    exported = candidate_pool.export_candidate_pool([{**item, "action": ""}], output_path)

    assert exported[0]["action"] == "Applied"
    assert json.loads(output_path.read_text(encoding="utf-8"))[0]["action"] == "Applied"


def test_job_aggregator_main_creates_candidate_pool_artifacts(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    output_path = tmp_path / "v2_jobs.json"
    pool_path = tmp_path / "v2_candidate_pool.json"
    stats_path = tmp_path / "v2_collector_stats.json"
    history_path = tmp_path / "v2_sent_jobs_history.json"
    run_stats_path = tmp_path / "v2_run_stats.json"
    plugin = replace(
        get_collector("gigroup"),
        callable=lambda **kwargs: [job()],
    )
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugin if name == "gigroup" else None)
    monkeypatch.setattr(
        "sys.argv",
        [
            "job_aggregator",
            "--collectors",
            "gigroup",
            "--output",
            str(output_path),
            "--candidate-pool-output",
            str(pool_path),
            "--collector-stats-output",
            str(stats_path),
            "--history-path",
            str(history_path),
            "--run-stats-path",
            str(run_stats_path),
        ],
    )

    job_aggregator.main()

    assert pool_path.exists()
    assert pool_path.with_suffix(".xlsx").exists()
    assert stats_path.exists()
    assert stats_path.with_suffix(".xlsx").exists()
    assert (tmp_path / "output/url_pattern_debug.json").exists()
    assert (tmp_path / "output/url_pattern_debug.xlsx").exists()
    assert (tmp_path / "output/unknown_urls.xlsx").exists()
    assert (tmp_path / "output/url_pattern_recommendations.md").exists()
    output = capsys.readouterr().out
    assert f"Saved {pool_path}" in output
    assert f"Saved {pool_path.with_suffix('.xlsx')}" in output
    assert f"Saved {stats_path}" in output
    assert f"Saved {stats_path.with_suffix('.xlsx')}" in output
