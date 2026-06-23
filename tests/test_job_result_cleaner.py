import json

from src.job_result_cleaner import (
    clean_job,
    clean_results,
    clean_results_with_summary,
    detect_result_type,
    load_jobs,
    write_jobs,
)


def test_search_url_is_filtered():
    job = {"title": "Data Entry Napoli", "url": "https://example.com/jobs?q=data"}

    assert detect_result_type(job) == "search_page"
    assert clean_results([job]) == []


def test_search_path_is_filtered():
    job = {"title": "Back office", "url": "https://example.com/search/data-entry"}

    assert detect_result_type(job) == "search_page"
    assert clean_results([job]) == []


def test_category_url_is_filtered():
    job = {"title": "Data entry", "url": "https://example.com/cerca/data-entry"}

    assert detect_result_type(job) == "category_page"
    assert clean_results([job]) == []


def test_title_prefix_is_aggregator_page():
    job = {"title": "Più di 100 offerte di lavoro data entry", "url": "https://example.com/jobs"}

    assert detect_result_type(job) == "aggregator_page"
    assert clean_results([job]) == []


def test_snippet_terms_are_aggregator_page():
    job = {
        "title": "Data Entry",
        "url": "https://example.com/job/123",
        "snippet": "More than 100 jobs found in Napoli",
    }

    assert detect_result_type(job) == "aggregator_page"
    assert clean_results([job]) == []


def test_unknown_without_title_and_url_is_filtered():
    job = {"company": "Example"}

    assert detect_result_type(job) == "unknown"
    assert clean_results([job]) == []


def test_clean_results_exports_only_jobs_with_result_type():
    jobs = [
        {"title": "Data Entry Part Time", "url": "https://it.indeed.com/viewjob?jk=1"},
        {"title": "Offerte di lavoro data entry", "url": "https://example.com/list"},
        {"title": "Back Office", "url": "https://example.com/offerte?query=back-office"},
    ]

    cleaned = clean_results(jobs)

    assert cleaned == [
        {
            "title": "Data Entry Part Time",
            "url": "https://it.indeed.com/viewjob?jk=1",
            "url_result_type": "real_job",
            "result_type": "job",
        }
    ]


def test_clean_job_preserves_original_fields():
    job = {"title": "Data Entry", "company": "Acme", "url": "https://it.indeed.com/viewjob?jk=1"}

    assert clean_job(job) == {
        "title": "Data Entry",
        "company": "Acme",
        "url": "https://it.indeed.com/viewjob?jk=1",
        "url_result_type": "real_job",
        "result_type": "job",
    }


def test_load_and_write_jobs(tmp_path):
    output_path = tmp_path / "clean_jobs.json"
    jobs = [
        {
            "title": "Data Entry",
            "url": "https://example.com/job/1",
            "url_result_type": "unknown",
            "result_type": "job",
        }
    ]

    write_jobs(jobs, output_path)

    assert json.loads(output_path.read_text(encoding="utf-8")) == jobs
    assert load_jobs(output_path) == jobs


def test_cleaner_summary_counts_removed_result_types():
    jobs = [
        {"title": "Data Entry", "url": "https://it.indeed.com/viewjob?jk=1"},
        {"title": "Data Entry", "url": "https://example.com/search/data-entry"},
        {"title": "Data Entry", "url": "https://example.com/cerca/data-entry"},
        {"title": "Annunci data entry", "url": "https://example.com/list"},
        {"company": "Example"},
    ]

    cleaned, summary = clean_results_with_summary(jobs)

    assert len(cleaned) == 1
    assert summary == {
        "total_before": 5,
        "total_after": 1,
        "removed_search_page": 1,
        "removed_category_page": 1,
        "removed_aggregator_page": 1,
        "removed_article": 0,
        "removed_profile": 0,
        "removed_company_page": 0,
        "removed_career_page": 0,
        "removed_excluded_domain": 0,
        "removed_unknown": 1,
    }


def test_url_search_page_is_filtered_even_when_title_looks_like_job():
    job = {
        "title": "Data Entry Part Time Napoli",
        "url": "https://it.indeed.com/offerte-lavoro-data-entry-napoli",
    }

    assert clean_results([job]) == []
    cleaned = clean_job(job)
    assert cleaned["url_result_type"] == "search_page"
    assert cleaned["result_type"] == "search_page"


def test_real_job_url_is_kept_when_title_is_job_like():
    job = {
        "title": "Data Entry Napoli",
        "url": "https://it.indeed.com/viewjob?jk=abc123",
    }

    cleaned = clean_results([job])

    assert len(cleaned) == 1
    assert cleaned[0]["url_result_type"] == "real_job"
    assert cleaned[0]["result_type"] == "job"


def test_excluded_domain_is_filtered():
    job = {
        "title": "AI Trainer",
        "url": "https://simonebarbone.net/ai-trainer",
    }

    assert clean_results([job]) == []
    cleaned = clean_job(job)
    assert cleaned["url_result_type"] == "excluded_domain"
    assert cleaned["result_type"] == "excluded_domain"


def test_url_result_type_is_added_to_clean_job():
    cleaned = clean_job({
        "title": "Data Entry",
        "url": "https://it.jooble.org/jdp/123456",
    })

    assert cleaned["url_result_type"] == "real_job"
    assert cleaned["result_type"] == "job"


def test_captcha_job_is_filtered():
    job = {
        "title": "Online Data Entry Captcha Job",
        "url": "https://onlinedataentryjob.com/captcha-entry",
        "snippet": "Captcha entry work from home",
    }

    assert clean_results([job]) == []
    cleaned = clean_job(job)
    assert cleaned["url_result_type"] == "excluded_domain"
    assert cleaned["result_type"] == "article"


def test_comune_di_napoli_open_data_is_filtered():
    job = {
        "title": "Comune di Napoli Open Data",
        "url": "https://www.comune.napoli.it/opendata/dataset",
        "snippet": "Elenco dei dataset disponibili",
    }

    assert clean_results([job]) == []
    cleaned = clean_job(job)
    assert cleaned["url_result_type"] == "excluded_domain"
    assert cleaned["result_type"] == "article"


def test_terredamare_tourist_article_is_filtered():
    job = {
        "title": "Treasure in the Phlegrean Fields Monte di Procida",
        "url": "https://www.terredamare.com/monte-di-procida-travel-guide",
        "snippet": "Travel guide turismo article",
    }

    assert clean_results([job]) == []
    cleaned = clean_job(job)
    assert cleaned["url_result_type"] == "excluded_domain"
    assert cleaned["result_type"] == "article"


def test_fatturazione_elettronica_page_is_filtered():
    job = {
        "title": "Fatturazione elettronica e marcatempo",
        "url": "https://example.com/fatturazione-elettronica",
        "snippet": "Rilevazione presenze aziendali",
    }

    assert clean_results([job]) == []
    cleaned = clean_job(job)
    assert cleaned["url_result_type"] == "unknown"
    assert cleaned["result_type"] == "article"


def test_indeed_q_offerte_lavoro_with_vjk_is_filtered():
    job = {
        "title": "Data Entry Napoli",
        "url": "https://it.indeed.com/q-data-entry-offerte-lavoro.html?vjk=abc123",
    }

    assert clean_results([job]) == []
    cleaned = clean_job(job)
    assert cleaned["url_result_type"] == "search_page"
    assert cleaned["result_type"] == "search_page"


def test_indeed_viewjob_is_kept():
    job = {
        "title": "Data Entry Napoli",
        "url": "https://it.indeed.com/viewjob?jk=abc123",
    }

    cleaned = clean_results([job])

    assert len(cleaned) == 1
    assert cleaned[0]["url_result_type"] == "real_job"
    assert cleaned[0]["result_type"] == "job"


def test_jobbydoo_lavoro_page_is_filtered():
    job = {
        "title": "Data Entry Napoli",
        "url": "https://www.jobbydoo.it/lavoro-data-entry-napoli",
    }

    assert clean_results([job]) == []
    assert clean_job(job)["result_type"] == "search_page"


def test_jooble_rjdp_is_kept():
    job = {
        "title": "Back Office Napoli",
        "url": "https://it.jooble.org/rjdp/123456789",
    }

    cleaned = clean_results([job])

    assert len(cleaned) == 1
    assert cleaned[0]["url_result_type"] == "real_job"


def test_subito_category_is_filtered():
    job = {
        "title": "Offerte e annunci lavoro",
        "url": "https://www.subito.it/annunci-campania/vendita/offerte-lavoro/napoli/",
    }

    cleaned = clean_results([job])

    assert len(cleaned) == 1
    assert cleaned[0]["result_type"] == "search_page"
    assert clean_results([job], strict_job_detail_only=True) == []


def test_lidl_annunci_di_lavoro_is_filtered():
    job = {
        "title": "Annunci di lavoro Lidl",
        "url": "https://lavoro.lidl.it/annunci-di-lavoro",
    }

    cleaned = clean_results([job])

    assert len(cleaned) == 1
    assert cleaned[0]["result_type"] == "career_page"
    assert clean_results([job], strict_job_detail_only=True) == []


def test_lidl_punti_vendita_is_kept():
    job = {
        "title": "Addetto Vendite",
        "url": "https://lavoro.lidl.it/punti-vendita/addetto-vendite-napoli-123",
    }

    cleaned = clean_results([job])

    assert len(cleaned) == 1
    assert cleaned[0]["url_result_type"] == "real_job"


def test_blacklisted_news_school_sport_terms_are_filtered():
    jobs = [
        {
            "title": "Concorso scuola Napoli",
            "url": "https://it.indeed.com/viewjob?jk=school",
        },
        {
            "title": "Motocross campionato",
            "url": "https://it.jooble.org/rjdp/sport",
        },
        {
            "title": "Circolare istituto liceo",
            "url": "https://lavoro.lidl.it/punti-vendita/test",
        },
    ]

    assert clean_results(jobs) == []
    assert [clean_job(job)["result_type"] for job in jobs] == ["article", "article", "article"]


def test_clean_output_contains_only_real_jobs():
    jobs = [
        {"title": "Data Entry", "url": "https://it.indeed.com/viewjob?jk=1"},
        {"title": "Back Office", "url": "https://it.jooble.org/rjdp/2"},
        {"title": "Unknown", "url": "https://example.com/job/1"},
        {"title": "Search", "url": "https://www.jobbydoo.it/lavoro-data-entry"},
    ]

    cleaned = clean_results(jobs, strict_job_detail_only=True)

    assert len(cleaned) == 2
    assert {job["url_result_type"] for job in cleaned} == {"real_job"}
    assert {job["result_type"] for job in cleaned} == {"job"}


def test_soft_clean_keeps_trusted_career_and_search_pages():
    jobs = [
        {
            "title": "Subito offerte lavoro Napoli",
            "url": "https://www.subito.it/annunci-campania/vendita/offerte-lavoro/napoli/",
        },
        {
            "title": "Lidl annunci",
            "url": "https://lavoro.lidl.it/annunci-di-lavoro",
        },
        {
            "title": "Eurospin lavora con noi",
            "url": "https://www.eurospin.it/lavora-con-noi/",
        },
        {
            "title": "Randstad offerte lavoro",
            "url": "https://www.randstad.it/offerte-lavoro/",
        },
        {
            "title": "Manpower trova lavoro",
            "url": "https://www.manpower.it/it/trova-lavoro",
        },
    ]

    cleaned = clean_results(jobs)

    assert [job["title"] for job in cleaned] == [
        "Subito offerte lavoro Napoli",
        "Lidl annunci",
        "Eurospin lavora con noi",
        "Randstad offerte lavoro",
        "Manpower trova lavoro",
    ]


def test_strict_clean_removes_trusted_pages_except_real_jobs():
    jobs = [
        {"title": "Indeed job", "url": "https://it.indeed.com/viewjob?jk=1"},
        {
            "title": "Subito offerte lavoro Napoli",
            "url": "https://www.subito.it/annunci-campania/vendita/offerte-lavoro/napoli/",
        },
        {"title": "Lidl annunci", "url": "https://lavoro.lidl.it/annunci-di-lavoro"},
        {"title": "Eurospin lavora con noi", "url": "https://www.eurospin.it/lavora-con-noi/"},
        {"title": "Randstad offerte lavoro", "url": "https://www.randstad.it/offerte-lavoro/"},
        {"title": "Manpower trova lavoro", "url": "https://www.manpower.it/it/trova-lavoro"},
    ]

    cleaned = clean_results(jobs, strict_job_detail_only=True)

    assert [job["title"] for job in cleaned] == ["Indeed job"]


def test_known_garbage_is_removed_in_soft_and_strict_modes():
    jobs = [
        {
            "title": "Concorso scuola Napoli",
            "url": "https://www.randstad.it/offerte-lavoro/",
        },
        {
            "title": "Motocross campionato",
            "url": "https://www.subito.it/annunci-campania/vendita/offerte-lavoro/napoli/",
        },
        {
            "title": "Captcha job",
            "url": "https://it.indeed.com/viewjob?jk=scam",
            "snippet": "captcha entry",
        },
    ]

    assert clean_results(jobs) == []
    assert clean_results(jobs, strict_job_detail_only=True) == []
