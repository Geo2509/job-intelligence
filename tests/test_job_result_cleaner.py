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
        {"title": "Data Entry Part Time", "url": "https://example.com/job/1"},
        {"title": "Offerte di lavoro data entry", "url": "https://example.com/list"},
        {"title": "Back Office", "url": "https://example.com/offerte?query=back-office"},
    ]

    cleaned = clean_results(jobs)

    assert cleaned == [
        {
            "title": "Data Entry Part Time",
            "url": "https://example.com/job/1",
            "url_result_type": "unknown",
            "result_type": "job",
        }
    ]


def test_clean_job_preserves_original_fields():
    job = {"title": "Data Entry", "company": "Acme", "url": "https://example.com/job/1"}

    assert clean_job(job) == {
        "title": "Data Entry",
        "company": "Acme",
        "url": "https://example.com/job/1",
        "url_result_type": "unknown",
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
        {"title": "Data Entry", "url": "https://example.com/job/1"},
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


def test_real_job_url_is_kept_even_when_title_has_search_prefix():
    job = {
        "title": "Offerte di lavoro Data Entry",
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
