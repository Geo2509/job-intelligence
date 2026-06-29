import argparse
import html
import json
import os
from email.mime.text import MIMEText
from pathlib import Path

from src.main import email_enabled, require_email_settings, smtplib


DEFAULT_INPUT_PATH = "output/v2_jobs.json"
DEFAULT_RUN_STATS_PATH = "output/v2_run_stats.json"
REMOTE_INPUT_PATH = "output/v2_remote_jobs.json"
REMOTE_RUN_STATS_PATH = "output/v2_remote_run_stats.json"
DEFAULT_TOP = 100
LOCAL_STUDENT_PROFILE = "local_student"
REMOTE_PROFILE = "remote"
SUBJECT = "Job Intelligence V2: Napoli Student Jobs"
REMOTE_SUBJECT = "Job Intelligence V2: Remote AI/Data Jobs"

LOCAL_BLOCKS = [
    "Campania part-time",
    "Hospitality / Hotel / Restaurant",
    "Cleaning / Pulizie",
    "Maintenance / Manutenzione",
    "Warehouse / GDO",
    "Remote / Data / AI",
    "Other",
]
REMOTE_BLOCKS = [
    "AI Training",
    "Data",
    "Logistics",
    "Virtual Assistant",
    "Transcription",
    "Other",
]
BLOCKS = LOCAL_BLOCKS

LOCAL_TERMS = [
    "napoli",
    "pozzuoli",
    "bacoli",
    "monte di procida",
    "quarto",
    "fuorigrotta",
    "campi flegrei",
    "campania",
]
HOSPITALITY_TERMS = [
    "hospitality",
    "hotel",
    "albergo",
    "restaurant",
    "ristorante",
    "accoglienza",
    "front office",
    "barista",
    "cameriere",
    "cameriera",
    "cuoco",
    "receptionist",
    "reception",
    "sala",
    "turismo",
]
CLEANING_TERMS = ["cleaning", "cleaner", "pulizie", "addetto pulizie", "addetta pulizie"]
MAINTENANCE_TERMS = [
    "maintenance",
    "manutenzione",
    "manutentore",
    "tecnico",
    "elettricista",
    "idraulico",
]
WAREHOUSE_TERMS = [
    "warehouse",
    "magazzino",
    "magazziniere",
    "logistica",
    "gdo",
    "supermercato",
    "scaffalista",
]
REMOTE_DATA_TERMS = [
    "remote",
    "remoto",
    "smart working",
    "data",
    "ai",
    "annotation",
    "annotator",
    "trainer",
    "transcription",
    "data entry",
    "inserimento dati",
    "back office",
]
AI_TRAINER_TERMS = ["ai trainer", "ai annotator", "data annotator", "ai evaluator", "search evaluator", "data labeling", "data annotation"]
DATA_PROCESSING_TERMS = ["data entry", "data processing", "google sheets", "excel"]
TRANSCRIPTION_TERMS = ["transcription", "trascrizione", "localization", "translation"]
VIRTUAL_ASSISTANT_TERMS = ["virtual assistant", "assistente virtuale"]
SUPPORT_MODERATION_TERMS = ["customer support", "content reviewer", "moderation"]
LOGISTICS_REMOTE_TERMS = ["logistics", "logistica", "operations", "freight forwarding"]
DATA_ENTRY_CATEGORIES = {"data_entry", "data_office", "campania_part_time_data"}
BACK_OFFICE_CATEGORIES = {"back_office", "administration", "accounting", "admin", "office"}
AI_CATEGORIES = {"remote_data", "ai_data", "ai_annotation", "ai training", "ai annotation"}
LOGISTICS_CATEGORIES = {"logistics", "warehouse"}
RECEPTION_CATEGORIES = {"reception", "front_office", "receptionist", "accoglienza"}
HOSPITALITY_CATEGORIES = {"hospitality", "hotel", "restaurant", "barista"} | RECEPTION_CATEGORIES
RETAIL_CATEGORIES = {"gdo", "retail", "vendita", "sales"}
HARD_RISK_TERMS = ["italian c1", "italiano c1", "c1 italiano", "night shift", "notturno", "turno notte"]
HISTORY_REJECTION_REASONS = {"history_seen", "seen_recently"}
PROFILE_REJECTION_REASONS = {"profile_rejected", "rejected_by_profile", "rejected_by_country", "rejected_by_seniority", "low_match"}
CLEANER_LOCATION_REJECTION_REASONS = {
    "location_rejected",
    "excluded_far",
    "unknown_location",
    "matched_search_page",
    "matched_category_page",
    "matched_company_page",
    "matched_profile",
    "matched_article",
    "matched_excluded_domain",
    "unknown_pattern",
}


def load_jobs(input_path):
    path = Path(input_path)
    if not path.exists():
        return []
    jobs = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(jobs, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return jobs


def email_selected_jobs(jobs):
    selected = [
        job
        for job in jobs
        if str(job.get("selection_rejection_reason") or "").lower() == "selected"
    ]
    if selected:
        return selected
    return jobs


def load_run_stats(stats_path=DEFAULT_RUN_STATS_PATH):
    path = Path(stats_path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return data


def load_candidate_pool(path):
    pool_path = Path(path)
    if not pool_path.exists():
        return []
    data = json.loads(pool_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {pool_path}")
    return data


def job_text(job):
    return " ".join(
        str(job.get(field, "") or "")
        for field in [
            "title",
            "company",
            "location",
            "category",
            "normalized_remote_category",
            "description",
            "query",
            "source",
        ]
    ).lower()


def has_any(text, terms):
    return any(term in text for term in terms)


def is_campania_part_time(job, text):
    return (
        job.get("priority_bucket") == "campania_part_time"
        or (bool(job.get("part_time")) and has_any(text, LOCAL_TERMS))
    )


def classify_job(job, search_profile=LOCAL_STUDENT_PROFILE):
    text = job_text(job)
    category = str(job.get("category", "") or "").lower()
    if search_profile == REMOTE_PROFILE:
        remote_category = str(job.get("normalized_remote_category") or "")
        if remote_category in {"AI Training", "AI Annotation"}:
            return "AI Training"
        if remote_category in {"Data Entry", "Analytics", "Python"}:
            return "Data"
        if remote_category == "Logistics":
            return "Logistics"
        if remote_category == "Virtual Assistant":
            return "Virtual Assistant"
        if remote_category in {"Transcription", "Translation"}:
            return "Transcription"
        if has_any(text, AI_TRAINER_TERMS):
            return "AI Training"
        if has_any(text, DATA_PROCESSING_TERMS):
            return "Data"
        if has_any(text, LOGISTICS_REMOTE_TERMS):
            return "Logistics"
        if has_any(text, TRANSCRIPTION_TERMS):
            return "Transcription"
        if has_any(text, VIRTUAL_ASSISTANT_TERMS):
            return "Virtual Assistant"
        if has_any(text, SUPPORT_MODERATION_TERMS):
            return "Other"
        return "Other"

    if is_campania_part_time(job, text):
        return "Campania part-time"
    if category in HOSPITALITY_CATEGORIES or has_any(text, HOSPITALITY_TERMS):
        return "Hospitality / Hotel / Restaurant"
    if category in {"cleaning", "pulizie"} or has_any(text, CLEANING_TERMS):
        return "Cleaning / Pulizie"
    if category in {"maintenance", "manutenzione"} or has_any(text, MAINTENANCE_TERMS):
        return "Maintenance / Manutenzione"
    if category in {"warehouse", "gdo", "logistics"} or has_any(text, WAREHOUSE_TERMS):
        return "Warehouse / GDO"
    if (
        job.get("priority_bucket") == "remote_data"
        or bool(job.get("remote"))
        or category in {"ai_data", "data_entry", "remote"}
        or has_any(text, REMOTE_DATA_TERMS)
    ):
        return "Remote / Data / AI"
    return "Other"


def blocks_for_profile(search_profile):
    if search_profile == REMOTE_PROFILE:
        return REMOTE_BLOCKS
    return LOCAL_BLOCKS


def grouped_jobs(jobs, search_profile=LOCAL_STUDENT_PROFILE):
    groups = {block: [] for block in blocks_for_profile(search_profile)}
    for job in jobs:
        groups[classify_job(job, search_profile)].append(job)
    return groups


def score_value(job, field):
    try:
        return int(job.get(field) or 0)
    except (TypeError, ValueError):
        return 0


def text_value(value):
    return str(value or "").strip()


def clean_items(items):
    cleaned = []
    seen = set()
    for item in items:
        text = text_value(item)
        if not text or text.lower() in seen:
            continue
        cleaned.append(text)
        seen.add(text.lower())
    return cleaned


def has_hard_candidate_risk(job):
    text = job_text(job)
    if job.get("location_fit") == "excluded_far":
        return True
    return has_any(text, HARD_RISK_TERMS)


def recommendation_level(job):
    rejection = str(job.get("selection_rejection_reason") or "").lower()
    history_status = str(job.get("history_status") or "").upper()
    match_score = score_value(job, "match_score")
    location_fit = str(job.get("location_fit") or "").lower()

    if rejection and rejection != "selected":
        return "skip"
    if history_status == "SEEN":
        return "skip"
    if match_score >= 75 and location_fit in {"allowed_local", "remote"} and not has_hard_candidate_risk(job):
        return "apply_today"
    if match_score >= 68:
        return "good"
    if match_score >= 58:
        return "consider"
    if match_score > 0:
        return "watch"
    return "skip"


def recommendation_label(level):
    return {
        "apply_today": "★★★★★ Apply today",
        "good": "★★★★ Good",
        "consider": "★★★ Consider",
        "watch": "★★ Watch",
        "skip": "★ Skip",
    }.get(level, "★★ Watch")


def fit_reasons(job):
    text = job_text(job)
    category = str(job.get("category") or "").lower()
    location_fit = str(job.get("location_fit") or "").lower()
    reasons = []

    if location_fit == "allowed_local":
        if "pozzuoli" in text:
            reasons.append("Pozzuoli / close to Monte di Procida")
        elif "bacoli" in text:
            reasons.append("Bacoli / close to Monte di Procida")
        elif "monte di procida" in text:
            reasons.append("Monte di Procida / very close")
        elif "napoli" in text:
            reasons.append("Napoli / allowed local area")
        else:
            reasons.append("Local area allowed by student profile")
    if location_fit == "remote" or bool(job.get("remote")):
        reasons.append("Remote possible")
    if bool(job.get("part_time")) or has_any(text, ["part time", "part-time", "tempo parziale"]):
        reasons.append("Part-time signal found")
        reasons.append("Compatible with study")
    if has_any(text, ["mattina", "lun-ven", "weekday", "giorno"]):
        reasons.append("Schedule signal looks study-friendly")
    if category in DATA_ENTRY_CATEGORIES or has_any(text, ["data entry", "inserimento dati", "excel", "google sheets"]):
        reasons.append("Matches Excel / Google Sheets / data entry")
    if category in BACK_OFFICE_CATEGORIES or has_any(text, ["back office", "amministrazione", "amministrativo", "segreteria"]):
        reasons.append("Matches back office / admin experience")
    if category in LOGISTICS_CATEGORIES or has_any(text, ["logistics", "logistica", "warehouse", "magazzino", "spedizioni"]):
        reasons.append("Matches logistics / warehouse experience")
    if category in HOSPITALITY_CATEGORIES or has_any(text, HOSPITALITY_TERMS):
        reasons.append("Hospitality role, possible entry-level")
    if category in AI_CATEGORIES or has_any(text, AI_TRAINER_TERMS):
        reasons.append("Matches remote AI / data annotation profile")
    if not has_any(text, ["laurea obbligatoria", "laurea richiesta", "degree required"]):
        reasons.append("No degree required signal found")

    existing = []
    for field in ("fit_reasons", "student_reason", "candidate_reason", "positive_reason"):
        value = job.get(field)
        if isinstance(value, list):
            existing.extend(value)
        elif value:
            existing.append(value)
    return clean_items(existing + reasons)[:7]


def risk_reasons(job):
    text = job_text(job)
    risks = []

    existing = job.get("risk_reasons")
    if isinstance(existing, list):
        risks.extend(existing)
    elif existing:
        risks.append(existing)

    if not (bool(job.get("part_time")) or has_any(text, ["part time", "part-time", "tempo parziale"])):
        risks.append("Full-time / part-time not confirmed")
    if has_any(text, ["italian b2", "italiano b2", "b2 italiano", "italian c1", "italiano c1", "c1 italiano"]):
        risks.append("Italian B2/C1 may be required")
    if has_any(text, ["night shift", "turno notte", "notturno", "notte"]):
        risks.append("Night shift")
    if job.get("location_fit") == "excluded_far":
        risks.append("Far location")
    if job.get("location_fit") == "unknown":
        risks.append("Location not confirmed")
    if not text_value(job.get("category")) or str(job.get("category")).lower() in {"general", "other", "unknown"}:
        risks.append("Category too generic")
    if not text_value(job.get("company")):
        risks.append("Company missing")
    if not text_value(job.get("location")):
        risks.append("Location missing")
    if not (text_value(job.get("salary_text")) or text_value(job.get("salary"))):
        risks.append("Salary missing")
    negative_reason = text_value(job.get("negative_reason"))
    if negative_reason:
        risks.append(negative_reason)
    return clean_items(risks)[:7]


def recommended_cv(job):
    text = job_text(job)
    category = str(job.get("category") or "").lower()
    remote_category = str(job.get("normalized_remote_category") or "").lower()

    if category in AI_CATEGORIES or remote_category in {"ai training", "ai annotation"} or has_any(text, AI_TRAINER_TERMS):
        return "AI / Data Annotation CV"
    if category in DATA_ENTRY_CATEGORIES or has_any(text, ["data entry", "inserimento dati", "excel", "google sheets"]):
        return "Data Entry CV"
    if category in RECEPTION_CATEGORIES or has_any(text, ["reception", "receptionist", "front office", "accoglienza"]):
        return "Back Office / Reception CV"
    if category in BACK_OFFICE_CATEGORIES or has_any(text, ["back office", "amministrazione", "amministrativo", "segreteria"]):
        return "Back Office CV"
    if category in LOGISTICS_CATEGORIES or has_any(text, ["logistics", "logistica", "warehouse", "magazzino", "spedizioni"]):
        return "Logistics CV"
    if category in HOSPITALITY_CATEGORIES or has_any(text, HOSPITALITY_TERMS):
        return "Hospitality CV"
    if category in RETAIL_CATEGORIES or has_any(text, ["gdo", "retail", "vendita", "cassiere", "scaffalista", "supermercato"]):
        return "Retail / GDO CV"
    return "Generic CV"


def recommended_cover_letter(job):
    cv = recommended_cv(job)
    return {
        "AI / Data Annotation CV": "AI Trainer / Annotator cover letter",
        "Data Entry CV": "Data Processing cover letter",
        "Back Office / Reception CV": "Back Office / Administration cover letter",
        "Back Office CV": "Back Office / Administration cover letter",
        "Logistics CV": "Logistics cover letter",
        "Hospitality CV": "Hospitality short message",
        "Retail / GDO CV": "Retail short message",
        "Generic CV": "Generic short message",
    }[cv]


def enrich_email_job(job):
    enriched = dict(job)
    enriched["recommendation_level"] = enriched.get("recommendation_level") or recommendation_level(enriched)
    enriched["fit_reasons"] = fit_reasons(enriched)
    enriched["risk_reasons"] = risk_reasons(enriched)
    enriched["recommended_cv"] = enriched.get("recommended_cv") or recommended_cv(enriched)
    enriched["recommended_cover_letter"] = (
        enriched.get("recommended_cover_letter") or recommended_cover_letter(enriched)
    )
    return enriched


def sorted_jobs(jobs):
    return sorted(
        jobs,
        key=lambda job: (
            selection_reason_order(job),
            -score_value(job, "match_score"),
            -score_value(job, "student_score"),
            -score_value(job, "candidate_score"),
            -score_value(job, "score"),
        ),
    )


def selection_reason_order(job):
    return {
        "NEW": 0,
        "UPDATED": 1,
        "NEVER_SENT_FILL": 2,
        "RESURFACED": 3,
        "FALLBACK_ROTATION": 4,
        "SEEN": 5,
    }.get(str(job.get("selection_reason") or ""), 6)


def match_label(match_score):
    if match_score >= 90:
        return "★★★★★ Strong match"
    if match_score >= 80:
        return "★★★★ Good match"
    return "★★★ Consider"


def history_status_label(status):
    return {
        "NEW": "🔥 NEW",
        "UPDATED": "♻️ UPDATED",
        "RESURFACED": "↩️ RESURFACED",
        "SEEN": "SEEN",
    }.get(str(status or ""), "")


def email_summary(jobs):
    top_match_score = max((score_value(job, "match_score") for job in jobs), default=0)
    recommended_count = sum(
        1
        for job in jobs
        if recommendation_level(job) == "apply_today"
    )
    return top_match_score, recommended_count


def main_action_reason(jobs):
    if not jobs:
        return "No selected jobs in this email."
    best = max(jobs, key=lambda job: score_value(job, "match_score"))
    reasons = fit_reasons(best)
    if reasons:
        return reasons[0]
    return "Highest match score in the current selection."


def render_action_plan(jobs, stats=None):
    stats = stats or {}
    counts = {
        "apply_today": 0,
        "watch": 0,
        "skip": 0,
    }
    for job in jobs:
        level = recommendation_level(job)
        if level == "apply_today":
            counts["apply_today"] += 1
        elif level == "watch":
            counts["watch"] += 1
        elif level == "skip":
            counts["skip"] += 1
    top_match_score = max((score_value(job, "match_score") for job in jobs), default=0)
    stats_skip = int(stats.get("seen_skipped") or 0) + int(stats.get("removed_far") or 0) + int(stats.get("removed_unknown") or 0)
    skip_total = counts["skip"] + stats_skip
    return (
        "<h2>Today's Action Plan</h2>"
        "<ul>"
        f"<li><strong>Apply today:</strong> {counts['apply_today']}</li>"
        f"<li><strong>Watch:</strong> {counts['watch']}</li>"
        f"<li><strong>Skip:</strong> {skip_total}</li>"
        f"<li><strong>Best match:</strong> {top_match_score}</li>"
        f"<li><strong>Main reason:</strong> {html.escape(main_action_reason(jobs))}</li>"
        "</ul>"
    )


def render_run_stats(stats):
    if not stats:
        return ""
    collector_rows = stats.get("collector_stats") or []
    history_skipped = int(stats.get("seen_skipped") or 0)
    new_jobs = int(stats.get("new_jobs") or 0)
    updated_jobs = int(stats.get("updated_jobs") or 0)
    seen_jobs = sum(int(row.get("history_seen") or 0) for row in collector_rows)
    allowed_local = sum(int(row.get("allowed_local") or 0) for row in collector_rows)
    remote = sum(int(row.get("remote") or 0) for row in collector_rows)
    unknown = sum(int(row.get("unknown_location") or 0) for row in collector_rows)
    excluded_far = sum(int(row.get("excluded_far") or 0) for row in collector_rows)
    return (
        "<h2>Email Statistics</h2>"
        f"<p><strong>Collected:</strong> {int(stats.get('total_candidates') or 0)}</p>"
        f"<p><strong>After cleaner:</strong> {int(stats.get('candidate_pool_jobs') or stats.get('after_cleaning') or 0)}</p>"
        f"<p><strong>Allowed local:</strong> {allowed_local}</p>"
        f"<p><strong>Remote:</strong> {remote}</p>"
        f"<p><strong>Unknown:</strong> {unknown}</p>"
        f"<p><strong>Excluded far:</strong> {excluded_far}</p>"
        f"<p><strong>History skipped:</strong> {history_skipped}</p>"
        f"<p><strong>New jobs:</strong> {new_jobs}</p>"
        f"<p><strong>Updated jobs:</strong> {updated_jobs}</p>"
        f"<p><strong>Seen jobs:</strong> {seen_jobs}</p>"
        "<h3>Collector contribution</h3>"
        f"{render_collector_contribution(stats)}"
        f"{render_collector_health(stats.get('collector_health') or [])}"
        f"{render_next_resurfacing(stats)}"
    )


def health_by_collector(stats):
    return {
        str(row.get("collector") or "").lower(): row
        for row in stats.get("collector_health") or []
    }


def render_collector_contribution(stats):
    collector_rows = stats.get("collector_stats") or []
    if not collector_rows:
        return "<p>No collector stats available.</p>"
    health_rows = health_by_collector(stats)
    items = []
    for row in collector_rows:
        collector = str(row.get("collector", "") or "unknown")
        health = health_rows.get(collector.lower(), {})
        status = str(health.get("collector_health_status") or row.get("collector_health_status") or "unknown")
        collected = int(row.get("collected") or row.get("raw_collected") or 0)
        real_jobs = int(row.get("real_jobs") or 0)
        candidate_pool = int(row.get("candidate_pool") or health.get("candidate_pool") or 0)
        email_jobs = int(row.get("email_jobs") or row.get("email") or 0)
        items.append(
            "<li>"
            f"<strong>{html.escape(collector.title())}</strong>: "
            f"collected: {collected} | real jobs: {real_jobs} | "
            f"candidate pool: {candidate_pool} | email: {email_jobs} | "
            f"reason: {html.escape(status)}"
            "</li>"
        )
    return "<ul>" + "".join(items) + "</ul>"


def render_next_resurfacing(stats):
    rotation_days = int(stats.get("rotation_days") or 0)
    if not rotation_days:
        return ""
    rows = stats.get("collector_health") or []
    seen_collectors = [
        str(row.get("collector") or "unknown")
        for row in rows
        if int(row.get("seen") or row.get("removed_by_history") or 0) > 0
    ]
    if not seen_collectors:
        return ""
    items = "".join(
        f"<li>{html.escape(name.title())}: Seen jobs may resurface after {rotation_days} days.</li>"
        for name in seen_collectors
    )
    return "<h3>Next resurfacing</h3><ul>" + items + "</ul>"


def render_collector_health(rows):
    if not rows:
        return ""
    items = []
    for row in rows:
        collector = html.escape(str(row.get("collector", "") or "unknown"))
        status = html.escape(str(row.get("collector_health_status", "") or ""))
        new = int(row.get("new") or 0)
        updated = int(row.get("updated") or 0)
        seen = int(row.get("seen") or row.get("removed_by_history") or 0)
        resurfaced = int(row.get("resurfaced") or 0)
        email_jobs = int(row.get("email") or 0)
        real_jobs = int(row.get("real_jobs") or 0)
        candidate_pool = int(row.get("candidate_pool") or 0)
        worldwide = int(row.get("worldwide_jobs") or 0)
        eu_jobs = int(row.get("eu_jobs") or 0)
        rejected_country = int(row.get("rejected_by_country") or 0)
        rejected_seniority = int(row.get("rejected_by_seniority") or 0)
        rejected_profile = int(row.get("rejected_by_profile") or 0)
        if real_jobs == 0:
            detail = "0 real jobs"
        else:
            detail = (
                f"{email_jobs} email / {real_jobs} real jobs / {candidate_pool} candidate pool"
                f" | NEW: {new} | UPDATED: {updated} | SEEN: {seen} | RESURFACED: {resurfaced}"
                f" | Worldwide: {worldwide} | EU: {eu_jobs}"
                f" | Rejected country: {rejected_country}"
                f" | Rejected seniority: {rejected_seniority}"
                f" | Rejected profile: {rejected_profile}"
            )
        items.append(f"<li><strong>{collector}</strong> ({status}) - {detail}</li>")
    return "<h2>Collector Health</h2><ul>" + "".join(items) + "</ul>"


def render_list(title, items):
    items = clean_items(items)
    if not items:
        return ""
    rendered = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"<p><strong>{html.escape(title)}:</strong></p><ul>{rendered}</ul>"


def render_field(label, value):
    text = text_value(value)
    if not text or text.lower() == "none":
        return ""
    return f"<p><strong>{html.escape(label)}:</strong> {html.escape(text)}</p>"


def render_link(label, url):
    url = text_value(url)
    if not url:
        return ""
    escaped = html.escape(url, quote=True)
    return f'<p><strong>{html.escape(label)}:</strong> <a href="{escaped}">{escaped}</a></p>'


def render_job(job):
    job = enrich_email_job(job)
    title = html.escape(str(job.get("title", "") or ""))
    company = str(job.get("company", "") or "")
    location = str(job.get("location", "") or "")
    score = str(job.get("score", "") or "")
    raw_match_score = score_value(job, "match_score")
    match_score = str(job.get("match_score", "") or "")
    student_score = str(job.get("student_score", "") or "")
    candidate_score = str(job.get("candidate_score", "") or "")
    remote_score = str(job.get("remote_score", "") or "")
    remote = str(job.get("remote", ""))
    remote_reason = str(job.get("remote_reason", "") or "none")
    part_time = str(job.get("part_time", ""))
    location_fit = str(job.get("location_fit", "") or "")
    category = str(job.get("category", "") or "")
    rejection_reason = str(job.get("rejection_reason", "") or "")
    country = str(job.get("country_restriction", "") or "")
    employment = str(job.get("employment_type", "") or "")
    salary = str(job.get("salary_text", "") or job.get("salary", "") or "")
    remote_category = str(job.get("normalized_remote_category", "") or "")
    source = str(job.get("source", "") or "")
    url = str(job.get("url", "") or "")
    recommendation = html.escape(recommendation_label(job["recommendation_level"]))
    history_status = html.escape(history_status_label(job.get("history_status")))
    selection_reason = html.escape(str(job.get("selection_reason", "") or ""))
    days_since_last_sent = html.escape(str(job.get("days_since_last_sent", "") or ""))
    status_line = f"<p><strong>Status:</strong> {history_status}</p>" if history_status else ""
    selection_line = f"<p><strong>Selection:</strong> {selection_reason}</p>" if selection_reason else ""
    days_since_line = (
        f"<p><strong>Days since last sent:</strong> {days_since_last_sent}</p>"
        if days_since_last_sent
        else ""
    )
    meta = " | ".join(
        item
        for item in [
            f"Match: {match_score}" if match_score else "",
            f"Student: {student_score}" if student_score else "",
            f"Candidate: {candidate_score}" if candidate_score else "",
            f"Score: {score}" if score else "",
        ]
        if item
    )

    return (
        "<li>"
        f"<h3>{title}</h3>"
        f"<p><strong>{recommendation}</strong></p>"
        f"<p>{html.escape(meta)}</p>"
        f"{status_line}"
        f"{selection_line}"
        f"{days_since_line}"
        f"{render_field('Location fit', location_fit)}"
        f"{render_field('Source', source)}"
        f"{render_field('Category', category)}"
        f"{render_field('Remote category', remote_category)}"
        f"{render_field('Remote', remote)}"
        f"{render_field('Remote reason', remote_reason)}"
        f"{render_field('Part time', part_time)}"
        f"{render_field('Remote score', remote_score)}"
        f"{render_field('Rejection reason', rejection_reason)}"
        f"{render_field('Country', country)}"
        f"{render_field('Employment', employment)}"
        f"{render_field('Salary', salary)}"
        f"{render_field('Positive reasons', job.get('positive_reason'))}"
        f"{render_field('Negative reasons', job.get('negative_reason'))}"
        f"{render_link('URL', url)}"
        f"{render_field('Company', company)}"
        f"{render_field('Location', location)}"
        f"{render_list('Why it fits Yurii', job.get('fit_reasons') or [])}"
        f"{render_list('Risks', job.get('risk_reasons') or [])}"
        f"{render_field('Recommended CV', job.get('recommended_cv'))}"
        f"{render_field('Recommended message', job.get('recommended_cover_letter'))}"
        "</li>"
    )


def diagnostic_jobs_for_block(block, run_stats=None, search_profile=LOCAL_STUDENT_PROFILE):
    stats = run_stats or {}
    candidate_pool = stats.get("candidate_pool") or stats.get("candidate_pool_jobs_data") or []
    if not isinstance(candidate_pool, list):
        return []
    return [
        job
        for job in candidate_pool
        if classify_job(job, search_profile) == block
    ]


def rejection_reason_for_stats(job):
    return str(
        job.get("selection_rejection_reason")
        or job.get("rejection_reason")
        or ""
    ).lower()


def empty_block_diagnostics(block, run_stats=None, search_profile=LOCAL_STUDENT_PROFILE):
    block_jobs = diagnostic_jobs_for_block(block, run_stats, search_profile)
    found = len(block_jobs)
    already_seen = sum(
        1
        for job in block_jobs
        if str(job.get("history_status") or "").upper() == "SEEN"
        or rejection_reason_for_stats(job) in {"history_seen", "seen_recently"}
    )
    rejected_history = sum(
        1
        for job in block_jobs
        if rejection_reason_for_stats(job) in HISTORY_REJECTION_REASONS
    )
    rejected_profile = sum(
        1
        for job in block_jobs
        if rejection_reason_for_stats(job) in PROFILE_REJECTION_REASONS
    )
    rejected_cleaner_location = sum(
        1
        for job in block_jobs
        if rejection_reason_for_stats(job) in CLEANER_LOCATION_REJECTION_REASONS
        or (
            str(job.get("location_fit") or "") in {"excluded_far", "unknown"}
            and not bool(job.get("remote"))
        )
    )
    return (
        "<li>"
        "<strong>No new jobs selected.</strong>"
        f"<br>Found in this block: {found}"
        f"<br>Already seen: {already_seen}"
        f"<br>Rejected by history: {rejected_history}"
        f"<br>Rejected by profile: {rejected_profile}"
        f"<br>Rejected by cleaner/location: {rejected_cleaner_location}"
        "</li>"
    )


def build_email_html(jobs, run_stats=None, search_profile=LOCAL_STUDENT_PROFILE):
    jobs = sorted_jobs([enrich_email_job(job) for job in jobs])
    top_match_score, recommended_count = email_summary(jobs)
    groups = grouped_jobs(jobs, search_profile)
    blocks = []
    for block in blocks_for_profile(search_profile):
        block_jobs = groups[block]
        if block_jobs:
            items = "".join(render_job(job) for job in block_jobs)
        else:
            items = empty_block_diagnostics(block, run_stats, search_profile)
        blocks.append(f"<h2>{html.escape(block)}</h2><ol>{items}</ol>")

    return (
        "<html><body>"
        "<h1>Job Intelligence V2</h1>"
        f"{render_action_plan(jobs, run_stats or {})}"
        f"<p><strong>Total jobs in email:</strong> {len(jobs)}</p>"
        f"<p><strong>Top match score:</strong> {top_match_score}</p>"
        f"<p><strong>Recommended to apply today:</strong> {recommended_count}</p>"
        f"{''.join(blocks)}"
        f"{render_run_stats(run_stats or {})}"
        "</body></html>"
    )


def send_html_email(subject, body):
    message = MIMEText(body, "html", "utf-8")
    message["Subject"] = subject
    message["From"] = os.environ["EMAIL_FROM"]
    message["To"] = os.environ["EMAIL_TO"]

    recipients = [item.strip() for item in os.environ["EMAIL_TO"].split(",") if item.strip()]
    with smtplib.SMTP(os.environ["EMAIL_SMTP_HOST"], int(os.environ["EMAIL_SMTP_PORT"])) as smtp:
        smtp.starttls()
        smtp.login(os.environ["EMAIL_SMTP_USER"], os.environ["EMAIL_SMTP_PASSWORD"])
        smtp.sendmail(os.environ["EMAIL_FROM"], recipients, message.as_string())


def subject_for_profile(search_profile):
    if search_profile == REMOTE_PROFILE:
        return REMOTE_SUBJECT
    return SUBJECT


def default_input_for_profile(search_profile):
    if search_profile == REMOTE_PROFILE:
        return REMOTE_INPUT_PATH
    return DEFAULT_INPUT_PATH


def default_stats_for_profile(search_profile):
    if search_profile == REMOTE_PROFILE:
        return REMOTE_RUN_STATS_PATH
    return DEFAULT_RUN_STATS_PATH


def default_candidate_pool_for_profile(search_profile):
    if search_profile == REMOTE_PROFILE:
        return "output/v2_remote_candidate_pool.json"
    return "output/v2_candidate_pool.json"


def run_stats_with_candidate_pool(stats, search_profile=LOCAL_STUDENT_PROFILE):
    stats = dict(stats or {})
    if "candidate_pool" not in stats:
        stats["candidate_pool"] = load_candidate_pool(default_candidate_pool_for_profile(search_profile))
    return stats


def send_v2_email_report(
    input_path=DEFAULT_INPUT_PATH,
    top=DEFAULT_TOP,
    stats_path=DEFAULT_RUN_STATS_PATH,
    search_profile=LOCAL_STUDENT_PROFILE,
):
    jobs = sorted_jobs(email_selected_jobs(load_jobs(input_path)))[:top]
    if not jobs:
        print("No V2 jobs to email")
        return False

    if not email_enabled():
        print("Email disabled: EMAIL_ENABLED is not true")
        return False

    require_email_settings()
    send_html_email(
        subject_for_profile(search_profile),
        build_email_html(
            jobs,
            run_stats_with_candidate_pool(load_run_stats(stats_path), search_profile),
            search_profile=search_profile,
        ),
    )
    print(f"V2 email report sent: {len(jobs)} jobs")
    return True


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--search-profile", choices=[LOCAL_STUDENT_PROFILE, REMOTE_PROFILE], default=LOCAL_STUDENT_PROFILE)
    parser.add_argument("--input", default=None)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP)
    parser.add_argument("--stats", default=None)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    send_v2_email_report(
        args.input or default_input_for_profile(args.search_profile),
        args.top,
        args.stats or default_stats_for_profile(args.search_profile),
        search_profile=args.search_profile,
    )


if __name__ == "__main__":
    main()
