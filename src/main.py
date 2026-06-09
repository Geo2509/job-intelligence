import argparse
import csv
import html
import os
import smtplib
import subprocess
import sys
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

from config_loader import QUERIES_ENV, SCORING_ENV, load_queries_config, load_scoring_config
from scoring_jobs import score_jobs


OUTPUT_DIR = Path("output/latest")
COLLECTORS = [
    ("arbeitnow", "arbeitnow_collector.py"),
    ("remotive", "remotive_collector.py"),
    ("remotejobs_org", "remotejobs_org_collector.py"),
    ("remotefirstjobs", "remotefirstjobs_collector.py"),
    ("jobicy", "jobicy_collector.py"),
    ("workanywhere", "workanywhere_collector.py"),
    ("smartjobspa", "smartjobspa_collector.py"),
    ("attalgroup", "attalgroup_collector.py"),
    ("direzionelavoro", "direzionelavoro_collector.py"),
    ("himalayas", "himalayas_collector.py"),
    ("reddit", "reddit_collector.py"),
    ("duckduckgo", "duckduckgo_collector.py"),
]
COLLECTOR_OUTPUT_FILES = {
    "arbeitnow": "arbeitnow_jobs.csv",
    "remotive": "remotive_jobs.csv",
    "remotejobs_org": "remotejobs_org_jobs.csv",
    "remotefirstjobs": "remotefirstjobs_jobs.csv",
    "jobicy": "jobicy_jobs.csv",
    "workanywhere": "workanywhere_jobs.csv",
    "smartjobspa": "smartjobspa_jobs.csv",
    "attalgroup": "attalgroup_jobs.csv",
    "direzionelavoro": "direzionelavoro_jobs.csv",
    "himalayas": "himalayas_jobs.csv",
    "reddit": "reddit_jobs.csv",
    "duckduckgo": "duckduckgo_jobs.csv",
}
FILTERS = [
    ("reddit", "filter_jobs.py", "reddit_jobs.csv"),
    ("himalayas", "himalayas_filter.py", "himalayas_jobs.csv"),
]


def run_script(script, env):
    subprocess.run([sys.executable, script], check=True, env=env)


def count_csv_rows(path):
    csv_path = Path(path)
    if not csv_path.exists():
        return 0
    with csv_path.open("r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def run_collectors(queries_file):
    env = os.environ.copy()
    env[QUERIES_ENV] = queries_file
    env["PYTHONUNBUFFERED"] = "1"
    counts = {}

    for name, script in COLLECTORS:
        print(f"Running collector: {name} ({script})")
        run_script(script, env)
        output_file = COLLECTOR_OUTPUT_FILES[name]
        counts[name] = count_csv_rows(output_file)
        print(f"Collector {name} found: {counts[name]} jobs")

    return counts


def run_filters(scoring_file):
    env = os.environ.copy()
    env[SCORING_ENV] = scoring_file
    env["PYTHONUNBUFFERED"] = "1"
    for name, script, input_file in FILTERS:
        if not Path(input_file).exists():
            print(f"Skipped {name} filter: missing {input_file}")
            continue
        print(f"Running filter: {name} ({script})")
        run_script(script, env)


def short_description(value, limit=500):
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


def top_jobs_rows(top_jobs, limit=20):
    if top_jobs.empty:
        return []
    return list(top_jobs.head(limit).to_dict("records"))


def priority_counts_text(scoring_result):
    counts = scoring_result.get("priority_counts", {})
    return [
        f"- HIGH jobs: {counts.get('HIGH', 0)}",
        f"- MEDIUM jobs: {counts.get('MEDIUM', 0)}",
        f"- LOW jobs: {counts.get('LOW', 0)}",
    ]


def write_summary(run_started, collector_counts, scoring_result, output_paths):
    rows = top_jobs_rows(scoring_result["top_jobs"], 20)
    lines = [
        "# Job Intelligence Run Summary",
        "",
        f"- Run date/time: {run_started.isoformat(timespec='seconds')}",
        f"- Collectors run: {', '.join(collector_counts)}",
        "",
        "## Jobs By Source",
    ]
    for source, count in collector_counts.items():
        lines.append(f"- {source}: {count}")

    lines.extend([
        "",
        "## Stage Statistics",
        f"- Collected: {scoring_result['collected']}",
        f"- After deduplication: {scoring_result['after_deduplication']}",
        f"- After filtering: {scoring_result['after_filtering']}",
        f"- After scoring threshold: {scoring_result['after_scoring_threshold']}",
        f"- Top jobs emailed: {scoring_result['top_jobs_emailed']}",
        f"- Top jobs min score: {scoring_result['top_jobs_score_stats']['min']}",
        f"- Top jobs max score: {scoring_result['top_jobs_score_stats']['max']}",
        f"- Top jobs average score: {scoring_result['top_jobs_score_stats']['average']}",
        "",
        "## Apply Priority",
        *priority_counts_text(scoring_result),
        "",
        "## Top 20 Jobs",
    ])

    if not rows:
        lines.append("No jobs passed scoring.")
    for index, row in enumerate(rows, start=1):
        title = row.get("title", "")
        score = row.get("job_score", "")
        priority = row.get("apply_priority", "")
        source = row.get("source", "")
        url = row.get("url", "")
        reasons = row.get("score_reason", "")
        lines.append(f"{index}. [{title}]({url}) — {priority}, score {score}, source {source}")
        if reasons:
            lines.append(f"   Reasons: {reasons}")

    lines.extend([
        "",
        "## Output Files",
    ])
    for path in output_paths:
        lines.append(f"- {path}")

    summary_path = OUTPUT_DIR / "run_summary.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved {summary_path}")
    return summary_path


def email_enabled():
    return os.environ.get("EMAIL_ENABLED", "").strip().lower() == "true"


def require_email_settings():
    required = [
        "EMAIL_SMTP_HOST",
        "EMAIL_SMTP_PORT",
        "EMAIL_SMTP_USER",
        "EMAIL_SMTP_PASSWORD",
        "EMAIL_FROM",
        "EMAIL_TO",
    ]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "EMAIL_ENABLED=true, but missing email settings: " + ", ".join(missing)
        )


def build_email_html(run_started, collector_counts, scoring_result):
    rows = top_jobs_rows(scoring_result["top_jobs"], 20)
    source_items = "".join(
        f"<li>{html.escape(str(source))}: {count}</li>"
        for source, count in collector_counts.items()
    )
    priority_counts = scoring_result.get("priority_counts", {})
    score_stats = scoring_result.get("top_jobs_score_stats", {"min": 0, "max": 0, "average": 0})
    priority_items = "".join(
        f"<li><strong>{priority} jobs:</strong> {priority_counts.get(priority, 0)}</li>"
        for priority in ["HIGH", "MEDIUM", "LOW"]
    )
    job_items = []
    for row in rows:
        title = html.escape(str(row.get("title", "")))
        source = html.escape(str(row.get("source", "")))
        score = html.escape(str(row.get("job_score", "")))
        priority = html.escape(str(row.get("apply_priority", "")))
        description = html.escape(short_description(row.get("description", ""), 500))
        reasons = html.escape(str(row.get("score_reason", "")))
        url = html.escape(str(row.get("url", "")), quote=True)
        job_items.append(
            "<li>"
            f"<h3>{title}</h3>"
            f"<p><strong>Priority:</strong> {priority} | <strong>Score:</strong> {score} | <strong>Source:</strong> {source}</p>"
            f"<p>{description}</p>"
            f"<p><strong>Reasons:</strong> {reasons}</p>"
            f'<p><a href="{url}">Open job</a></p>'
            "</li>"
        )

    jobs_html = "".join(job_items) or "<li>No jobs passed scoring.</li>"
    return f"""
    <html>
      <body>
        <h1>Job Intelligence Report</h1>
        <p><strong>Run date/time:</strong> {html.escape(run_started.isoformat(timespec='seconds'))}</p>
        <h2>Jobs by source</h2>
        <ul>{source_items}</ul>
        <h2>Stage statistics</h2>
        <ul>
          <li>Collected: {scoring_result['collected']}</li>
          <li>After deduplication: {scoring_result['after_deduplication']}</li>
          <li>After filtering: {scoring_result['after_filtering']}</li>
          <li>After scoring threshold: {scoring_result['after_scoring_threshold']}</li>
          <li>Top jobs emailed: {scoring_result['top_jobs_emailed']}</li>
          <li>Top jobs min score: {score_stats['min']}</li>
          <li>Top jobs max score: {score_stats['max']}</li>
          <li>Top jobs average score: {score_stats['average']}</li>
        </ul>
        <h2>Apply priority</h2>
        <ul>{priority_items}</ul>
        <h2>Top 20 jobs</h2>
        <ol>{jobs_html}</ol>
      </body>
    </html>
    """


def send_email_report(run_started, collector_counts, scoring_result):
    if not email_enabled():
        print("Email disabled: EMAIL_ENABLED is not true")
        return False

    require_email_settings()
    message = MIMEText(build_email_html(run_started, collector_counts, scoring_result), "html", "utf-8")
    message["Subject"] = f"Job Intelligence Report — {run_started.date().isoformat()}"
    message["From"] = os.environ["EMAIL_FROM"]
    message["To"] = os.environ["EMAIL_TO"]

    recipients = [item.strip() for item in os.environ["EMAIL_TO"].split(",") if item.strip()]
    with smtplib.SMTP(os.environ["EMAIL_SMTP_HOST"], int(os.environ["EMAIL_SMTP_PORT"])) as smtp:
        smtp.starttls()
        smtp.login(os.environ["EMAIL_SMTP_USER"], os.environ["EMAIL_SMTP_PASSWORD"])
        smtp.sendmail(os.environ["EMAIL_FROM"], recipients, message.as_string())

    print("Email report sent")
    return True


def validate_output_files(paths):
    missing = [str(path) for path in paths if not Path(path).exists()]
    if missing:
        raise RuntimeError("Missing output files: " + ", ".join(missing))
    print("Output file check passed:")
    for path in paths:
        print(f"- {path}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", required=True, help="Path to queries YAML config")
    parser.add_argument("--scoring", required=True, help="Path to scoring YAML config")
    return parser.parse_args()


def main():
    try:
        args = parse_args()
        run_started = datetime.now(ZoneInfo("Europe/Rome"))

        print(f"Using queries config: {args.queries}")
        print(f"Using scoring config: {args.scoring}")
        print(f"EMAIL_ENABLED: {os.environ.get('EMAIL_ENABLED', '')}")
        load_queries_config(args.queries)
        load_scoring_config(args.scoring)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        collector_counts = run_collectors(args.queries)
        run_filters(args.scoring)

        csv_path = OUTPUT_DIR / "jobs_scored.csv"
        xlsx_path = OUTPUT_DIR / "jobs_scored.xlsx"
        top_csv_path = OUTPUT_DIR / "top_50_jobs.csv"
        top_jobs_xlsx_path = OUTPUT_DIR / "top_jobs.xlsx"
        scoring_result = score_jobs(
            scoring_file=args.scoring,
            csv_path=csv_path,
            xlsx_path=xlsx_path,
            top_csv_path=top_csv_path,
            top_xlsx_path=top_jobs_xlsx_path,
        )

        print(f"Jobs after filtering: {scoring_result['after_filtering']}")
        print(f"Jobs in final result: {scoring_result['after_scoring']}")
        summary_path = write_summary(
            run_started,
            collector_counts,
            scoring_result,
            [csv_path, xlsx_path, top_csv_path, top_jobs_xlsx_path, OUTPUT_DIR / "run_summary.md"],
        )
        validate_output_files([csv_path, xlsx_path, top_csv_path, top_jobs_xlsx_path, summary_path])
        email_was_sent = send_email_report(run_started, collector_counts, scoring_result)
        print(f"Email sent: {email_was_sent}")
        print(f"Output files saved in: {OUTPUT_DIR}")
        print(f"Summary: {summary_path}")
        print("FINAL STATUS: SUCCESS")
    except Exception as exc:
        print(f"FINAL STATUS: FAILED - {exc}")
        raise


if __name__ == "__main__":
    main()
