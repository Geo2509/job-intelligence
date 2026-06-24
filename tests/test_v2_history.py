import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from src import job_aggregator
from src.job_collector_registry import get_collector


def job(title="Back office Napoli", url="https://example.com/jobs/1", **extra):
    data = {
        "title": title,
        "company": extra.pop("company", "Acme"),
        "location": extra.pop("location", "Napoli"),
        "url": url,
        "source": extra.pop("source", "duckduckgo"),
        "query": extra.pop("query", "back office Napoli"),
        "remote": extra.pop("remote", False),
        "part_time": extra.pop("part_time", True),
        "category": extra.pop("category", "data_entry"),
        "priority_bucket": extra.pop("priority_bucket", "campania_part_time"),
        "score": extra.pop("score", 100),
        "student_score": extra.pop("student_score", 90),
        "candidate_score": extra.pop("candidate_score", 90),
        "match_score": extra.pop("match_score", 90),
        "location_fit": extra.pop("location_fit", "allowed_local"),
        "found_at": extra.pop("found_at", "2026-06-24T00:00:00+00:00"),
    }
    data.update(extra)
    return data


def history_for(item, **extra):
    record = {
        "job_id": job_aggregator.job_id(item),
        "url": item["url"],
        "title": item["title"],
        "source": item["source"],
        "first_seen": "2026-06-20T00:00:00+00:00",
        "last_seen": "2026-06-20T00:00:00+00:00",
        "last_sent": extra.pop("last_sent", "2026-06-23T00:00:00+00:00"),
        "sent_count": extra.pop("sent_count", 1),
        "content_hash": extra.pop("content_hash", job_aggregator.content_hash(item)),
        "match_score": extra.pop("match_score", item["match_score"]),
    }
    record.update(extra)
    return record


def write_history(tmp_path, records):
    path = tmp_path / "v2_sent_jobs_history.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def install_collector(monkeypatch, jobs):
    plugin = replace(
        get_collector("duckduckgo"),
        callable=lambda **kwargs: jobs,
    )
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugin if name == "duckduckgo" else None)


def test_new_job_gets_new_status():
    item = job()

    annotated = job_aggregator.annotate_history_status([item], {})

    assert annotated[0]["history_status"] == "NEW"


def test_repeated_job_gets_seen_status():
    item = job()
    history = {job_aggregator.job_id(item): history_for(item)}

    annotated = job_aggregator.annotate_history_status([item], history)

    assert annotated[0]["history_status"] == "SEEN"


def test_changed_content_hash_gets_updated_status():
    item = job(match_score=95)
    previous = history_for(item, content_hash="old-hash")
    history = {job_aggregator.job_id(item): previous}

    annotated = job_aggregator.annotate_history_status([item], history)

    assert annotated[0]["history_status"] == "UPDATED"


def test_old_last_sent_gets_resurfaced_status():
    item = job()
    old_sent = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    history = {job_aggregator.job_id(item): history_for(item, last_sent=old_sent)}

    annotated = job_aggregator.annotate_history_status([item], history, skip_seen_days=7)

    assert annotated[0]["history_status"] == "RESURFACED"


def test_seen_is_skipped_by_default(monkeypatch, tmp_path):
    item = job()
    history_path = write_history(tmp_path, [history_for(job_aggregator.normalize_job(item))])
    install_collector(monkeypatch, [item])

    jobs = job_aggregator.aggregate_jobs(["duckduckgo"], history_path=history_path)

    assert jobs == []


def test_include_seen_true_includes_seen(monkeypatch, tmp_path):
    item = job()
    history_path = write_history(tmp_path, [history_for(job_aggregator.normalize_job(item))])
    install_collector(monkeypatch, [item])

    jobs = job_aggregator.aggregate_jobs(
        ["duckduckgo"],
        history_path=history_path,
        include_seen=True,
    )

    assert len(jobs) == 1
    assert jobs[0]["history_status"] == "SEEN"


def test_history_update_increments_sent_count():
    item = job()
    existing = {job_aggregator.job_id(item): history_for(item, sent_count=2)}

    updated = job_aggregator.update_sent_history(existing, [item], sent_at="2026-06-24T00:00:00+00:00")

    assert updated[job_aggregator.job_id(item)]["sent_count"] == 3
    assert updated[job_aggregator.job_id(item)]["last_sent"] == "2026-06-24T00:00:00+00:00"


def test_job_id_is_stable_for_same_url():
    first = job(url="https://example.com/jobs/1?utm_source=x")
    second = job(url="https://example.com/jobs/1")

    assert job_aggregator.job_id(first) == job_aggregator.job_id(second)


def test_v2_run_stats_json_is_created(monkeypatch, tmp_path):
    output_path = tmp_path / "v2_jobs.json"
    history_path = tmp_path / "v2_sent_jobs_history.json"
    stats_path = tmp_path / "v2_run_stats.json"
    install_collector(monkeypatch, [job()])
    monkeypatch.setattr(
        "sys.argv",
        [
            "job_aggregator",
            "--collectors",
            "duckduckgo",
            "--output",
            str(output_path),
            "--history-path",
            str(history_path),
            "--run-stats-path",
            str(stats_path),
            "--top",
            "10",
        ],
    )

    job_aggregator.main()

    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    assert stats["total_candidates"] == 1
    assert stats["new_jobs"] == 1
    assert stats["email_jobs"] == 1
    assert output_path.exists()
    assert history_path.exists()
