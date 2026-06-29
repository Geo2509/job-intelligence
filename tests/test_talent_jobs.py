from urllib.parse import parse_qs, urlsplit

from src.collectors import talent_jobs


def test_build_talent_search_url():
    url = talent_jobs.build_talent_search_url("data entry Napoli part time")
    parsed = urlsplit(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "it.talent.com"
    assert parsed.path == "/jobs"
    assert params["k"] == ["data entry Napoli part time"]


def test_talent_detail_url_detection():
    assert talent_jobs.is_talent_job_detail_url("https://it.talent.com/view?id=abc123")
    assert talent_jobs.is_talent_job_detail_url("https://www.talent.com/view?id=abc123")
    assert not talent_jobs.is_talent_job_detail_url("https://it.talent.com/jobs?k=data-entry")
    assert not talent_jobs.is_talent_job_detail_url("https://it.talent.com/company/acme")


def test_fallback_duckduckgo_keeps_only_detail_urls(monkeypatch):
    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def text(self, query, region, safesearch, max_results):
            return [
                {
                    "title": "Data entry jobs in Napoli",
                    "href": "https://it.talent.com/jobs?k=data+entry&l=napoli",
                    "body": "Search results",
                },
                {
                    "title": "Data Entry Part Time",
                    "href": "https://it.talent.com/view?id=abc123",
                    "body": "Tempo parziale",
                },
            ]

    monkeypatch.setattr(talent_jobs, "get_ddgs_class", lambda: FakeDDGS)

    jobs = talent_jobs.collect_fallback_duckduckgo_jobs(limit=2)

    assert [job["url"] for job in jobs] == ["https://it.talent.com/view?id=abc123"]


def test_parse_talent_html_extracts_job_detail_links():
    page_html = """
    <html><body>
      <div data-new-id="abc123" data-testid="jobcard-container-abc123">
        <article>
          <h2 class="JobCard_title__X32Qk">Data entry part time Napoli</h2>
          <span class="JobCard_company__NmRol">Acme</span>
          <span class="JobCard_location__nmTtw">Napoli, Campania</span>
          <p class="JobCard_snippet__rqX60">
            Tempo parziale ufficio
            <a href="/view?id=abc123">Mostra di più</a>
          </p>
        </article>
      </div>
      <a href="/jobs?k=data-entry">Search page</a>
    </body></html>
    """

    jobs = talent_jobs.parse_talent_html(page_html, "data entry Napoli part time")

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Data entry part time Napoli"
    assert jobs[0]["url"] == "https://it.talent.com/view?id=abc123"
    assert jobs[0]["company"] == "Acme"
    assert jobs[0]["location"] == "Napoli, Campania"


def test_normalize_talent_result_output_schema():
    job = talent_jobs.normalize_talent_result(
        {
            "title": "Back office part time",
            "company": "Acme",
            "location": "Napoli",
            "url": "https://it.talent.com/view?id=abc123&utm_source=x",
            "snippet": "Tempo parziale ufficio",
        },
        "back office Napoli part time",
        found_at="2026-06-29T00:00:00+00:00",
    )

    assert set(job) == set(talent_jobs.OUTPUT_FIELDS)
    assert job["source"] == "talent"
    assert job["part_time"] is True
    assert job["found_at"] == "2026-06-29T00:00:00+00:00"
    assert "utm_source" not in job["url"]
