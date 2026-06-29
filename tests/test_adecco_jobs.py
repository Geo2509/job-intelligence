from urllib.parse import parse_qs, urlsplit

from src.collectors import adecco_jobs


def test_build_adecco_search_url():
    url = adecco_jobs.build_adecco_search_url("data entry Napoli")
    parsed = urlsplit(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "www.adecco.it"
    assert parsed.path == "/lavoro/"
    assert params["k"] == ["data entry Napoli"]


def test_collector_does_not_crash_when_adecco_blocks(monkeypatch):
    monkeypatch.setattr(adecco_jobs, "fetch_direct_search", lambda url: None)
    monkeypatch.setattr(adecco_jobs, "get_ddgs_class", lambda: None)

    jobs = adecco_jobs.collect_jobs(limit=1, direct_pause_seconds=0)

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
                    "href": "https://www.adecco.it/lavoro/back-office-part-time_napoli_123456/",
                    "body": "Tempo parziale ufficio",
                }
            ]

    monkeypatch.setattr(adecco_jobs, "get_ddgs_class", lambda: FakeDDGS)

    jobs = adecco_jobs.collect_fallback_duckduckgo_jobs(limit=1)

    assert len(jobs) == 1
    assert jobs[0]["source"] == "adecco"
    assert jobs[0]["part_time"] is True
    assert jobs[0]["student_score"] >= 90
    assert jobs[0]["priority_bucket"] == "campania_part_time"


def test_fallback_duckduckgo_keeps_only_detail_urls(monkeypatch):
    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def text(self, query, region, safesearch, max_results):
            return [
                {
                    "title": "Consulta le offerte di lavoro Adecco",
                    "href": "https://www.adecco.it/offerte-lavoro?l=napoli",
                    "body": "Search results",
                },
                {
                    "title": "Back office part time Napoli",
                    "href": "https://www.adecco.it/lavoro/back-office-part-time_napoli_123456/",
                    "body": "Tempo parziale",
                },
            ]

    monkeypatch.setattr(adecco_jobs, "get_ddgs_class", lambda: FakeDDGS)

    jobs = adecco_jobs.collect_fallback_duckduckgo_jobs(limit=2)

    assert [job["url"] for job in jobs] == [
        "https://www.adecco.it/lavoro/back-office-part-time_napoli_123456"
    ]


def test_parse_adecco_html_extracts_job_detail_links():
    page_html = """
    <html><body>
      <a href="/lavoro/data-entry-part-time_napoli_123456/">
        Data entry part time Napoli
      </a>
      <a href="/lavoro/?k=data-entry">Search page</a>
      <a href="/lavora-con-noi">Career page</a>
    </body></html>
    """

    jobs = adecco_jobs.parse_adecco_html(page_html, "data entry Napoli")

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Data entry part time Napoli"
    assert jobs[0]["url"] == "https://www.adecco.it/lavoro/data-entry-part-time_napoli_123456"


def test_normalize_adecco_result_output_schema():
    job = adecco_jobs.normalize_adecco_result(
        {
            "title": "Impiegato amministrativo part time",
            "company": "Adecco",
            "location": "Napoli",
            "url": "https://www.adecco.it/lavoro/impiegato-amministrativo_napoli_123/?utm_source=x",
            "snippet": "Tempo parziale back office",
        },
        "impiegato amministrativo Napoli",
        found_at="2026-06-23T00:00:00+00:00",
    )

    assert set(job) == set(adecco_jobs.OUTPUT_FIELDS)
    assert job["source"] == "adecco"
    assert job["part_time"] is True
    assert job["student_score"] >= 90
    assert job["found_at"] == "2026-06-23T00:00:00+00:00"
    assert "utm_source" not in job["url"]
