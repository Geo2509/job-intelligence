import json
from dataclasses import replace
from pathlib import Path

import yaml

from src import job_aggregator, v2_email_report
from src.job_collector_registry import get_collector


def job(title, url="https://it.indeed.com/viewjob?jk=1", **extra):
    data = {
        "title": title,
        "company": extra.pop("company", "Acme"),
        "location": extra.pop("location", ""),
        "url": url,
        "source": extra.pop("source", "duckduckgo"),
        "query": extra.pop("query", ""),
        "remote": extra.pop("remote", False),
        "part_time": extra.pop("part_time", False),
        "category": extra.pop("category", "general"),
        "priority_bucket": extra.pop("priority_bucket", "other"),
        "score": extra.pop("score", 50),
        "found_at": extra.pop("found_at", "2026-06-25T00:00:00+00:00"),
    }
    data.update(extra)
    return data


def test_remote_mode_does_not_drop_unknown_or_far_locations(monkeypatch):
    plugin = replace(
        get_collector("duckduckgo"),
        callable=lambda **kwargs: [
            job("AI trainer online", "https://it.indeed.com/viewjob?jk=far", location="Milano"),
            job("AI annotator online", "https://it.indeed.com/viewjob?jk=unknown"),
        ],
    )
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugin if name == "duckduckgo" else None)

    jobs = job_aggregator.aggregate_jobs(
        ["duckduckgo"],
        search_profile="remote",
        drop_far_locations=True,
        drop_unknown_locations=True,
    )

    assert {item["title"] for item in jobs} == {"AI trainer online", "AI annotator online"}
    assert {item["location_fit"] for item in jobs} == {"excluded_far", "unknown"}


def test_remote_mode_removes_onsite_in_sede_and_non_remoto(monkeypatch):
    plugin = replace(
        get_collector("duckduckgo"),
        callable=lambda **kwargs: [
            job("AI Trainer remote", "https://it.indeed.com/viewjob?jk=remote"),
            job("AI Trainer onsite", "https://it.indeed.com/viewjob?jk=onsite"),
            job("Data annotator in sede", "https://it.indeed.com/viewjob?jk=sede"),
            job("AI evaluator non remoto", "https://it.indeed.com/viewjob?jk=nonremoto"),
        ],
    )
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugin if name == "duckduckgo" else None)

    jobs = job_aggregator.aggregate_jobs(["duckduckgo"], search_profile="remote")

    assert [item["title"] for item in jobs] == ["AI Trainer remote"]


def test_remote_mode_keeps_ai_trainer_data_entry_and_transcription(monkeypatch):
    plugin = replace(
        get_collector("duckduckgo"),
        callable=lambda **kwargs: [
            job("AI Trainer remote Italian", "https://it.indeed.com/viewjob?jk=ai"),
            job("Data entry smart working Italia", "https://it.indeed.com/viewjob?jk=data"),
            job("Transcription remote Ukrainian", "https://it.indeed.com/viewjob?jk=transcription"),
            job("Back office Napoli", "https://it.indeed.com/viewjob?jk=local", location="Napoli"),
        ],
    )
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugin if name == "duckduckgo" else None)

    jobs = job_aggregator.aggregate_jobs(["duckduckgo"], search_profile="remote")

    assert {item["title"] for item in jobs} == {
        "AI Trainer remote Italian",
        "Data entry smart working Italia",
        "Transcription remote Ukrainian",
    }
    assert all(item["search_profile"] == "remote" for item in jobs)
    assert all("remote_score" in item for item in jobs)


def test_remote_mode_uses_candidate_score_as_main_score():
    item = job_aggregator.normalize_job(
        job("AI Trainer remote Italian", query="AI trainer remote Italian"),
        search_profile="remote",
    )

    assert item["remote_score"] >= item["candidate_score"] + 30
    assert item["match_score"] == int(round(0.8 * item["candidate_score"] + 0.2 * item["remote_score"]))


def test_local_student_mode_still_drops_unknown_locations(monkeypatch):
    plugin = replace(
        get_collector("duckduckgo"),
        callable=lambda **kwargs: [
            job("Back office", "https://it.indeed.com/viewjob?jk=unknown"),
            job("Back office Napoli", "https://it.indeed.com/viewjob?jk=napoli", location="Napoli"),
        ],
    )
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugin if name == "duckduckgo" else None)

    jobs = job_aggregator.aggregate_jobs(
        ["duckduckgo"],
        search_profile="local_student",
        drop_unknown_locations=True,
    )

    assert [item["title"] for item in jobs] == ["Back office Napoli"]


def test_remote_output_files_and_history_are_separate(monkeypatch, tmp_path):
    output_path = tmp_path / "v2_remote_jobs.json"
    pool_path = tmp_path / "v2_remote_candidate_pool.json"
    history_path = tmp_path / "v2_remote_sent_jobs_history.json"
    run_stats_path = tmp_path / "v2_remote_run_stats.json"
    local_history_path = tmp_path / "v2_sent_jobs_history.json"
    plugin = replace(
        get_collector("duckduckgo"),
        callable=lambda **kwargs: [
            job("AI Trainer remote Italian", "https://it.indeed.com/viewjob?jk=remote"),
        ],
    )
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugin if name == "duckduckgo" else None)
    monkeypatch.setattr(
        "sys.argv",
        [
            "job_aggregator",
            "--search-profile",
            "remote",
            "--collectors",
            "duckduckgo",
            "--output",
            str(output_path),
            "--candidate-pool-output",
            str(pool_path),
            "--history-path",
            str(history_path),
            "--run-stats-path",
            str(run_stats_path),
            "--email-clean-results",
        ],
    )

    job_aggregator.main()

    assert output_path.exists()
    assert output_path.with_suffix(".xlsx").exists()
    assert pool_path.exists()
    assert pool_path.with_suffix(".xlsx").exists()
    assert run_stats_path.exists()
    assert history_path.exists()
    assert not local_history_path.exists()
    assert json.loads(output_path.read_text(encoding="utf-8"))[0]["search_profile"] == "remote"
    assert all(
        item["search_profile"] == "remote"
        for item in json.loads(pool_path.read_text(encoding="utf-8"))
    )


def test_remote_email_subject_and_blocks():
    jobs = [
        job("AI Trainer remote", category="ai_data", history_status="NEW", match_score=95, candidate_score=90, remote_score=120),
        job("Data entry smart working", category="data_entry", remote_score=110),
        job("Transcription remote", remote_score=110),
        job("Virtual Assistant remote", remote_score=105),
        job("Customer Support remote moderation", remote_score=100),
        job("Logistics coordinator remote", remote_score=95),
        job("Freelance online role", remote_score=80),
    ]

    body = v2_email_report.build_email_html(jobs, search_profile="remote")

    assert v2_email_report.subject_for_profile("remote") == "Job Intelligence V2: Remote AI/Data Jobs"
    for block in v2_email_report.REMOTE_BLOCKS:
        assert block in body
    assert "<strong>Remote:</strong>" in body
    assert "NEW" in body


def test_github_workflow_accepts_v2_search_profile():
    workflow = Path(".github/workflows/run_collectors.yml").read_text(encoding="utf-8")

    assert "v2_search_profile:" in workflow
    assert '--search-profile "${{ inputs.v2_search_profile }}"' in workflow
    assert "output/v2_remote_jobs.json" in workflow
    assert "--drop-far-locations" in workflow
    assert 'inputs.v2_search_profile }}" = "local_student"' in workflow


def test_remote_discovery_queries_are_configured():
    data = yaml.safe_load(Path("configs/job_sources.yaml").read_text(encoding="utf-8"))

    assert "remote_discovery_queries" in data
    assert "AI trainer remote Italian" in data["remote_discovery_queries"]
    assert "TSMG Ukrainian transcription" in data["remote_discovery_queries"]
