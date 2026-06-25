import argparse
import csv
import json
from pathlib import Path

from src import job_collector_registry
from src.candidate_pool import score_value, write_xlsx
from src.job_aggregator import normalize_job
from src.job_result_cleaner import clean_job


DEFAULT_COLLECTOR = "gigroup"
DEFAULT_LIMIT = 5
DEFAULT_OUTPUT_DIR = "output/debug/gigroup"
CLASSIFICATION_FIELDS = [
    "source",
    "title",
    "company",
    "location",
    "url",
    "url_result_type",
    "result_type",
    "location_fit",
    "category",
    "score",
    "student_score",
    "candidate_score",
    "match_score",
    "rejection_reason",
]
SUMMARY_FIELDS = [
    "collector",
    "collected",
    "real_job",
    "search_page",
    "category_page",
    "career_page",
    "company_page",
    "article",
    "unknown",
    "allowed_local",
    "remote",
    "excluded_far",
    "unknown_location",
]


def collector_error(name):
    available = ", ".join(job_collector_registry.enabled_collectors())
    return f"Unsupported collector: {name}. Available collectors: {available}"


def run_collector(name, limit):
    plugin = job_collector_registry.get_collector(name)
    if plugin is None or not plugin.enabled:
        raise ValueError(collector_error(name))

    kwargs = dict(plugin.default_kwargs)
    if plugin.supports_limit:
        kwargs["limit"] = limit
    if plugin.supports_top:
        kwargs["top"] = limit
    if plugin.supports_campania_part_time_first:
        kwargs["campania_part_time_first"] = False
    return plugin.callable(**kwargs)


def debug_rejection_reason(job):
    result_type = job.get("result_type")
    if result_type == "search_page":
        return "search_page"
    if result_type == "category_page":
        return "category_page"
    if result_type == "career_page":
        return "career_page"
    if result_type == "company_page":
        return "company_page"
    if result_type == "article":
        return "article"
    if result_type == "excluded_domain":
        return "excluded_domain"
    if result_type == "unknown":
        return "unknown"
    if job.get("location_fit") == "excluded_far":
        return "excluded_far"
    if job.get("location_fit") == "unknown" and not bool(job.get("remote")):
        return "unknown_location"
    return "passed"


def classify_job(job, collector):
    normalized = normalize_job(job)
    normalized["collector"] = collector
    normalized["source"] = normalized.get("source") or collector
    classified = clean_job(normalized)
    classified["rejection_reason"] = debug_rejection_reason(classified)
    return classified


def classify_jobs(jobs, collector):
    return [classify_job(job, collector) for job in jobs]


def empty_summary(collector):
    summary = {field: 0 for field in SUMMARY_FIELDS if field != "collector"}
    summary["collector"] = collector
    return summary


def is_real_job(job):
    return job.get("result_type") == "job" and job.get("url_result_type") == "real_job"


def build_summary(collector, raw_jobs, classified_jobs):
    summary = empty_summary(collector)
    summary["collected"] = len(raw_jobs)
    for job in classified_jobs:
        result_type = job.get("result_type") or "unknown"
        if is_real_job(job):
            summary["real_job"] += 1
        elif result_type in summary:
            summary[result_type] += 1
        else:
            summary["unknown"] += 1

        location_fit = job.get("location_fit")
        if location_fit == "allowed_local":
            summary["allowed_local"] += 1
        elif location_fit == "remote" or bool(job.get("remote")):
            summary["remote"] += 1
        elif location_fit == "excluded_far":
            summary["excluded_far"] += 1
        elif location_fit == "unknown":
            summary["unknown_location"] += 1
    return summary


def write_json(data, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    count = len(data) if isinstance(data, list) else 1
    print(f"Saved {path}: {count} rows")


def classification_row(job):
    row = {}
    for field in CLASSIFICATION_FIELDS:
        if field in {"score", "student_score", "candidate_score", "match_score"}:
            row[field] = score_value(job, field)
        else:
            row[field] = job.get(field, "")
    return row


def write_classification_csv(rows, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CLASSIFICATION_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {path}: {len(rows)} rows")


def write_classification_xlsx(rows, output_path):
    table = [
        [
            row[field]
            for field in CLASSIFICATION_FIELDS
        ]
        for row in rows
    ]
    write_xlsx(table, CLASSIFICATION_FIELDS, output_path, sheet_name="url_classification")


def run_debug(collector=DEFAULT_COLLECTOR, limit=DEFAULT_LIMIT, output_dir=DEFAULT_OUTPUT_DIR):
    output_dir = Path(output_dir)
    raw_jobs = run_collector(collector, limit)
    classified_jobs = classify_jobs(raw_jobs, collector)
    classification_rows = [classification_row(job) for job in classified_jobs]
    summary = build_summary(collector, raw_jobs, classified_jobs)

    write_json(raw_jobs, output_dir / "raw_jobs.json")
    write_classification_csv(classification_rows, output_dir / "url_classification.csv")
    write_classification_xlsx(classification_rows, output_dir / "url_classification.xlsx")
    write_json(summary, output_dir / "summary.json")
    return {
        "raw_jobs": raw_jobs,
        "classified_jobs": classified_jobs,
        "summary": summary,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--collector", default=DEFAULT_COLLECTOR)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--output-dir", default=None)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    output_dir = args.output_dir or f"output/debug/{args.collector}"
    try:
        run_debug(args.collector, args.limit, output_dir)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
