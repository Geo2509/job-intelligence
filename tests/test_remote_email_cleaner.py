from src.remote_email_cleaner import classify_remote_email_candidate, is_remote_email_eligible


def test_search_page_rejected():
    job = {
        "title": "Top 97 Data Annotation Remote Jobs (Hiring Now) | Indeed.com",
        "url": "https://www.indeed.com/jobs?q=data+annotation+remote",
        "description": "Remote data annotation jobs found.",
    }

    classified = classify_remote_email_candidate(job)

    assert classified["remote_email_result_type"] == "search_page"
    assert classified["remote_email_rejection_reason"] == "search_page"
    assert is_remote_email_eligible(job) is False


def test_language_mismatch_rejected_even_when_snippet_mentions_russian():
    job = {
        "title": "Data Annotator - Korean Language - Virtual Vocations",
        "url": "https://www.virtualvocations.com/job/123",
        "description": "Remote data annotation. Russian language appears in related jobs.",
    }

    classified = classify_remote_email_candidate(job)

    assert classified["remote_email_result_type"] == "language_mismatch"
    assert classified["remote_email_rejection_reason"] == "language_mismatch"
    assert is_remote_email_eligible(job) is False


def test_real_ukrainian_remote_job_accepted():
    job = {
        "title": "Ukrainian Language Specialist",
        "url": "https://example.com/jobs/ukrainian-language-specialist",
        "description": "Remote data annotation and data labeling project.",
    }

    classified = classify_remote_email_candidate(job)

    assert classified["remote_email_result_type"] == "job"
    assert classified["remote_email_rejection_reason"] == ""
    assert "Remote" in classified["remote_match_summary"]
    assert "Ukrainian language" in classified["remote_match_summary"]
    assert "AI Data Annotation" in classified["remote_match_summary"]
