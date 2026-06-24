import argparse
import html
import json
import os
from email.mime.text import MIMEText
from pathlib import Path

from src.main import email_enabled, require_email_settings, smtplib


DEFAULT_INPUT_PATH = "output/v2_jobs.json"
DEFAULT_TOP = 100
SUBJECT = "Job Intelligence V2: Campania Part-Time + Remote Jobs"

BLOCKS = [
    "Campania part-time",
    "Hospitality / Hotel / Restaurant",
    "Cleaning / Pulizie",
    "Maintenance / Manutenzione",
    "Warehouse / GDO",
    "Remote / Data / AI",
    "Other",
]

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


def load_jobs(input_path):
    path = Path(input_path)
    if not path.exists():
        return []
    jobs = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(jobs, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return jobs


def job_text(job):
    return " ".join(
        str(job.get(field, "") or "")
        for field in ["title", "company", "location", "category", "query", "source"]
    ).lower()


def has_any(text, terms):
    return any(term in text for term in terms)


def is_campania_part_time(job, text):
    return (
        job.get("priority_bucket") == "campania_part_time"
        or (bool(job.get("part_time")) and has_any(text, LOCAL_TERMS))
    )


def classify_job(job):
    text = job_text(job)
    category = str(job.get("category", "") or "").lower()

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


def grouped_jobs(jobs):
    groups = {block: [] for block in BLOCKS}
    for job in jobs:
        groups[classify_job(job)].append(job)
    return groups


def render_job(job):
    title = html.escape(str(job.get("title", "") or ""))
    company = html.escape(str(job.get("company", "") or ""))
    location = html.escape(str(job.get("location", "") or ""))
    score = html.escape(str(job.get("score", "") or ""))
    match_score = html.escape(str(job.get("match_score", "") or ""))
    student_score = html.escape(str(job.get("student_score", "") or ""))
    candidate_score = html.escape(str(job.get("candidate_score", "") or ""))
    category = html.escape(str(job.get("category", "") or ""))
    source = html.escape(str(job.get("source", "") or ""))
    url = html.escape(str(job.get("url", "") or ""), quote=True)
    match_line = f"⭐⭐⭐⭐⭐ Match {match_score}%" if match_score else "⭐⭐⭐⭐⭐ Match"

    return (
        "<li>"
        f"<h3>{title}</h3>"
        f"<p><strong>{match_line}</strong></p>"
        f"<p><strong>student:</strong> {student_score}</p>"
        f"<p><strong>candidate:</strong> {candidate_score}</p>"
        f"<p><strong>source:</strong> {source}</p>"
        f"<p><strong>Company:</strong> {company}</p>"
        f"<p><strong>Location:</strong> {location}</p>"
        f"<p><strong>Score:</strong> {score}</p>"
        f"<p><strong>Category:</strong> {category}</p>"
        f'<p><strong>URL:</strong> <a href="{url}">{url}</a></p>'
        "</li>"
    )


def build_email_html(jobs):
    groups = grouped_jobs(jobs)
    blocks = []
    for block in BLOCKS:
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
        f"{''.join(blocks)}"
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


def send_v2_email_report(input_path=DEFAULT_INPUT_PATH, top=DEFAULT_TOP):
    jobs = load_jobs(input_path)[:top]
    if not jobs:
        print("No V2 jobs to email")
        return False

    if not email_enabled():
        print("Email disabled: EMAIL_ENABLED is not true")
        return False

    require_email_settings()
    send_html_email(SUBJECT, build_email_html(jobs))
    print(f"V2 email report sent: {len(jobs)} jobs")
    return True


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    send_v2_email_report(args.input, args.top)


if __name__ == "__main__":
    main()
