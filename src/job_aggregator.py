import argparse
import csv
import hashlib
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from src.candidate_pool import (
    DEFAULT_COLLECTOR_STATS_PATH,
    DEFAULT_POOL_PATH,
    build_candidate_pool,
    build_collector_stats,
    classify_candidates,
    export_candidate_pool,
    export_collector_stats,
)
from src.candidate_profile import calculate_match_score, evaluate_candidate_score
from src.job_collector_registry import enabled_collectors, get_collector
from src.job_matching import (
    combined_text,
    detect_category,
    detect_part_time,
    detect_priority_bucket,
    detect_remote,
    normalize_url,
    score_job,
)
from src.job_result_cleaner import clean_results_with_summary, print_cleaning_summary
from src.student_profile import detect_location_fit, evaluate_student_score, load_student_profile


DEFAULT_OUTPUT_PATH = "output/v2_jobs.json"
DEFAULT_HISTORY_PATH = "output/v2_sent_jobs_history.json"
DEFAULT_RUN_STATS_PATH = "output/v2_run_stats.json"
DEFAULT_LIMIT = 5
DEFAULT_TOP = 50
DEFAULT_SKIP_SEEN_DAYS = 7
DEFAULT_MAX_SEEN_REPEAT = 1
DEFAULT_MIN_REMOTE = 20
DEFAULT_MIN_HOSPITALITY = 20
DEFAULT_MIN_CLEANING = 15
DEFAULT_MIN_MAINTENANCE = 10
DEFAULT_MIN_DATA_OFFICE = 20
PRIORITY_ORDER = {
    "campania_part_time": 0,
    "remote_data": 1,
    "local_general": 2,
    "other": 3,
}
LOCATION_FIT_ORDER = {
    "allowed_local": 0,
    "remote": 0,
    "unknown": 1,
    "excluded_far": 2,
}
OUTPUT_FIELDS = [
    "title",
    "company",
    "location",
    "url",
    "source",
    "query",
    "remote",
    "part_time",
    "category",
    "priority_bucket",
    "location_fit",
    "student_score",
    "candidate_score",
    "match_score",
    "history_status",
    "score",
    "found_at",
]
RESULT_TYPE_OUTPUT_FIELDS = OUTPUT_FIELDS + ["result_type", "url_result_type"]
DATA_OFFICE_TERMS = [
    "data entry",
    "inserimento dati",
    "back office",
    "office",
    "ufficio",
    "excel",
    "google sheets",
]
HOSPITALITY_TERMS = [
    "hospitality",
    "hotel",
    "albergo",
    "restaurant",
    "ristorante",
    "barista",
    "cameriere",
    "cameriera",
    "cuoco",
    "receptionist",
    "sala",
    "turismo",
]
CLEANING_TERMS = ["cleaning", "cleaner", "pulizie", "addetto pulizie", "addetta pulizie"]
MAINTENANCE_TERMS = [
    "maintenance",
    "manutenzione",
    "manutentore",
    "tecnico manutenzione",
    "elettricista",
    "idraulico",
]


def parse_collectors(value):
    if value is None:
        return enabled_collectors()
    return [
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    ]


def run_collector(name, limit, top, campania_part_time_first):
    plugin = get_collector(name)
    if plugin is None:
        print(f"Unknown collector skipped: {name}")
        return []
    if not plugin.enabled:
        print(f"Disabled collector skipped: {name}")
        return []

    try:
        kwargs = dict(plugin.default_kwargs)
        if plugin.supports_limit:
            kwargs["limit"] = limit
        if plugin.supports_top:
            kwargs["top"] = top
        if plugin.supports_campania_part_time_first:
            kwargs["campania_part_time_first"] = campania_part_time_first
        return plugin.callable(**kwargs)
    except Exception as exc:
        print(f"Collector failed: {name} | {exc}")
        return []


def normalize_job(job, include_profile_scores=True):
    job = dict(job)
    title = job.get("title", "")
    company = job.get("company", "")
    location = job.get("location", "")
    query = job.get("query", "")
    snippet = " ".join([str(company or ""), str(location or "")])
    searchable = combined_text(title, " ".join([snippet, query]), "")

    job["url"] = normalize_url(job.get("url", ""))
    job["company"] = company or ""
    job["location"] = location or ""
    job["remote"] = bool(job.get("remote")) or detect_remote(title, snippet, query)
    job["part_time"] = bool(job.get("part_time")) or detect_part_time(title, snippet, query)
    job["category"] = job.get("category") or detect_category(title, snippet, query)
    job["score"] = int(job.get("score") or score_job(title, snippet, query))
    job["location_fit"] = detect_location_fit(job, load_student_profile())
    if include_profile_scores:
        job["student_score"] = int(evaluate_student_score(job))
        job["candidate_score"] = int(evaluate_candidate_score(job))
        job["match_score"] = calculate_match_score(job["student_score"], job["candidate_score"])
    job["priority_bucket"] = detect_priority_bucket(
        searchable,
        job["part_time"],
        job["remote"],
    )
    job["found_at"] = job.get("found_at") or datetime.now(timezone.utc).isoformat()
    return job


def aggregator_dedup_key(job):
    if job.get("url"):
        return normalize_url(job["url"])
    return "|".join([
        str(job.get("title", "")).strip().lower(),
        str(job.get("company", "")).strip().lower(),
        str(job.get("location", "")).strip().lower(),
    ])


def deduplicate_jobs(jobs):
    deduped = []
    seen = set()
    for job in jobs:
        key = aggregator_dedup_key(job)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(job)
    return deduped


def location_fit_order(job):
    location_fit = job.get("location_fit")
    if not location_fit and bool(job.get("remote")):
        location_fit = "remote"
    return LOCATION_FIT_ORDER.get(location_fit or "unknown", 1)


def sort_jobs(jobs):
    return sorted(
        jobs,
        key=lambda job: (
            history_status_order(job),
            -int(job.get("match_score") or 0),
            -int(job.get("student_score") or 0),
            -int(job.get("candidate_score") or 0),
            -int(job.get("score") or 0),
        ),
    )


def sort_by_score(jobs):
    return sorted(
        jobs,
        key=lambda job: (
            history_status_order(job),
            -int(job.get("match_score") or 0),
            -int(job.get("student_score") or 0),
            -int(job.get("candidate_score") or 0),
            -int(job.get("score") or 0),
        ),
    )


def history_status_order(job):
    return {
        "NEW": 0,
        "UPDATED": 1,
        "RESURFACED": 2,
        "SEEN": 3,
    }.get(str(job.get("history_status") or ""), 4)


def add_profile_scores(jobs):
    scored = []
    for job in jobs:
        job = dict(job)
        job["location_fit"] = job.get("location_fit") or detect_location_fit(job, load_student_profile())
        job["student_score"] = int(evaluate_student_score(job))
        job["candidate_score"] = int(evaluate_candidate_score(job))
        job["match_score"] = calculate_match_score(job["student_score"], job["candidate_score"])
        scored.append(job)
    return scored


def stable_hash(parts):
    normalized_parts = [
        str(part or "").strip().lower()
        for part in parts
    ]
    payload = json.dumps(normalized_parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def job_history_key(job):
    if job.get("url"):
        return normalize_url(job["url"])
    return "|".join([
        str(job.get("source", "") or ""),
        str(job.get("title", "") or ""),
        str(job.get("company", "") or ""),
        str(job.get("location", "") or ""),
    ])


def job_id(job):
    return stable_hash([job_history_key(job)])


def content_hash(job):
    return stable_hash([
        job.get("title", ""),
        job.get("company", ""),
        job.get("location", ""),
        job.get("category", ""),
        job.get("match_score", ""),
        normalize_url(job.get("url", "")),
    ])


def parse_timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def load_sent_history(path=DEFAULT_HISTORY_PATH):
    history_path = Path(path)
    if not history_path.exists():
        return {}
    data = json.loads(history_path.read_text(encoding="utf-8") or "[]")
    if isinstance(data, dict):
        records = data.values()
    elif isinstance(data, list):
        records = data
    else:
        raise ValueError(f"Expected a JSON list or mapping in {history_path}")
    return {
        str(record.get("job_id")): record
        for record in records
        if isinstance(record, dict) and record.get("job_id")
    }


def write_sent_history(history, path=DEFAULT_HISTORY_PATH):
    history_path = Path(path)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    records = sorted(
        history.values(),
        key=lambda record: (
            str(record.get("last_sent") or ""),
            str(record.get("source") or ""),
            str(record.get("title") or ""),
        ),
        reverse=True,
    )
    history_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {history_path}: {len(records)} rows")


def classify_history_status(job, history_record, now=None, skip_seen_days=DEFAULT_SKIP_SEEN_DAYS):
    if history_record is None:
        return "NEW"
    if history_record.get("content_hash") != content_hash(job):
        return "UPDATED"

    now = now or datetime.now(timezone.utc)
    last_sent = parse_timestamp(history_record.get("last_sent"))
    if last_sent and last_sent.tzinfo is None:
        last_sent = last_sent.replace(tzinfo=timezone.utc)
    if last_sent and now - last_sent >= timedelta(days=skip_seen_days):
        return "RESURFACED"
    return "SEEN"


def annotate_history_status(jobs, history, now=None, skip_seen_days=DEFAULT_SKIP_SEEN_DAYS):
    annotated = []
    for job in jobs:
        job = dict(job)
        current_job_id = job_id(job)
        job["job_id"] = current_job_id
        job["content_hash"] = content_hash(job)
        job["history_status"] = classify_history_status(
            job,
            history.get(current_job_id),
            now=now,
            skip_seen_days=skip_seen_days,
        )
        annotated.append(job)
    return annotated


def filter_history_jobs(jobs, include_seen=False, max_seen_repeat=DEFAULT_MAX_SEEN_REPEAT):
    filtered = []
    seen_included = 0
    seen_skipped = 0
    for job in jobs:
        status = job.get("history_status")
        if status == "SEEN" and not include_seen:
            seen_skipped += 1
            continue
        if status == "SEEN" and include_seen:
            if seen_included >= max_seen_repeat:
                seen_skipped += 1
                continue
            seen_included += 1
        filtered.append(job)
    return filtered, seen_skipped


def history_status_counts(jobs):
    return {
        "new_jobs": sum(1 for job in jobs if job.get("history_status") == "NEW"),
        "updated_jobs": sum(1 for job in jobs if job.get("history_status") == "UPDATED"),
        "resurfaced_jobs": sum(1 for job in jobs if job.get("history_status") == "RESURFACED"),
    }


def update_sent_history(history, jobs, sent_at=None):
    sent_at = sent_at or datetime.now(timezone.utc).isoformat()
    updated = dict(history)
    for job in jobs:
        current_job_id = job.get("job_id") or job_id(job)
        previous = updated.get(current_job_id, {})
        first_seen = previous.get("first_seen") or job.get("found_at") or sent_at
        updated[current_job_id] = {
            "job_id": current_job_id,
            "url": normalize_url(job.get("url", "")),
            "title": job.get("title", ""),
            "source": job.get("source", ""),
            "first_seen": first_seen,
            "last_seen": sent_at,
            "last_sent": sent_at,
            "sent_count": int(previous.get("sent_count") or 0) + 1,
            "content_hash": job.get("content_hash") or content_hash(job),
            "match_score": int(job.get("match_score") or 0),
        }
    return updated


def empty_run_stats():
    return {
        "total_candidates": 0,
        "after_cleaning": 0,
        "candidate_pool_jobs": 0,
        "removed_far": 0,
        "removed_unknown": 0,
        "new_jobs": 0,
        "updated_jobs": 0,
        "seen_skipped": 0,
        "resurfaced_jobs": 0,
        "email_jobs": 0,
    }


def write_run_stats(stats, path=DEFAULT_RUN_STATS_PATH):
    stats_path = Path(path)
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {stats_path}")


def drop_far_location_jobs(jobs):
    return [
        job
        for job in jobs
        if job.get("location_fit") != "excluded_far"
    ]


def drop_unknown_location_jobs(jobs):
    return [
        job
        for job in jobs
        if job.get("location_fit") != "unknown" or bool(job.get("remote"))
    ]


def category_text(job):
    return combined_text(
        job.get("title", ""),
        " ".join([
            str(job.get("company", "") or ""),
            str(job.get("location", "") or ""),
            str(job.get("category", "") or ""),
        ]),
        job.get("query", ""),
    )


def has_any(text, terms):
    return any(term in text for term in terms)


def is_remote_job(job):
    return job.get("priority_bucket") == "remote_data" or bool(job.get("remote"))


def is_data_office_job(job):
    category = str(job.get("category", "") or "").lower()
    if category in {"data_office", "campania_part_time_data", "data_entry"}:
        return True
    return has_any(category_text(job), DATA_OFFICE_TERMS)


def is_hospitality_job(job):
    category = str(job.get("category", "") or "").lower()
    if category in {"hospitality", "hotel", "restaurant"}:
        return True
    return has_any(category_text(job), HOSPITALITY_TERMS)


def is_cleaning_job(job):
    category = str(job.get("category", "") or "").lower()
    if category in {"cleaning", "pulizie"}:
        return True
    return has_any(category_text(job), CLEANING_TERMS)


def is_maintenance_job(job):
    category = str(job.get("category", "") or "").lower()
    if category in {"maintenance", "manutenzione"}:
        return True
    return has_any(category_text(job), MAINTENANCE_TERMS)


def is_not_far_location(job):
    return job.get("location_fit") != "excluded_far"


def balanced_top(
    jobs,
    top=DEFAULT_TOP,
    min_remote=DEFAULT_MIN_REMOTE,
    min_hospitality=DEFAULT_MIN_HOSPITALITY,
    min_cleaning=DEFAULT_MIN_CLEANING,
    min_maintenance=DEFAULT_MIN_MAINTENANCE,
    min_data_office=DEFAULT_MIN_DATA_OFFICE,
):
    selected = []
    selected_keys = set()

    def add_jobs(candidates, quota):
        for job in sort_by_score(candidates):
            if len(selected) >= top or quota <= 0:
                return
            key = aggregator_dedup_key(job)
            if key in selected_keys:
                continue
            selected.append(job)
            selected_keys.add(key)
            quota -= 1

    quota_groups = [
        (is_remote_job, min_remote),
        (is_data_office_job, min_data_office),
        (is_hospitality_job, min_hospitality),
        (is_cleaning_job, min_cleaning),
        (is_maintenance_job, min_maintenance),
    ]
    for predicate, quota in quota_groups:
        add_jobs([job for job in jobs if predicate(job) and is_not_far_location(job)], quota)

    add_jobs(jobs, top - len(selected))
    return sort_jobs(selected)[:top]


def aggregate_jobs(
    collector_names=None,
    limit=DEFAULT_LIMIT,
    top=DEFAULT_TOP,
    campania_part_time_first=False,
    clean_results=False,
    email_clean_results=False,
    strict_job_detail_only=False,
    drop_far_locations=False,
    drop_unknown_locations=False,
    history_path=None,
    skip_seen_days=DEFAULT_SKIP_SEEN_DAYS,
    max_seen_repeat=DEFAULT_MAX_SEEN_REPEAT,
    include_seen=False,
    return_stats=False,
    return_artifacts=False,
    min_remote=DEFAULT_MIN_REMOTE,
    min_hospitality=DEFAULT_MIN_HOSPITALITY,
    min_cleaning=DEFAULT_MIN_CLEANING,
    min_maintenance=DEFAULT_MIN_MAINTENANCE,
    min_data_office=DEFAULT_MIN_DATA_OFFICE,
):
    jobs = []
    stats = empty_run_stats()
    collected_counts = {}
    collector_names = collector_names or enabled_collectors()
    should_clean_results = clean_results or email_clean_results or strict_job_detail_only
    for name in collector_names:
        collector_jobs = run_collector(name, limit, top, campania_part_time_first)
        print(f"Collector {name} returned: {len(collector_jobs)} jobs")
        collected_counts[name] = len(collector_jobs)
        jobs.extend(
            {
                **normalize_job(job, include_profile_scores=not should_clean_results),
                "collector": name,
            }
            for job in collector_jobs
        )

    stats["total_candidates"] = len(jobs)
    jobs = deduplicate_jobs(jobs)
    history = load_sent_history(history_path) if history_path else {}
    if return_artifacts:
        candidate_candidates = add_profile_scores(classify_candidates(jobs))
        candidate_candidates = annotate_history_status(
            candidate_candidates,
            history,
            skip_seen_days=skip_seen_days,
        )
    else:
        candidate_candidates = []
    if should_clean_results:
        jobs, summary = clean_results_with_summary(
            jobs,
            strict_job_detail_only=strict_job_detail_only,
            email_clean_results=email_clean_results,
        )
        print_cleaning_summary(summary)
        stats["after_cleaning"] = len(jobs)
        if drop_far_locations:
            before_drop = len(jobs)
            jobs = drop_far_location_jobs(jobs)
            stats["removed_far"] = before_drop - len(jobs)
            print(f"Removed excluded_far location: {stats['removed_far']}")
        if drop_unknown_locations:
            before_drop = len(jobs)
            jobs = drop_unknown_location_jobs(jobs)
            stats["removed_unknown"] = before_drop - len(jobs)
            print(f"Removed unknown non-remote location: {stats['removed_unknown']}")
        jobs = add_profile_scores(jobs)
    else:
        stats["after_cleaning"] = len(jobs)
        if drop_far_locations:
            before_drop = len(jobs)
            jobs = drop_far_location_jobs(jobs)
            stats["removed_far"] = before_drop - len(jobs)
        if drop_unknown_locations:
            before_drop = len(jobs)
            jobs = drop_unknown_location_jobs(jobs)
            stats["removed_unknown"] = before_drop - len(jobs)

    if history_path:
        jobs = annotate_history_status(jobs, history, skip_seen_days=skip_seen_days)
        status_counts = history_status_counts(jobs)
        stats.update(status_counts)
        jobs, seen_skipped = filter_history_jobs(
            jobs,
            include_seen=include_seen,
            max_seen_repeat=max_seen_repeat,
        )
        stats["seen_skipped"] = seen_skipped

    jobs = sort_jobs(jobs)
    jobs = balanced_top(
        jobs,
        top=top,
        min_remote=min_remote,
        min_hospitality=min_hospitality,
        min_cleaning=min_cleaning,
        min_maintenance=min_maintenance,
        min_data_office=min_data_office,
    )
    stats["email_jobs"] = len(jobs)
    if return_artifacts:
        candidate_pool = build_candidate_pool(candidate_candidates, jobs, history)
        collector_stats = build_collector_stats(collected_counts, candidate_candidates, jobs)
        stats["candidate_pool_jobs"] = len(candidate_pool)
        stats["collector_stats"] = collector_stats
        stats["collector_contribution"] = {
            row["collector"]: row["email_jobs"]
            for row in collector_stats
        }
        return jobs, stats, {
            "candidate_pool": candidate_pool,
            "collector_stats": collector_stats,
        }
    if return_stats:
        return jobs, stats
    return jobs


def write_json(jobs, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {path}: {len(jobs)} rows")


def sibling_output_path(output_path, suffix):
    return Path(output_path).with_suffix(suffix)


def output_fields_for_jobs(jobs):
    if any("result_type" in job for job in jobs):
        return RESULT_TYPE_OUTPUT_FIELDS
    return OUTPUT_FIELDS


def write_csv(jobs, output_path):
    path = sibling_output_path(output_path, ".csv")
    output_fields = output_fields_for_jobs(jobs)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields)
        writer.writeheader()
        for job in jobs:
            writer.writerow({field: job.get(field, "") for field in output_fields})
    print(f"Saved {path}: {len(jobs)} rows")


def write_xlsx(jobs, output_path):
    path = sibling_output_path(output_path, ".xlsx")
    output_fields = output_fields_for_jobs(jobs)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [output_fields] + [
        [str(job.get(field, "")) for field in output_fields]
        for job in jobs
    ]
    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            cell_ref = f"{column_letter(column_index)}{row_index}"
            cells.append(
                f'<c r="{cell_ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
            )
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        '</worksheet>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as xlsx:
        xlsx.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        xlsx.writestr("_rels/.rels", ROOT_RELS_XML)
        xlsx.writestr("xl/workbook.xml", WORKBOOK_XML)
        xlsx.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS_XML)
        xlsx.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    print(f"Saved {path}: {len(jobs)} rows")


def column_letter(index):
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
ROOT_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
WORKBOOK_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="v2_jobs" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""
WORKBOOK_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""


def export_jobs(jobs, output_path=DEFAULT_OUTPUT_PATH):
    write_json(jobs, output_path)
    write_csv(jobs, output_path)
    write_xlsx(jobs, output_path)


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--collectors", default=None)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--candidate-pool-output", default=DEFAULT_POOL_PATH)
    parser.add_argument("--collector-stats-output", default=DEFAULT_COLLECTOR_STATS_PATH)
    parser.add_argument("--history-path", default=DEFAULT_HISTORY_PATH)
    parser.add_argument("--run-stats-path", default=DEFAULT_RUN_STATS_PATH)
    parser.add_argument("--skip-seen-days", type=int, default=DEFAULT_SKIP_SEEN_DAYS)
    parser.add_argument("--max-seen-repeat", type=int, default=DEFAULT_MAX_SEEN_REPEAT)
    parser.add_argument("--include-seen", choices=["false", "true"], default="false")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP)
    parser.add_argument("--campania-part-time-first", action="store_true")
    parser.add_argument("--clean-results", action="store_true")
    parser.add_argument("--email-clean-results", action="store_true")
    parser.add_argument("--strict-job-detail-only", action="store_true")
    parser.add_argument("--drop-far-locations", action="store_true")
    parser.add_argument("--drop-unknown-locations", action="store_true")
    parser.add_argument("--min-remote", type=int, default=DEFAULT_MIN_REMOTE)
    parser.add_argument("--min-hospitality", type=int, default=DEFAULT_MIN_HOSPITALITY)
    parser.add_argument("--min-cleaning", type=int, default=DEFAULT_MIN_CLEANING)
    parser.add_argument("--min-maintenance", type=int, default=DEFAULT_MIN_MAINTENANCE)
    parser.add_argument("--min-data-office", type=int, default=DEFAULT_MIN_DATA_OFFICE)
    return parser.parse_args(argv)


def main():
    args = parse_args()
    jobs, stats, artifacts = aggregate_jobs(
        parse_collectors(args.collectors),
        limit=args.limit,
        top=args.top,
        campania_part_time_first=args.campania_part_time_first,
        clean_results=args.clean_results,
        email_clean_results=args.email_clean_results,
        strict_job_detail_only=args.strict_job_detail_only,
        drop_far_locations=args.drop_far_locations,
        drop_unknown_locations=args.drop_unknown_locations,
        history_path=args.history_path,
        skip_seen_days=args.skip_seen_days,
        max_seen_repeat=args.max_seen_repeat,
        include_seen=args.include_seen == "true",
        return_stats=True,
        return_artifacts=True,
        min_remote=args.min_remote,
        min_hospitality=args.min_hospitality,
        min_cleaning=args.min_cleaning,
        min_maintenance=args.min_maintenance,
        min_data_office=args.min_data_office,
    )
    export_jobs(jobs, args.output)
    export_candidate_pool(artifacts["candidate_pool"], args.candidate_pool_output)
    export_collector_stats(artifacts["collector_stats"], args.collector_stats_output)
    history = load_sent_history(args.history_path)
    history = update_sent_history(history, jobs)
    write_sent_history(history, args.history_path)
    write_run_stats(stats, args.run_stats_path)


if __name__ == "__main__":
    main()
