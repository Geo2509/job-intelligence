from urllib.parse import parse_qs, urlsplit

from src.collectors import jooble_jobs


def test_build_jooble_search_url():
    url = jooble_jobs.build_jooble_search_url("data entry Napoli part time")
    parsed = urlsplit(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "it.jooble.org"
    assert parsed.path == "/SearchResult"
    assert params["ukw"] == ["data entry Napoli part time"]


def test_jooble_detail_url_detection_accepts_only_jdp():
    assert jooble_jobs.is_jooble_job_detail_url("https://it.jooble.org/jdp/123456")
    assert not jooble_jobs.is_jooble_job_detail_url("https://it.jooble.org/rjdp/123456")
    assert not jooble_jobs.is_jooble_job_detail_url("https://it.jooble.org/lavoro-data-entry/napoli")
    assert not jooble_jobs.is_jooble_job_detail_url("https://it.jooble.org/SearchResult?ukw=data")


def test_fallback_duckduckgo_accepts_only_jdp_urls(monkeypatch):
    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def text(self, query, region, safesearch, max_results):
            return [
                {
                    "title": "Data entry jobs Napoli",
                    "href": "https://it.jooble.org/lavoro-data-entry/napoli",
                    "body": "Search results",
                },
                {
                    "title": "Data Entry Part Time",
                    "href": "https://it.jooble.org/jdp/123456",
                    "body": "Tempo parziale",
                },
                {
                    "title": "Redirect result",
                    "href": "https://it.jooble.org/rjdp/789012",
                    "body": "Redirect",
                },
            ]

    monkeypatch.setattr(jooble_jobs, "get_ddgs_class", lambda: FakeDDGS)

    jobs = jooble_jobs.collect_fallback_duckduckgo_jobs(limit=3)

    assert [job["url"] for job in jobs] == ["https://it.jooble.org/jdp/123456"]


def test_parse_jooble_html_extracts_jdp_links():
    page_html = """
    <html><body>
      <a href="/jdp/123456">Data entry part time Napoli</a>
      <a href="/SearchResult?ukw=data">Search page</a>
    </body></html>
    """

    jobs = jooble_jobs.parse_jooble_html(page_html, "data entry Napoli part time")

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Data entry part time Napoli"
    assert jobs[0]["url"] == "https://it.jooble.org/jdp/123456"


def test_normalize_jooble_result_output_schema():
    job = jooble_jobs.normalize_jooble_result(
        {
            "title": "Back office part time",
            "company": "Acme",
            "location": "Napoli",
            "url": "https://it.jooble.org/jdp/123456?utm_source=x",
            "snippet": "Tempo parziale ufficio",
        },
        "back office Napoli part time",
        found_at="2026-06-29T00:00:00+00:00",
    )

    assert set(job) == set(jooble_jobs.OUTPUT_FIELDS)
    assert job["source"] == "jooble"
    assert job["part_time"] is True
    assert job["found_at"] == "2026-06-29T00:00:00+00:00"
    assert "utm_source" not in job["url"]
