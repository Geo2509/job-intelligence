import json
import zipfile

from src.url_pattern_debug import (
    build_url_pattern_debug_rows,
    export_url_pattern_debug,
    write_recommendations,
)


def job(title, url, collector="indeed", **extra):
    data = {
        "title": title,
        "url": url,
        "collector": collector,
        "source": collector,
        "location_fit": extra.pop("location_fit", "allowed_local"),
        "match_score": extra.pop("match_score", 90),
    }
    data.update(extra)
    return data


def test_url_pattern_debug_rows_include_unknown_and_duplicate():
    raw_jobs = [
        job("Indeed job", "https://it.indeed.com/viewjob?jk=1"),
        job("Indeed job duplicate", "https://it.indeed.com/viewjob?jk=1"),
        job("Unknown detail", "https://example.com/jobs/view/123", collector="gigroup"),
    ]
    classified_jobs = [
        {
            **raw_jobs[0],
            "result_type": "job",
            "url_result_type": "real_job",
            "history_status": "NEW",
        },
        {
            **raw_jobs[2],
            "result_type": "unknown",
            "url_result_type": "unknown",
        },
    ]

    rows = build_url_pattern_debug_rows(raw_jobs, classified_jobs, [classified_jobs[0]])

    assert rows[0]["matched_pattern"] == "indeed_job"
    assert rows[0]["classification"] == "accepted"
    assert rows[0]["final_status"] == "email"
    assert rows[1]["rejection_reason"] == "duplicate"
    assert rows[2]["detected_type"] == "unknown"
    assert rows[2]["rejection_reason"] == "unknown_pattern"


def test_url_pattern_debug_artifacts_are_created(tmp_path):
    rows = build_url_pattern_debug_rows([
        job("Unknown detail", "https://example.com/jobs/view/123", collector="gigroup"),
    ])
    output_path = tmp_path / "url_pattern_debug.json"

    export_url_pattern_debug(rows, output_path)

    assert output_path.exists()
    assert output_path.with_suffix(".xlsx").exists()
    assert (tmp_path / "unknown_urls.xlsx").exists()
    assert (tmp_path / "url_pattern_recommendations.md").exists()
    assert json.loads(output_path.read_text(encoding="utf-8"))[0]["collector"] == "gigroup"
    with zipfile.ZipFile(output_path.with_suffix(".xlsx")) as xlsx:
        workbook = xlsx.read("xl/workbook.xml").decode("utf-8")
    assert "Pattern Explorer" in workbook


def test_url_pattern_recommendations_include_repeated_paths(tmp_path):
    rows = [
        {
            "collector": "GiGroup",
            "url": "https://www.gigroup.it/offerta-lavoro/data-entry-1",
            "title": "Data Entry",
            "detected_type": "unknown",
            "matched_pattern": "none",
            "classification": "rejected",
            "final_status": "rejected",
            "rejection_reason": "unknown_pattern",
        },
        {
            "collector": "GiGroup",
            "url": "https://www.gigroup.it/offerta-lavoro/data-entry-2",
            "title": "Data Entry",
            "detected_type": "unknown",
            "matched_pattern": "none",
            "classification": "rejected",
            "final_status": "rejected",
            "rejection_reason": "unknown_pattern",
        },
    ]
    path = tmp_path / "recommendations.md"

    write_recommendations(rows, path)

    content = path.read_text(encoding="utf-8")
    assert "Collector: GiGroup" in content
    assert "`/offerta-lavoro/`: 2" in content
    assert "real_job:" in content
