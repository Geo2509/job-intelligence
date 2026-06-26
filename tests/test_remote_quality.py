import pandas as pd

from scoring_jobs import calculate_score, enrich_remote_quality, remote_quality_signals
from src import job_aggregator, v2_email_report


def remote_job(title, **extra):
    job = {
        "title": title,
        "company": "Acme",
        "location": extra.pop("location", "Worldwide"),
        "description": extra.pop("description", ""),
        "source": extra.pop("source", "remotive"),
        "url": extra.pop("url", "https://example.com/job"),
        "query": extra.pop("query", ""),
    }
    job.update(extra)
    return job


def scored(title, **extra):
    row = remote_job(title, **extra)
    row.update(enrich_remote_quality(row))
    return calculate_score(pd.Series(row))


def test_scoring_dataframe_assignment_matches_returned_columns():
    df = pd.DataFrame([
        remote_job("AI Trainer remote", description="Worldwide LLM human feedback role"),
        remote_job("Data Annotation remote", description="US only"),
    ])
    quality_rows = df.apply(lambda row: pd.Series(remote_quality_signals(row)), axis=1)
    for column in quality_rows.columns:
        df[column] = quality_rows[column]

    score_columns = ["job_score", "score_reason", "positive_reason", "negative_reason"]
    df[score_columns] = df.apply(calculate_score, axis=1)[score_columns]

    assert df["job_score"].tolist()
    assert all(column in df for column in score_columns)


def test_remote_positive_ai_trainer_scores_high():
    result = scored("AI Trainer remote", description="Worldwide LLM human feedback role")

    assert result["job_score"] >= 100
    assert "AI Trainer" in result["positive_reason"]


def test_remote_positive_data_annotation_ukrainian_scores_high():
    result = scored("Data Annotation Ukrainian remote", description="Worldwide data labeling")

    assert result["job_score"] >= 120
    assert "AI Annotation" in result["positive_reason"] or "Languages" in result["positive_reason"]


def test_remote_positive_ocean_freight_analyst_scores_high():
    result = scored("Ocean Freight Operations Analyst remote", description="Europe shipping supply chain")

    assert result["job_score"] >= 100
    assert "Logistics" in result["positive_reason"]


def test_remote_positive_virtual_assistant_google_sheets_scores_high():
    result = scored("Virtual Assistant Google Sheets remote", description="Worldwide back office reporting")

    assert result["job_score"] >= 100
    assert "Virtual Assistant" in result["positive_reason"]


def test_remote_negative_senior_engineering_manager_scores_low():
    result = scored("Senior Engineering Manager remote", description="Worldwide staff engineer role")

    assert result["job_score"] < 70
    assert "excluded title" in result["negative_reason"] or "seniority" in result["negative_reason"]


def test_remote_negative_cyber_intelligence_scores_low():
    result = scored("Cyber Intelligence Analyst remote", description="SOC analyst security clearance")

    assert result["job_score"] < 70
    assert "irrelevant" in result["negative_reason"]


def test_remote_negative_country_restrictions_penalize():
    us = scored("Data Annotation remote", description="US only")
    brazil = scored("Data Annotation remote", description="Brazil only")
    worldwide = scored("Data Annotation remote", description="Worldwide")

    assert us["job_score"] < worldwide["job_score"]
    assert brazil["job_score"] < worldwide["job_score"]
    assert "country" in us["negative_reason"]


def test_remote_negative_medical_doctor_scores_low():
    result = scored("Medical Doctor remote", description="licensed physician")

    assert result["job_score"] < 70
    assert "medical" in result["negative_reason"]


def test_remote_quality_fields_feed_v2_remote_mode():
    item = job_aggregator.normalize_job(
        remote_job(
            "Ocean Freight Operations Analyst remote",
            description="Worldwide contract shipping dashboard role $30000 - $50000",
        ),
        search_profile="remote",
    )

    assert item["normalized_remote_category"] == "Logistics"
    assert item["country_restriction"] == "Worldwide"
    assert item["employment_type"] == "Contract"
    assert item["salary_min"] == 30000
    assert item["salary_max"] == 50000
    assert item["currency"] == "USD"
    assert item["match_score"] >= 80


def test_remote_email_renders_quality_fields_and_blocks():
    item = {
        **remote_job("AI Trainer remote"),
        "normalized_remote_category": "AI Training",
        "country_restriction": "Worldwide",
        "employment_type": "Freelance",
        "salary_text": "$20/hour",
        "candidate_score": 95,
        "match_score": 100,
        "positive_reason": "+45 AI Trainer",
        "negative_reason": "",
    }
    body = v2_email_report.build_email_html([item], search_profile="remote")

    assert "AI Training" in body
    assert "<strong>Country:</strong> Worldwide" in body
    assert "<strong>Employment:</strong> Freelance" in body
    assert "<strong>Positive reasons:</strong> +45 AI Trainer" in body
