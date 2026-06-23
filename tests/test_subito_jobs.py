from urllib.parse import parse_qs, urlsplit

from src.collectors import subito_jobs


def test_build_subito_search_url():
    url = subito_jobs.build_subito_search_url("lavoro part time Napoli")
    parsed = urlsplit(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "www.subito.it"
    assert parsed.path == "/annunci-campania/vendita/offerte-lavoro/"
    assert params["q"] == ["lavoro part time Napoli"]


def test_collector_does_not_crash_when_subito_blocks(monkeypatch):
    monkeypatch.setattr(subito_jobs, "fetch_direct_search", lambda url: None)
    monkeypatch.setattr(subito_jobs, "get_ddgs_class", lambda: None)

    jobs = subito_jobs.collect_jobs(limit=1, direct_pause_seconds=0)

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
                    "title": "Pulizie part time Napoli",
                    "href": "https://www.subito.it/offerte-lavoro/pulizie-part-time-napoli-123456.htm",
                    "body": "Tempo parziale mattina",
                }
            ]

    monkeypatch.setattr(subito_jobs, "get_ddgs_class", lambda: FakeDDGS)

    jobs = subito_jobs.collect_fallback_duckduckgo_jobs(limit=1)

    assert len(jobs) == 1
    assert jobs[0]["source"] == "subito"
    assert jobs[0]["part_time"] is True
    assert jobs[0]["priority_bucket"] == "campania_part_time"


def test_parse_subito_html_extracts_job_detail_links():
    page_html = """
    <html><body>
      <a href="/offerte-lavoro/cameriere-part-time-napoli-123456.htm">
        Cameriere part time Napoli
      </a>
      <a href="/annunci-campania/vendita/offerte-lavoro/napoli/">Categoria</a>
    </body></html>
    """

    jobs = subito_jobs.parse_subito_html(page_html, "cameriere part time Napoli")

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Cameriere part time Napoli"
    assert jobs[0]["url"] == "https://www.subito.it/offerte-lavoro/cameriere-part-time-napoli-123456.htm"
