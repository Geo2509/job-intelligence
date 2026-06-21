from src.job_url_patterns import classify_url, load_url_patterns


def patterns():
    return load_url_patterns("configs/job_url_patterns.yaml")


def test_indeed_viewjob_is_real_job():
    assert classify_url("https://it.indeed.com/viewjob?jk=abc123", patterns()) == "real_job"


def test_indeed_root_is_search_page():
    assert classify_url("https://it.indeed.com/", patterns()) == "search_page"


def test_indeed_offerte_lavoro_is_search_page():
    assert classify_url("https://it.indeed.com/offerte-lavoro-data-entry", patterns()) == "search_page"


def test_jooble_jdp_is_real_job():
    assert classify_url("https://it.jooble.org/jdp/123456", patterns()) == "real_job"


def test_jooble_lavoro_is_search_page():
    assert classify_url("https://it.jooble.org/lavoro-data-entry/napoli", patterns()) == "search_page"


def test_linkedin_jobs_view_is_real_job():
    assert classify_url("https://it.linkedin.com/jobs/view/123456", patterns()) == "real_job"


def test_linkedin_jobs_search_is_search_page():
    assert classify_url("https://it.linkedin.com/jobs/search?keywords=data", patterns()) == "search_page"


def test_glassdoor_job_listing_is_real_job():
    url = "https://www.glassdoor.it/job-listing/data-entry-acme-JV_IC123.htm"

    assert classify_url(url, patterns()) == "real_job"


def test_glassdoor_lavoro_is_search_page():
    assert classify_url("https://www.glassdoor.it/Lavoro/napoli-data-entry-lavoro-SRCH_IL.htm", patterns()) == "search_page"


def test_randstad_query_is_search_page():
    assert classify_url("https://www.randstad.it/offerte-lavoro/q-data-entry/", patterns()) == "search_page"


def test_general_excluded_domains_are_excluded():
    for domain in [
        "partitaiva.it",
        "duckinformatica.it",
        "ispazio.net",
        "tooliamo.com",
        "simonebarbone.net",
    ]:
        assert classify_url(f"https://{domain}/article", patterns()) == "excluded_domain"


def test_unknown_domain_is_unknown():
    assert classify_url("https://example.com/job/123", patterns()) == "unknown"
