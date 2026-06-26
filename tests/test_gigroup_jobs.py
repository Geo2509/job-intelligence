from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

from src import job_aggregator
from src.collectors import gigroup_jobs
from src.job_collector_registry import COLLECTOR_REGISTRY, get_collector


def test_build_gigroup_search_url():
    url = gigroup_jobs.build_gigroup_search_url("back office Napoli")
    parsed = urlsplit(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "www.gigroup.it"
    assert parsed.path == "/offerte-lavoro/"
    assert params["job"] == ["back office"]
    assert params["placeOfWork"] == ["Napoli"]
    assert params["radius"] == ["25"]


def test_registry_contains_gigroup():
    plugin = get_collector("gigroup")

    assert "gigroup" in COLLECTOR_REGISTRY
    assert plugin.name == "gigroup"
    assert plugin.enabled is True
    assert plugin.module == "src.collectors.gigroup_jobs"
    assert plugin.function == "collect_jobs"
    assert callable(plugin.callable)


def test_collector_does_not_crash_when_gigroup_blocks(monkeypatch):
    monkeypatch.setattr(gigroup_jobs, "fetch_direct_search", lambda url: None)
    monkeypatch.setattr(gigroup_jobs, "get_ddgs_class", lambda: None)

    jobs = gigroup_jobs.collect_jobs(limit=1, direct_pause_seconds=0)

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
                    "href": "https://www.gigroup.it/offerte-lavoro/dettaglio-offerta/back-office-part-time-napoli_123/",
                    "body": "Tempo parziale ufficio",
                }
            ]

    monkeypatch.setattr(gigroup_jobs, "get_ddgs_class", lambda: FakeDDGS)
    monkeypatch.setattr(gigroup_jobs, "fetch_detail_page", lambda url: None)

    jobs = gigroup_jobs.collect_fallback_duckduckgo_jobs(limit=1)

    assert len(jobs) == 1
    assert jobs[0]["source"] == "gigroup"
    assert jobs[0]["part_time"] is True
    assert jobs[0]["student_score"] >= 90
    assert jobs[0]["candidate_score"] > 0
    assert jobs[0]["match_score"] > 0
    assert jobs[0]["priority_bucket"] == "campania_part_time"


def test_fallback_duckduckgo_skips_search_urls(monkeypatch):
    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def text(self, query, region, safesearch, max_results):
            return [
                {
                    "title": "Offerte lavoro Napoli",
                    "href": "https://www.gigroup.it/offerte-lavoro/?q=Napoli",
                    "body": "Search results",
                },
                {
                    "title": "Back office part time Napoli",
                    "href": "https://www.gigroup.it/offerte-lavoro-dettaglio/napoli-back-office-part-time/1323119/",
                    "body": "Tempo parziale ufficio",
                },
            ]

    monkeypatch.setattr(gigroup_jobs, "get_ddgs_class", lambda: FakeDDGS)
    monkeypatch.setattr(gigroup_jobs, "fetch_detail_page", lambda url: None)

    jobs = gigroup_jobs.collect_fallback_duckduckgo_jobs(limit=2)

    assert [job["url"] for job in jobs] == [
        "https://www.gigroup.it/offerte-lavoro-dettaglio/napoli-back-office-part-time/1323119"
    ]


def test_parse_gigroup_html_extracts_job_detail_links():
    page_html = """
    <html><body>
      <article class="ggp-job-item">
        <a itemprop="url"
           href="/offerte-lavoro-dettaglio/napoli-data-entry-part-time/1323119/"
           class="ggp-job-title-url"
           data-job='{"offerTitle":"Data entry part time Napoli","industry":"Office","professionalArea":"Back office","province":"Napoli"}'>
          <h2 class="ggp-job-item-title">Data entry part time Napoli</h2>
        </a>
        <span class="visually-hidden">Luogo di lavoro:</span><span>Napoli, NA, Campania</span>
      </article>
      <a href="/offerte-lavoro/?q=data-entry">Search page</a>
      <a href="/lavora-con-noi">Career page</a>
      <a href="https://it.mygigroup.com/members/jobs/seek/viewoffer/1323119">Candidati</a>
    </body></html>
    """

    jobs = gigroup_jobs.parse_gigroup_html(page_html, "data entry Napoli")

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Data entry part time Napoli"
    assert jobs[0]["location"] == "Napoli, NA, Campania"
    assert jobs[0]["url"] == (
        "https://www.gigroup.it/offerte-lavoro-dettaglio/"
        "napoli-data-entry-part-time/1323119"
    )


def test_parse_gigroup_html_tolerates_missing_optional_fields():
    page_html = """
    <html><body>
      <article class="ggp-job-item">
        <a href="/offerte-lavoro-dettaglio/napoli-magazziniere/1323120/">
          Magazziniere
        </a>
      </article>
    </body></html>
    """

    jobs = gigroup_jobs.parse_gigroup_html(page_html, "magazziniere Napoli")

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Magazziniere"
    assert jobs[0]["location"] == ""
    assert jobs[0]["url"] == "https://www.gigroup.it/offerte-lavoro-dettaglio/napoli-magazziniere/1323120"


def test_gigroup_job_detail_url_detection_filters_service_links():
    assert gigroup_jobs.is_gigroup_job_detail_url(
        "https://www.gigroup.it/offerte-lavoro-dettaglio/piove-di-sacco-padova-recruitment-consultant-senior/A1605/"
    )
    assert not gigroup_jobs.is_gigroup_job_detail_url("https://www.gigroup.it/offerte-lavoro/?q=Napoli")
    assert not gigroup_jobs.is_gigroup_job_detail_url("https://www.gigroup.it/offerte-lavoro/part-time-do/")
    assert not gigroup_jobs.is_gigroup_job_detail_url("https://it.mygigroup.com/members/jobs/seek/viewoffer/1323119")


def test_normalize_gigroup_result_output_schema():
    job = gigroup_jobs.normalize_gigroup_result(
        {
            "title": "Impiegato amministrativo part time",
            "company": "Gi Group",
            "location": "Napoli",
            "url": "https://www.gigroup.it/offerte-lavoro/dettaglio-offerta/impiegato-amministrativo-napoli_123/?utm_source=x",
            "snippet": "Tempo parziale back office",
        },
        "impiegato amministrativo Napoli",
        found_at="2026-06-24T00:00:00+00:00",
    )

    assert set(job) == set(gigroup_jobs.OUTPUT_FIELDS)
    assert job["source"] == "gigroup"
    assert job["part_time"] is True
    assert job["student_score"] >= 90
    assert job["candidate_score"] > 0
    assert job["match_score"] > 0
    assert job["location_fit"] == "allowed_local"
    assert job["found_at"] == "2026-06-24T00:00:00+00:00"
    assert "utm_source" not in job["url"]


def test_gigroup_detail_page_parsing_extracts_enrichment_fields():
    page_html = """
    <html><body>
      <section class="job-description">
        Back office data entry con Excel. Contratto: somministrazione.
        Orario di lavoro: part time. Luogo di lavoro: Napoli.
      </section>
    </body></html>
    """

    details = gigroup_jobs.parse_gigroup_detail_html(page_html)

    assert "Back office data entry" in details["description"]
    assert details["contract_type"] == "somministrazione"
    assert details["working_hours"] == "part time"
    assert details["location"] == "Napoli"


def test_gigroup_enriched_text_affects_category_remote_and_part_time(monkeypatch):
    detail_html = """
    <html><body>
      <section class="job-description">
        Inserimento dati e back office con Excel. Orario di lavoro: part time.
        Possibilita di smart working due giorni a settimana. Luogo di lavoro: Napoli.
      </section>
    </body></html>
    """
    monkeypatch.setattr(gigroup_jobs, "fetch_detail_page", lambda url: detail_html)
    base = gigroup_jobs.normalize_gigroup_result(
        {
            "title": "Addetto ufficio",
            "company": "Gi Group",
            "location": "",
            "url": "https://www.gigroup.it/offerte-lavoro-dettaglio/addetto-ufficio/1323120/",
            "snippet": "",
        },
        "part time Napoli",
        found_at="2026-06-24T00:00:00+00:00",
    )

    enriched = gigroup_jobs.enrich_gigroup_job(base)

    assert enriched["category"] == "data_entry"
    assert enriched["remote"] is True
    assert enriched["remote_reason"] == "description: smart working"
    assert enriched["part_time"] is True
    assert enriched["score"] > base["score"]


def test_aggregator_accepts_gigroup_collector(monkeypatch):
    plugin = replace(
        get_collector("gigroup"),
        callable=lambda **kwargs: [
            gigroup_jobs.normalize_gigroup_result(
                {
                    "title": "Back office part time Napoli",
                    "company": "Gi Group",
                    "location": "Napoli",
                    "url": "https://www.gigroup.it/offerte-lavoro/dettaglio-offerta/back-office-part-time-napoli_123/",
                    "snippet": "Tempo parziale ufficio",
                },
                "back office Napoli",
                found_at="2026-06-24T00:00:00+00:00",
            )
        ],
    )
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugin if name == "gigroup" else None)

    jobs = job_aggregator.aggregate_jobs(["gigroup"], limit=1, top=1)

    assert len(jobs) == 1
    assert jobs[0]["source"] == "gigroup"
