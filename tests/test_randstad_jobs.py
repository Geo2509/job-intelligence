from urllib.parse import urlsplit

from src.collectors import randstad_jobs


def test_build_randstad_search_url():
    url = randstad_jobs.build_randstad_search_url("data entry Napoli")
    parsed = urlsplit(url)

    assert parsed.scheme == "https"
    assert parsed.netloc == "www.randstad.it"
    assert parsed.path == "/offerte-lavoro/q-data-entry-napoli/"


def test_collector_does_not_crash_when_randstad_blocks(monkeypatch):
    monkeypatch.setattr(randstad_jobs, "fetch_direct_search", lambda url: None)
    monkeypatch.setattr(randstad_jobs, "get_ddgs_class", lambda: None)

    jobs = randstad_jobs.collect_jobs(limit=1, direct_pause_seconds=0)

    assert jobs == []


def test_fallback_duckduckgo_works_with_mocks(monkeypatch):
    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def text(self, query, region, safesearch, max_results):
            return [
                {
                    "title": "Back office part time Napoli",
                    "href": "https://www.randstad.it/offerte-lavoro/back-office-part-time_napoli_123456/",
                    "body": "Tempo parziale ufficio",
                }
            ]

    monkeypatch.setattr(randstad_jobs, "get_ddgs_class", lambda: FakeDDGS)

    jobs = randstad_jobs.collect_fallback_duckduckgo_jobs(limit=1)

    assert len(jobs) == 1
    assert jobs[0]["source"] == "randstad"
    assert jobs[0]["part_time"] is True
    assert jobs[0]["priority_bucket"] == "campania_part_time"


def test_parse_randstad_html_extracts_job_detail_links():
    page_html = """
    <html><body>
      <a href="/offerte-lavoro/data-entry-part-time_napoli_123456/">
        Data entry part time Napoli
      </a>
      <a href="/offerte-lavoro/q-data-entry-napoli/">Search page</a>
    </body></html>
    """

    jobs = randstad_jobs.parse_randstad_html(page_html, "data entry Napoli")

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Data entry part time Napoli"
    assert jobs[0]["url"] == "https://www.randstad.it/offerte-lavoro/data-entry-part-time_napoli_123456"


def test_normalize_randstad_result_output_schema():
    job = randstad_jobs.normalize_randstad_result(
        {
            "title": "Impiegato amministrativo part time",
            "company": "Randstad",
            "location": "Napoli",
            "url": "https://www.randstad.it/offerte-lavoro/impiegato-amministrativo_napoli_123/?utm_source=x",
            "snippet": "Tempo parziale back office",
        },
        "impiegato amministrativo Napoli",
        found_at="2026-06-23T00:00:00+00:00",
    )

    assert set(job) == set(randstad_jobs.OUTPUT_FIELDS)
    assert job["source"] == "randstad"
    assert job["category"] in {"administration", "data_office", "data_entry", "general"}
    assert job["part_time"] is True
    assert job["found_at"] == "2026-06-23T00:00:00+00:00"
    assert "utm_source" not in job["url"]
