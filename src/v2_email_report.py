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


def load_jobs(input_path):
    path = Path(input_path)
    if not path.exists():
        return []
    jobs = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(jobs, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return jobs


def load_run_stats(stats_path=DEFAULT_RUN_STATS_PATH):
    path = Path(stats_path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}")
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
    if category in {"hospitality", "hotel", "restaurant"} or has_any(text, HOSPITALITY_TERMS):
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
        "FALLBACK_FILL": 4,
        "SEEN": 5,
    }.get(str(job.get("selection_reason") or ""), 6)


def match_label(match_score):
    if match_score >= 90:
        return "⭐⭐⭐⭐⭐ Strong match"
    if match_score >= 80:
        return "⭐⭐⭐⭐ Good match"
    return "⭐⭐⭐ Consider"


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
        if score_value(job, "match_score") >= 80
    )
    return top_match_score, recommended_count


def render_run_stats(stats):
    if not stats:
        return ""
    collector_rows = stats.get("collector_stats") or []
    contribution = "".join(
        f"<li>{html.escape(str(row.get('collector', '')))}: {int(row.get('email_jobs') or 0)}</li>"
        for row in collector_rows
    )
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
        f"<ul>{contribution}</ul>"
        f"{render_collector_health(stats.get('collector_health') or [])}"
    )


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


def render_job(job):
    title = html.escape(str(job.get("title", "") or ""))
    company = html.escape(str(job.get("company", "") or ""))
    location = html.escape(str(job.get("location", "") or ""))
    score = html.escape(str(job.get("score", "") or ""))
    raw_match_score = score_value(job, "match_score")
    match_score = html.escape(str(job.get("match_score", "") or ""))
    student_score = html.escape(str(job.get("student_score", "") or ""))
    candidate_score = html.escape(str(job.get("candidate_score", "") or ""))
    remote_score = html.escape(str(job.get("remote_score", "") or ""))
    remote = html.escape(str(job.get("remote", "")))
    remote_reason = html.escape(str(job.get("remote_reason", "") or "none"))
    part_time = html.escape(str(job.get("part_time", "")))
    location_fit = html.escape(str(job.get("location_fit", "") or ""))
    category = html.escape(str(job.get("category", "") or ""))
    rejection_reason = html.escape(str(job.get("rejection_reason", "") or ""))
    country = html.escape(str(job.get("country_restriction", "") or ""))
    employment = html.escape(str(job.get("employment_type", "") or ""))
    salary = html.escape(str(job.get("salary_text", "") or ""))
    remote_category = html.escape(str(job.get("normalized_remote_category", "") or ""))
    positive_reason = html.escape(str(job.get("positive_reason", "") or ""))
    negative_reason = html.escape(str(job.get("negative_reason", "") or ""))
    source = html.escape(str(job.get("source", "") or ""))
    url = html.escape(str(job.get("url", "") or ""), quote=True)
    match = html.escape(match_label(raw_match_score))
    history_status = html.escape(history_status_label(job.get("history_status")))
    selection_reason = html.escape(str(job.get("selection_reason", "") or ""))
    status_line = f"<p><strong>Status:</strong> {history_status}</p>" if history_status else ""
    selection_line = f"<p><strong>Selection:</strong> {selection_reason}</p>" if selection_reason else ""

    return (
        "<li>"
        f"<h3>{title}</h3>"
        f"{status_line}"
        f"{selection_line}"
        f"<p><strong>{match}</strong></p>"
        f"<p><strong>Match:</strong> {match_score}</p>"
        f"<p><strong>Student:</strong> {student_score}</p>"
        f"<p><strong>Candidate:</strong> {candidate_score}</p>"
        f"<p><strong>Remote:</strong> {remote}</p>"
        f"<p><strong>Remote reason:</strong> {remote_reason}</p>"
        f"<p><strong>Part time:</strong> {part_time}</p>"
        f"<p><strong>Remote score:</strong> {remote_score}</p>"
        f"<p><strong>Location fit:</strong> {location_fit}</p>"
        f"<p><strong>Rejection reason:</strong> {rejection_reason}</p>"
        f"<p><strong>Source:</strong> {source}</p>"
        f"<p><strong>Category:</strong> {category}</p>"
        f"<p><strong>Remote category:</strong> {remote_category}</p>"
        f"<p><strong>Country:</strong> {country}</p>"
        f"<p><strong>Employment:</strong> {employment}</p>"
        f"<p><strong>Salary:</strong> {salary}</p>"
        f"<p><strong>Positive reasons:</strong> {positive_reason}</p>"
        f"<p><strong>Negative reasons:</strong> {negative_reason}</p>"
        f'<p><strong>URL:</strong> <a href="{url}">{url}</a></p>'
        f"<p><strong>Company:</strong> {company}</p>"
        f"<p><strong>Location:</strong> {location}</p>"
        f"<p><strong>Score:</strong> {score}</p>"
        "</li>"
    )


def build_email_html(jobs, run_stats=None, search_profile=LOCAL_STUDENT_PROFILE):
    jobs = sorted_jobs(jobs)
    top_match_score, recommended_count = email_summary(jobs)
    groups = grouped_jobs(jobs, search_profile)
    blocks = []
    for block in blocks_for_profile(search_profile):
        block_jobs = groups[block]
        if block_jobs:
            items = "".join(render_job(job) for job in block_jobs)
        else:
            items = "<li>No jobs in this block.</li>"
        blocks.append(f"<h2>{html.escape(block)}</h2><ol>{items}</ol>")

    return (
        "<html><body>"
        "<h1>Job Intelligence V2</h1>"
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


def send_v2_email_report(
    input_path=DEFAULT_INPUT_PATH,
    top=DEFAULT_TOP,
    stats_path=DEFAULT_RUN_STATS_PATH,
    search_profile=LOCAL_STUDENT_PROFILE,
):
    jobs = sorted_jobs(load_jobs(input_path))[:top]
    if not jobs:
        print("No V2 jobs to email")
        return False

    if not email_enabled():
        print("Email disabled: EMAIL_ENABLED is not true")
        return False

    require_email_settings()
    send_html_email(
        subject_for_profile(search_profile),
        build_email_html(jobs, load_run_stats(stats_path), search_profile=search_profile),
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
