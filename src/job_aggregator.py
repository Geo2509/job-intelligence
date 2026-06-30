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
from src.collector_health import build_collector_health, export_collector_health
from src.job_collector_registry import enabled_collectors, get_collector
from src.job_matching import (
    combined_text,
    detect_category,
    detect_part_time,
    detect_priority_bucket,
    detect_remote,
    detect_remote_reason,
    normalize_url,
    score_job,
)
from src.job_result_cleaner import clean_results_with_summary, print_cleaning_summary
from src.student_profile import detect_location_fit, evaluate_student_score, load_student_profile
from src.url_pattern_debug import build_url_pattern_debug_rows, export_url_pattern_debug
from scoring_jobs import enrich_remote_quality


DEFAULT_OUTPUT_PATH = "output/v2_jobs.json"
DEFAULT_HISTORY_PATH = "output/v2_sent_jobs_history.json"
DEFAULT_RUN_STATS_PATH = "output/v2_run_stats.json"
REMOTE_OUTPUT_PATH = "output/v2_remote_jobs.json"
REMOTE_POOL_PATH = "output/v2_remote_candidate_pool.json"
REMOTE_HISTORY_PATH = "output/v2_remote_sent_jobs_history.json"
REMOTE_RUN_STATS_PATH = "output/v2_remote_run_stats.json"
LOCAL_STUDENT_PROFILE = "local_student"
REMOTE_PROFILE = "remote"
DEFAULT_LIMIT = 5
DEFAULT_TOP = 500
DEFAULT_SKIP_SEEN_DAYS = 7
DEFAULT_MAX_SEEN_REPEAT = 1
DEFAULT_EMAIL_TARGET = 50
DEFAULT_EMAIL_MIN_MATCH = 50
DEFAULT_ROTATION_DAYS = 7
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
    "description",
    "contract_type",
    "employment_type",
    "working_hours",
    "salary",
    "experience",
    "skills",
    "smart_working",
    "full_time",
    "url",
    "source",
    "query",
    "remote",
    "remote_reason",
    "part_time",
    "category",
    "normalized_category",
    "priority_bucket",
    "location_fit",
    "student_score",
    "candidate_score",
    "remote_score",
    "country_restriction",
    "employment_type",
    "salary_min",
    "salary_max",
    "currency",
    "salary_text",
    "normalized_remote_category",
    "positive_reason",
    "negative_reason",
    "match_score",
    "search_profile",
    "history_status",
    "last_sent",
    "sent_count",
    "days_since_last_sent",
    "rotation_eligible",
    "selection_reason",
    "selection_rejection_reason",
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
REMOTE_KEYWORDS = [
    "remote",
    "remoto",
    "full remote",
    "smart working",
    "lavoro da casa",
    "work from home",
    "home based",
    "da remoto",
    "online",
    "freelance",
    "contractor",
    "ai trainer",
    "ai annotator",
    "data annotator",
    "ai evaluator",
    "search evaluator",
    "data labeling",
    "data annotation",
    "transcription",
    "trascrizione",
    "virtual assistant",
    "assistente virtuale",
    "google sheets",
    "excel remote",
    "data processing",
    "data entry remoto",
    "customer support remote",
    "content reviewer",
    "moderation",
    "logistics remote",
]
REMOTE_BLOCKER_TERMS = ["onsite", "in sede", "presenza", "non remoto"]
REMOTE_BONUSES = [
    (30, ["ai trainer", "ai annotator", "data annotator"]),
    (30, ["transcription", "trascrizione"]),
    (25, ["data entry remote", "data entry remoto"]),
    (25, ["virtual assistant", "assistente virtuale"]),
    (25, ["google sheets", "excel remote"]),
    (20, ["customer support remote"]),
    (20, ["content reviewer", "moderation"]),
    (15, ["logistics remote"]),
    (15, ["python", "automation"]),
    (10, ["freelance", "contractor"]),
    (10, ["part-time", "part time", "tempo parziale"]),
]
REMOTE_PENALTIES = [
    (30, ["onsite"]),
    (30, ["in sede"]),
    (30, ["presenza"]),
    (30, ["non remoto"]),
    (20, ["italian c1 required", "italiano c1 richiesto"]),
    (20, ["english c1 required", "inglese c1 richiesto"]),
]


def parse_collectors(value):
    if value is None:
        return enabled_collectors()
    return [
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    ]


def run_collector(name, limit, top, campania_part_time_first, search_profile=LOCAL_STUDENT_PROFILE):
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
        if getattr(plugin, "supports_search_profile", False):
            kwargs["search_profile"] = search_profile
        return plugin.callable(**kwargs)
    except Exception as exc:
        print(f"Collector failed: {name} | {exc}")
        return []


def normalize_job(job, include_profile_scores=True, search_profile=LOCAL_STUDENT_PROFILE):
    job = dict(job)
    title = job.get("title", "")
    company = job.get("company", "")
    location = job.get("location", "")
    query = job.get("query", "")
    snippet = " ".join([
        str(job.get(field, "") or "")
        for field in (
            "description",
            "contract_type",
            "employment_type",
            "working_hours",
            "salary",
            "experience",
            "skills",
            "snippet",
            "summary",
            "body",
            "company",
            "location",
            "url",
        )
    ])
    searchable = combined_text(title, " ".join([snippet, str(job.get("category", "") or "")]), "")

    job["url"] = normalize_url(job.get("url", ""))
    job["company"] = company or ""
    job["location"] = location or ""
    job["remote"] = detect_remote(
        title,
        snippet,
        query,
        location=location,
        url=job["url"],
        description=job.get("description", ""),
    )
    job["remote_reason"] = detect_remote_reason(
        title,
        snippet,
        query,
        location=location,
        url=job["url"],
        description=job.get("description", ""),
    )
    job["part_time"] = detect_part_time(title, snippet, "")
    job["category"] = detect_category(title, snippet, query)
    job["normalized_category"] = job["category"]
    job["score"] = int(score_job(title, snippet, ""))
    job["location_fit"] = detect_location_fit(job, load_student_profile())
    job["search_profile"] = search_profile
    job.setdefault("remote_score", 0)
    if search_profile == REMOTE_PROFILE:
        job.update(enrich_remote_quality(job))
        if job.get("normalized_remote_category") and job["normalized_remote_category"] != "Other":
            job["category"] = job["normalized_remote_category"]
            job["normalized_category"] = job["category"]
    if include_profile_scores:
        job["student_score"] = int(evaluate_student_score(job))
        if is_unwanted_title_rejected(job):
            apply_unwanted_title_rejection(job)
        else:
            job["candidate_score"] = int(evaluate_candidate_score(job))
        apply_profile_scores(job, search_profile)
    job["priority_bucket"] = detect_priority_bucket(
        searchable,
        job["part_time"],
        job["remote"],
    )
    job["found_at"] = job.get("found_at") or datetime.now(timezone.utc).isoformat()
    return job


def remote_text(job):
    return combined_text(
        job.get("title", ""),
        " ".join([
            str(job.get("company", "") or ""),
            str(job.get("location", "") or ""),
            str(job.get("description", "") or ""),
            str(job.get("query", "") or ""),
            str(job.get("url", "") or ""),
            str(job.get("source", "") or ""),
        ]),
        "",
    )


def is_remote_related(job):
    return has_any(remote_text(job), REMOTE_KEYWORDS)


def has_remote_blocker(job):
    return has_any(remote_text(job), REMOTE_BLOCKER_TERMS)


def filter_remote_jobs(jobs):
    return [
        job
        for job in jobs
        if is_remote_related(job) and not has_remote_blocker(job)
    ]


def calculate_remote_score(job):
    text = remote_text(job)
    score = int(job.get("candidate_score") or 0)
    for points, terms in REMOTE_BONUSES:
        if has_any(text, terms):
            score += points
    for points, terms in REMOTE_PENALTIES:
        if has_any(text, terms):
            score -= points
    score += int(job.get("remote_score_delta") or 0)
    return score


def is_unwanted_title_rejected(job):
    return (
        str(job.get("profile_reason") or "").lower() == "unwanted_title"
        and job.get("profile_match") is False
    ) or str(job.get("selection_rejection_reason") or "").lower() == "unwanted_title"


def apply_unwanted_title_rejection(job):
    job["profile_match"] = False
    job["profile_reason"] = "unwanted_title"
    job["selection_rejection_reason"] = "unwanted_title"
    job["student_score"] = 0
    job["candidate_score"] = 0
    job["match_score"] = 0
    return job


def apply_profile_scores(job, search_profile=LOCAL_STUDENT_PROFILE):
    job["search_profile"] = search_profile
    if is_unwanted_title_rejected(job):
        return apply_unwanted_title_rejection(job)
    if search_profile == REMOTE_PROFILE:
        job["remote_score"] = int(calculate_remote_score(job))
        job["match_score"] = int(round(
            0.8 * int(job.get("candidate_score") or 0)
            + 0.2 * int(job.get("remote_score") or 0)
        ))
    else:
        job["remote_score"] = int(job.get("remote_score") or 0)
        job["match_score"] = calculate_match_score(job["student_score"], job["candidate_score"])
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
            selection_reason_order(job),
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
            selection_reason_order(job),
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


def selection_reason_order(job):
    return {
        "NEW": 0,
        "UPDATED": 1,
        "NEVER_SENT_FILL": 2,
        "RESURFACED": 3,
        "FALLBACK_ROTATION": 4,
        "SEEN": 5,
    }.get(str(job.get("selection_reason") or ""), 6)


def add_profile_scores(jobs):
    scored = []
    for job in jobs:
        job = dict(job)
        title = job.get("title", "")
        snippet = " ".join([
            str(job.get(field, "") or "")
            for field in (
                "description",
                "contract_type",
                "employment_type",
                "working_hours",
                "salary",
                "experience",
                "skills",
                "snippet",
                "summary",
                "body",
                "company",
                "location",
                "url",
            )
        ])
        job["remote"] = detect_remote(
            title,
            snippet,
            job.get("query", ""),
            location=job.get("location", ""),
            url=job.get("url", ""),
            description=job.get("description", ""),
        )
        job["remote_reason"] = detect_remote_reason(
            title,
            snippet,
            job.get("query", ""),
            location=job.get("location", ""),
            url=job.get("url", ""),
            description=job.get("description", ""),
        )
        job["category"] = detect_category(title, snippet, job.get("query", ""))
        job["normalized_category"] = job["category"]
        job["part_time"] = detect_part_time(title, snippet, "")
        job["score"] = int(score_job(title, snippet, ""))
        if (job.get("search_profile") or LOCAL_STUDENT_PROFILE) == REMOTE_PROFILE:
            job.update(enrich_remote_quality(job))
            if job.get("normalized_remote_category") and job["normalized_remote_category"] != "Other":
                job["category"] = job["normalized_remote_category"]
                job["normalized_category"] = job["category"]
        job["location_fit"] = detect_location_fit(job, load_student_profile())
        job["student_score"] = int(evaluate_student_score(job))
        if is_unwanted_title_rejected(job):
            apply_unwanted_title_rejection(job)
        else:
            job["candidate_score"] = int(evaluate_candidate_score(job))
        apply_profile_scores(job, job.get("search_profile") or LOCAL_STUDENT_PROFILE)
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
        job.get("description", ""),
        job.get("contract_type", ""),
        job.get("employment_type", ""),
        job.get("working_hours", ""),
        job.get("salary", ""),
        job.get("experience", ""),
        job.get("skills", ""),
        bool(job.get("smart_working")),
        bool(job.get("part_time")),
        bool(job.get("full_time")),
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


def days_since_last_sent(last_sent, now=None):
    sent_at = parse_timestamp(last_sent)
    if not sent_at:
        return ""
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return max(0, (now - sent_at).days)


def annotate_history_status(jobs, history, now=None, skip_seen_days=DEFAULT_SKIP_SEEN_DAYS):
    annotated = []
    now = now or datetime.now(timezone.utc)
    for job in jobs:
        job = dict(job)
        current_job_id = job_id(job)
        history_record = history.get(current_job_id)
        job["job_id"] = current_job_id
        job["content_hash"] = content_hash(job)
        if history_record:
            job["first_seen"] = history_record.get("first_seen") or job.get("found_at", "")
            job["last_seen"] = history_record.get("last_seen") or job.get("found_at", "")
            job["last_sent"] = history_record.get("last_sent") or ""
            job["sent_count"] = int(history_record.get("sent_count") or 0)
        else:
            job["first_seen"] = job.get("first_seen") or job.get("found_at", "")
            job["last_seen"] = job.get("last_seen") or job.get("found_at", "")
            job["last_sent"] = job.get("last_sent") or ""
            job["sent_count"] = int(job.get("sent_count") or 0)
        job["history_status"] = classify_history_status(
            job,
            history_record,
            now=now,
            skip_seen_days=skip_seen_days,
        )
        days_since = days_since_last_sent(job.get("last_sent"), now=now)
        job["days_since_last_sent"] = days_since
        job["rotation_eligible"] = (
            isinstance(days_since, int)
            and int(job.get("sent_count") or 0) > 0
            and days_since >= skip_seen_days
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


def is_never_sent(job):
    last_sent = str(job.get("last_sent") or "").strip()
    try:
        sent_count = int(job.get("sent_count") or 0)
    except (TypeError, ValueError):
        sent_count = 0
    never_sent_by_history = sent_count == 0 or not last_sent
    if never_sent_by_history:
        return True
    status = str(job.get("history_status") or "").upper()
    if status == "NEVER_SENT" and never_sent_by_history:
        return True
    return False


def with_selection_reason(job, reason):
    item = dict(job)
    item["selection_reason"] = reason
    return item


def empty_selection_debug():
    return {
        "candidate_pool_total": 0,
        "candidates_total": 0,
        "eligible_new": 0,
        "eligible_updated": 0,
        "eligible_never_sent_fill": 0,
        "eligible_never_sent": 0,
        "eligible_resurfaced": 0,
        "eligible_fallback": 0,
        "eligible_fallback_rotation": 0,
        "rejected_low_match": 0,
        "rejected_profile": 0,
        "rejected_location": 0,
        "rejected_seen_recently": 0,
        "rejected_seen": 0,
        "rejected_no_selection_bucket": 0,
        "rejected_not_selected_due_to_limit": 0,
        "selected_total": 0,
    }


def match_score_value(job):
    try:
        return int(job.get("match_score") or 0)
    except (TypeError, ValueError):
        return 0


def is_match_eligible(job, email_min_match):
    return match_score_value(job) >= email_min_match


def is_location_rejected(job):
    return job.get("location_fit") == "excluded_far" or (
        job.get("location_fit") == "unknown" and not bool(job.get("remote"))
    )


def is_profile_rejected(job):
    negative_reason = str(job.get("negative_reason") or "").lower()
    return (
        is_unwanted_title_rejected(job)
        or
        "country" in negative_reason
        or "seniority" in negative_reason
        or "excluded title" in negative_reason
    )


def history_status(job):
    return str(job.get("history_status") or "").upper()


def is_new_bucket(job):
    return history_status(job) == "NEW"


def is_updated_bucket(job):
    return history_status(job) == "UPDATED"


def is_never_sent_fill_bucket(job):
    return is_never_sent(job) and history_status(job) not in {"NEW", "UPDATED"}


def is_resurfaced_bucket(job):
    return history_status(job) == "RESURFACED"


def is_rotation_eligible(job):
    value = job.get("rotation_eligible")
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def is_fallback_rotation_bucket(job):
    return (
        is_rotation_eligible(job)
        and not is_never_sent(job)
        and history_status(job) in {"SEEN", "RESURFACED"}
    )


def has_selection_bucket(job):
    return (
        is_new_bucket(job)
        or is_updated_bucket(job)
        or is_never_sent_fill_bucket(job)
        or is_resurfaced_bucket(job)
    )


def is_selectable_candidate(job, email_min_match):
    return (
        is_match_eligible(job, email_min_match)
        and not is_location_rejected(job)
        and not is_profile_rejected(job)
    )


def selection_rejection_reason(job, selected_keys, email_min_match, include_seen=False):
    key = aggregator_dedup_key(job)
    if key in selected_keys:
        return "selected"
    if is_location_rejected(job):
        return "location_rejected"
    if is_profile_rejected(job):
        return "profile_rejected"
    if not is_match_eligible(job, email_min_match):
        return "low_match"
    status = history_status(job)
    if status == "SEEN" and not include_seen and not is_never_sent(job):
        return "seen_recently"
    if not has_selection_bucket(job) and not (include_seen and status == "SEEN"):
        return "no_selection_bucket"
    return "not_selected_due_to_limit"


def select_email_jobs(
    jobs,
    email_target=DEFAULT_EMAIL_TARGET,
    email_min_match=DEFAULT_EMAIL_MIN_MATCH,
    include_seen=False,
    max_seen_repeat=DEFAULT_MAX_SEEN_REPEAT,
    fallback_enabled=False,
    return_debug=False,
):
    selected = []
    selected_keys = set()
    debug = empty_selection_debug()
    debug["candidate_pool_total"] = len(jobs)
    debug["candidates_total"] = len(jobs)

    def eligible(job):
        return is_selectable_candidate(job, email_min_match)

    def add_bucket(candidates, reason):
        for job in sort_by_score([item for item in candidates if eligible(item)]):
            if len(selected) >= email_target:
                return
            key = aggregator_dedup_key(job)
            if key in selected_keys:
                continue
            selected.append(with_selection_reason(job, reason))
            selected_keys.add(key)

    eligible_jobs = [job for job in jobs if eligible(job)]
    debug["eligible_new"] = sum(1 for job in eligible_jobs if is_new_bucket(job))
    debug["eligible_updated"] = sum(1 for job in eligible_jobs if is_updated_bucket(job))
    debug["eligible_never_sent_fill"] = sum(1 for job in eligible_jobs if is_never_sent_fill_bucket(job))
    debug["eligible_never_sent"] = sum(1 for job in eligible_jobs if is_never_sent(job))
    debug["eligible_resurfaced"] = sum(1 for job in eligible_jobs if is_resurfaced_bucket(job))

    add_bucket([job for job in jobs if is_new_bucket(job)], "NEW")
    add_bucket([job for job in jobs if is_updated_bucket(job)], "UPDATED")
    add_bucket([job for job in jobs if is_never_sent_fill_bucket(job)], "NEVER_SENT_FILL")
    add_bucket([job for job in jobs if is_resurfaced_bucket(job)], "RESURFACED")
    if include_seen:
        add_bucket(
            [job for job in jobs if history_status(job) == "SEEN"][:max_seen_repeat],
            "SEEN",
        )
    fallback_jobs = [
        job
        for job in eligible_jobs
        if is_fallback_rotation_bucket(job)
    ]
    debug["eligible_fallback_rotation"] = sum(
        1
        for job in fallback_jobs
        if aggregator_dedup_key(job) not in selected_keys
    )
    debug["eligible_fallback"] = debug["eligible_fallback_rotation"]
    if fallback_enabled and len(selected) < email_target:
        add_bucket(fallback_jobs, "FALLBACK_ROTATION")

    selected = selected[:email_target]
    selected_keys = {aggregator_dedup_key(job) for job in selected}
    debug["selected_total"] = len(selected)
    reasons = [
        selection_rejection_reason(job, selected_keys, email_min_match, include_seen=include_seen)
        for job in jobs
    ]
    debug["rejected_low_match"] = reasons.count("low_match")
    debug["rejected_profile"] = reasons.count("profile_rejected")
    debug["rejected_location"] = reasons.count("location_rejected")
    debug["rejected_seen_recently"] = reasons.count("seen_recently")
    debug["rejected_seen"] = debug["rejected_seen_recently"]
    debug["rejected_no_selection_bucket"] = reasons.count("no_selection_bucket")
    debug["rejected_not_selected_due_to_limit"] = reasons.count("not_selected_due_to_limit")

    if return_debug:
        return selected, debug
    return selected


def history_status_counts(jobs):
    return {
        "new_jobs": sum(1 for job in jobs if job.get("history_status") == "NEW"),
        "updated_jobs": sum(1 for job in jobs if job.get("history_status") == "UPDATED"),
        "seen_jobs": sum(1 for job in jobs if job.get("history_status") == "SEEN"),
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
        "search_profile": LOCAL_STUDENT_PROFILE,
        "total_candidates": 0,
        "after_cleaning": 0,
        "candidate_pool_jobs": 0,
        "removed_far": 0,
        "removed_unknown": 0,
        "removed_non_remote": 0,
        "new_jobs": 0,
        "updated_jobs": 0,
        "seen_skipped": 0,
        "resurfaced_jobs": 0,
        "email_jobs": 0,
        "selection_debug": empty_selection_debug(),
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
    search_profile=LOCAL_STUDENT_PROFILE,
    email_target=None,
    email_min_match=DEFAULT_EMAIL_MIN_MATCH,
    rotation_days=DEFAULT_ROTATION_DAYS,
    selection_fallback=False,
):
    jobs = []
    stats = empty_run_stats()
    stats["search_profile"] = search_profile
    export_limit = top
    target_count = email_target if email_target is not None else DEFAULT_EMAIL_TARGET
    stats["export_top"] = export_limit
    stats["email_target"] = target_count
    stats["email_min_match"] = email_min_match
    stats["rotation_days"] = rotation_days
    collected_counts = {}
    collector_names = collector_names or enabled_collectors()
    should_clean_results = clean_results or email_clean_results or strict_job_detail_only
    for name in collector_names:
        collector_jobs = run_collector(name, limit, top, campania_part_time_first, search_profile)
        print(f"Collector {name} returned: {len(collector_jobs)} jobs")
        collected_counts[name] = len(collector_jobs)
        jobs.extend(
            {
                **normalize_job(
                    job,
                    include_profile_scores=not should_clean_results,
                    search_profile=search_profile,
                ),
                "collector": name,
            }
            for job in collector_jobs
        )

    stats["total_candidates"] = len(jobs)
    raw_jobs = list(jobs)
    jobs = deduplicate_jobs(jobs)
    history = load_sent_history(history_path) if history_path else {}
    candidate_candidates = []
    if should_clean_results:
        jobs, summary = clean_results_with_summary(
            jobs,
            strict_job_detail_only=strict_job_detail_only,
            email_clean_results=email_clean_results,
        )
        print_cleaning_summary(summary)
        stats["after_cleaning"] = len(jobs)
        if search_profile == REMOTE_PROFILE:
            before_remote = len(jobs)
            jobs = filter_remote_jobs(jobs)
            stats["removed_non_remote"] = before_remote - len(jobs)
        if drop_far_locations and search_profile != REMOTE_PROFILE:
            before_drop = len(jobs)
            jobs = drop_far_location_jobs(jobs)
            stats["removed_far"] = before_drop - len(jobs)
            print(f"Removed excluded_far location: {stats['removed_far']}")
        if drop_unknown_locations and search_profile != REMOTE_PROFILE:
            before_drop = len(jobs)
            jobs = drop_unknown_location_jobs(jobs)
            stats["removed_unknown"] = before_drop - len(jobs)
            print(f"Removed unknown non-remote location: {stats['removed_unknown']}")
        jobs = add_profile_scores(jobs)
    else:
        stats["after_cleaning"] = len(jobs)
        if search_profile == REMOTE_PROFILE:
            before_remote = len(jobs)
            jobs = filter_remote_jobs(jobs)
            stats["removed_non_remote"] = before_remote - len(jobs)
        if drop_far_locations and search_profile != REMOTE_PROFILE:
            before_drop = len(jobs)
            jobs = drop_far_location_jobs(jobs)
            stats["removed_far"] = before_drop - len(jobs)
        if drop_unknown_locations and search_profile != REMOTE_PROFILE:
            before_drop = len(jobs)
            jobs = drop_unknown_location_jobs(jobs)
            stats["removed_unknown"] = before_drop - len(jobs)

    effective_rotation_days = rotation_days if rotation_days is not None else skip_seen_days
    if return_artifacts:
        candidate_candidates = annotate_history_status(
            jobs,
            history,
            skip_seen_days=effective_rotation_days,
        )
    if history_path:
        jobs = candidate_candidates if return_artifacts else annotate_history_status(
            jobs,
            history,
            skip_seen_days=effective_rotation_days,
        )
        status_counts = history_status_counts(jobs)
        stats.update(status_counts)
        selected_jobs, selection_debug = select_email_jobs(
            jobs,
            email_target=target_count,
            email_min_match=email_min_match,
            include_seen=include_seen,
            max_seen_repeat=max_seen_repeat,
            fallback_enabled=selection_fallback,
            return_debug=True,
        )
        stats["selection_debug"] = selection_debug
        selected_keys = {aggregator_dedup_key(job) for job in selected_jobs}
        selected_jobs = [
            {
                **job,
                "selection_rejection_reason": "selected",
            }
            for job in selected_jobs
        ]
        selected_by_key = {
            aggregator_dedup_key(job): job
            for job in selected_jobs
        }
        jobs = [
            {
                **job,
                "selection_reason": selected_by_key.get(aggregator_dedup_key(job), {}).get(
                    "selection_reason",
                    job.get("selection_reason", ""),
                ),
                "selection_rejection_reason": selected_by_key.get(aggregator_dedup_key(job), {}).get(
                    "selection_rejection_reason",
                    selection_rejection_reason(
                        job,
                        selected_keys,
                        email_min_match,
                        include_seen=include_seen,
                    ),
                ),
            }
            for job in jobs
        ]
        stats["seen_skipped"] = sum(
            1
            for job in jobs
            if job.get("history_status") == "SEEN" and aggregator_dedup_key(job) not in selected_keys
        )
    else:
        jobs = annotate_history_status(
            jobs,
            {},
            skip_seen_days=effective_rotation_days,
        )
        selectable_jobs = [
            job
            for job in jobs
            if int(job.get("match_score") or 0) >= email_min_match
        ]
        selected_jobs, selection_debug = select_email_jobs(
            selectable_jobs,
            email_target=target_count,
            email_min_match=email_min_match,
            include_seen=include_seen,
            max_seen_repeat=max_seen_repeat,
            fallback_enabled=selection_fallback,
            return_debug=True,
        )
        stats["selection_debug"] = selection_debug
        selected_keys = {aggregator_dedup_key(job) for job in selected_jobs}
        selected_by_key = {
            aggregator_dedup_key(job): {
                **job,
                "selection_rejection_reason": "selected",
            }
            for job in selected_jobs
        }
        selected_jobs = list(selected_by_key.values())
        jobs = [
            {
                **with_selection_reason(job, selected_by_key.get(aggregator_dedup_key(job), {}).get("selection_reason", "")),
                "selection_rejection_reason": selected_by_key.get(aggregator_dedup_key(job), {}).get(
                    "selection_rejection_reason",
                    selection_rejection_reason(
                        job,
                        selected_keys,
                        email_min_match,
                        include_seen=include_seen,
                    ),
                ),
            }
            for job in selectable_jobs
        ]

    jobs = sort_jobs(jobs)
    if search_profile == REMOTE_PROFILE:
        jobs = jobs[:export_limit]
    else:
        jobs = balanced_top(
            jobs,
            top=export_limit,
            min_remote=min_remote,
            min_hospitality=min_hospitality,
            min_cleaning=min_cleaning,
            min_maintenance=min_maintenance,
            min_data_office=min_data_office,
        )
    stats["export_jobs"] = len(jobs)
    stats["email_jobs"] = len(selected_jobs)
    if return_artifacts:
        candidate_pool = build_candidate_pool(candidate_candidates, selected_jobs, history, email_min_match=email_min_match)
        collector_stats = build_collector_stats(collected_counts, candidate_candidates, selected_jobs)
        collector_health = build_collector_health(collector_stats, candidate_pool)
        url_pattern_debug = build_url_pattern_debug_rows(raw_jobs, candidate_candidates, jobs)
        stats["candidate_pool_jobs"] = len(candidate_pool)
        stats["collector_stats"] = collector_stats
        stats["collector_health"] = collector_health
        stats["collector_contribution"] = {
            row["collector"]: row["email_jobs"]
            for row in collector_stats
        }
        return jobs, stats, {
            "candidate_pool": candidate_pool,
            "collector_stats": collector_stats,
            "collector_health": collector_health,
            "url_pattern_debug": url_pattern_debug,
            "email_jobs": selected_jobs,
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


def default_paths_for_profile(search_profile):
    if search_profile == REMOTE_PROFILE:
        return {
            "output": REMOTE_OUTPUT_PATH,
            "candidate_pool_output": REMOTE_POOL_PATH,
            "collector_stats_output": DEFAULT_COLLECTOR_STATS_PATH,
            "history_path": REMOTE_HISTORY_PATH,
            "run_stats_path": REMOTE_RUN_STATS_PATH,
        }
    return {
        "output": DEFAULT_OUTPUT_PATH,
        "candidate_pool_output": DEFAULT_POOL_PATH,
        "collector_stats_output": DEFAULT_COLLECTOR_STATS_PATH,
        "history_path": DEFAULT_HISTORY_PATH,
        "run_stats_path": DEFAULT_RUN_STATS_PATH,
    }


def resolve_cli_path(value, key, search_profile):
    if value:
        return value
    return default_paths_for_profile(search_profile)[key]


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--collectors", default=None)
    parser.add_argument("--search-profile", choices=[LOCAL_STUDENT_PROFILE, REMOTE_PROFILE], default=LOCAL_STUDENT_PROFILE)
    parser.add_argument("--output", default=None)
    parser.add_argument("--candidate-pool-output", default=None)
    parser.add_argument("--collector-stats-output", default=None)
    parser.add_argument("--history-path", default=None)
    parser.add_argument("--run-stats-path", default=None)
    parser.add_argument("--skip-seen-days", type=int, default=DEFAULT_SKIP_SEEN_DAYS)
    parser.add_argument("--max-seen-repeat", type=int, default=DEFAULT_MAX_SEEN_REPEAT)
    parser.add_argument("--include-seen", choices=["false", "true"], default="false")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP)
    parser.add_argument("--email-target", type=int, default=DEFAULT_EMAIL_TARGET)
    parser.add_argument("--email-min-match", type=int, default=DEFAULT_EMAIL_MIN_MATCH)
    parser.add_argument("--rotation-days", type=int, default=DEFAULT_ROTATION_DAYS)
    parser.add_argument("--selection-fallback", choices=["false", "true"], default="false")
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
    output_path = resolve_cli_path(args.output, "output", args.search_profile)
    candidate_pool_output = resolve_cli_path(args.candidate_pool_output, "candidate_pool_output", args.search_profile)
    collector_stats_output = resolve_cli_path(args.collector_stats_output, "collector_stats_output", args.search_profile)
    history_path = resolve_cli_path(args.history_path, "history_path", args.search_profile)
    run_stats_path = resolve_cli_path(args.run_stats_path, "run_stats_path", args.search_profile)
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
        history_path=history_path,
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
        search_profile=args.search_profile,
        email_target=args.email_target,
        email_min_match=args.email_min_match,
        rotation_days=args.rotation_days,
        selection_fallback=args.selection_fallback == "true",
    )
    export_jobs(jobs, output_path)
    export_candidate_pool(artifacts["candidate_pool"], candidate_pool_output)
    export_collector_stats(artifacts["collector_stats"], collector_stats_output)
    export_collector_health(artifacts["collector_health"])
    export_url_pattern_debug(artifacts["url_pattern_debug"])
    history = load_sent_history(history_path)
    history = update_sent_history(history, artifacts["email_jobs"])
    write_sent_history(history, history_path)
    write_run_stats(stats, run_stats_path)


if __name__ == "__main__":
    main()
