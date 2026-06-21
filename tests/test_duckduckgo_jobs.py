import builtins

from src.collectors import duckduckgo_jobs


def test_scoring_remote():
    score = duckduckgo_jobs.score_result(
        "Data entry full remote",
        "Smart working lavoro da casa",
        "",
    )

    assert score >= 30


def test_scoring_part_time():
    score = duckduckgo_jobs.score_result(
        "Back office part-time",
        "Tempo parziale 4 ore",
        "",
    )

    assert score >= 25


def test_scoring_local_city():
    score = duckduckgo_jobs.score_result(
        "Data entry",
        "Offerta a Pozzuoli vicino Napoli",
        "",
    )

    assert score >= 20


def test_bad_job_exclusion():
    assert duckduckgo_jobs.is_bad_job(
        "Agente commerciale",
        "Solo provvigioni e porta a porta",
    )


def test_url_normalization_removes_tracking_params():
    normalized = duckduckgo_jobs.normalize_url(
        "https://Example.com/jobs/123/?utm_source=x&fbclid=y&gclid=z&ref=keep"
    )

    assert normalized == "https://example.com/jobs/123?ref=keep"


def test_dedup_works():
    jobs = [
        {
            "title": "Data Entry",
            "query": "data entry Napoli",
            "url": "https://example.com/jobs/1",
        },
        {
            "title": "Data Entry duplicate",
            "query": "other query",
            "url": "https://example.com/jobs/1",
        },
        {
            "title": "No URL",
            "query": "data entry Napoli",
            "url": "",
        },
        {
            "title": "No URL",
            "query": "data entry Napoli",
            "url": "",
        },
    ]

    deduped = duckduckgo_jobs.deduplicate_jobs(jobs)

    assert len(deduped) == 2


def test_ddgs_missing_fallback_does_not_crash(monkeypatch, capsys):
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "ddgs":
            raise ImportError("missing ddgs")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    jobs = duckduckgo_jobs.collect_jobs("configs/job_sources.yaml", limit=1, pause_seconds=0)

    assert jobs == []
    assert "ddgs package not installed" in capsys.readouterr().out
