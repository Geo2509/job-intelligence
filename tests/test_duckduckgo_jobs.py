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


def test_get_priority_bucket_returns_campania_part_time():
    text = "Back office Napoli tempo parziale"
    bucket = duckduckgo_jobs.get_priority_bucket(text, part_time=True, remote=False)
    assert bucket == "campania_part_time"


def test_campania_part_time_sorting_prioritizes_local_part_time_above_remote():
    jobs = [
        {"score": 10, "remote": True, "priority_bucket": "other"},
        {"score": 5, "remote": False, "priority_bucket": "campania_part_time"},
        {"score": 20, "remote": False, "priority_bucket": "other"},
    ]

    sorted_jobs = sorted(jobs, key=duckduckgo_jobs.campania_part_time_sort_key)
    assert sorted_jobs[0]["priority_bucket"] == "campania_part_time"
    assert sorted_jobs[1]["remote"] is True


def test_collect_jobs_defaults_to_top_50(monkeypatch):
    class FakeResult:
        def __init__(self, url, title):
            self._url = url
            self._title = title
        def get(self, key):
            return {
                "href": self._url,
                "title": self._title,
                "body": "",
                "snippet": "",
            }.get(key)

    class FakeDDGS:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def text(self, query, region, safesearch, max_results):
            return [FakeResult(f"https://example.com/{i}", f"Title {i}") for i in range(100)]

    monkeypatch.setattr(duckduckgo_jobs, "get_ddgs_class", lambda: lambda: FakeDDGS())
    monkeypatch.setattr(duckduckgo_jobs, "load_discovery_queries", lambda config_path: ["query"])

    jobs = duckduckgo_jobs.collect_jobs("configs/job_sources.yaml", limit=1, pause_seconds=0)
    assert len(jobs) == 50


def test_scoring_local_part_time_is_high():
    score = duckduckgo_jobs.score_result(
        "Back office part-time Napoli",
        "Tempo parziale 4 ore",
        "",
    )
    assert score >= 75
