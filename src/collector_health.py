from pathlib import Path

from src.candidate_pool import write_json, write_xlsx


DEFAULT_HEALTH_PATH = "output/collector_health.json"
DEFAULT_RECOMMENDATIONS_PATH = "output/collector_recommendations.md"
HEALTH_FIELDS = [
    "collector",
    "raw_collected",
    "after_cleaner",
    "real_jobs",
    "candidate_pool",
    "new",
    "updated",
    "seen",
    "resurfaced",
    "email",
    "removed_by_cleaner",
    "removed_by_location",
    "removed_by_history",
    "collector_health_status",
    "collector_health_score",
    "recommendation",
]
DETAIL_EXTRACTION_TYPES = [
    "search_pages",
    "category_pages",
    "career_pages",
    "company_pages",
]


def int_value(row, field):
    try:
        return int(row.get(field) or 0)
    except (TypeError, ValueError):
        return 0


def collector_name(job):
    return str(job.get("collector") or job.get("source") or "unknown").lower()


def candidate_pool_counts(candidate_pool):
    counts = {}
    for job in candidate_pool or []:
        name = collector_name(job)
        counts[name] = counts.get(name, 0) + 1
    return counts


def removed_by_location(row):
    return int_value(row, "excluded_far") + int_value(row, "unknown_location")


def removed_by_cleaner(row):
    collected = int_value(row, "collected")
    after_cleaner = int_value(row, "after_cleaner")
    return max(0, collected - after_cleaner)


def needs_detail_extraction(row):
    if int_value(row, "real_jobs") > 0:
        return False
    return any(int_value(row, field) > 0 for field in DETAIL_EXTRACTION_TYPES)


def health_status(row):
    collected = int_value(row, "collected")
    real_jobs = int_value(row, "real_jobs")
    email_jobs = int_value(row, "email_jobs")
    history_seen = int_value(row, "history_seen")
    removed_cleaner = removed_by_cleaner(row)
    candidate_pool = int_value(row, "candidate_pool")

    after_cleaner = int_value(row, "after_cleaner")
    if (
        email_jobs > candidate_pool
        or candidate_pool > real_jobs
        or real_jobs > after_cleaner
        or after_cleaner > collected
    ):
        return "inconsistent"

    if collected == 0:
        return "error"
    if needs_detail_extraction(row):
        return "needs_detail_extraction"
    if real_jobs == 0 and removed_cleaner > 0:
        return "cleaner_removed"
    if real_jobs == 0:
        return "no_real_jobs"
    if email_jobs == 0 and history_seen >= real_jobs:
        return "history_only"
    return "healthy"


def health_score(row, status):
    collected = int_value(row, "collected")
    real_jobs = int_value(row, "real_jobs")
    email_jobs = int_value(row, "email_jobs")
    location_removed = removed_by_location(row)

    if status == "inconsistent":
        return 0
    if status == "error":
        return 0
    if status == "needs_detail_extraction":
        return 20
    if status == "no_real_jobs":
        return 10
    if status == "cleaner_removed":
        return 30
    if status == "history_only":
        return 80

    score = 85
    if collected:
        score += round((real_jobs / collected) * 10)
    if real_jobs:
        score += round((email_jobs / real_jobs) * 5)
    if location_removed:
        score -= min(20, location_removed * 2)
    return max(0, min(100, int(score)))


def recommendation_for(row, status):
    collector = row.get("collector", "unknown")
    real_jobs = int_value(row, "real_jobs")
    email_jobs = int_value(row, "email_jobs")
    history_seen = int_value(row, "history_seen")
    history_new = int_value(row, "history_new")
    location_removed = removed_by_location(row)

    if status == "inconsistent":
        return "Dashboard counts inconsistent: check source arrays"
    if status == "healthy":
        if history_new:
            return f"{collector}: Healthy, {history_new} NEW jobs"
        if history_seen:
            return f"{collector}: Healthy, {history_seen} jobs skipped by History"
        if real_jobs <= 1:
            return f"{collector}: Healthy, only {real_jobs} real job; improve Detail Extraction"
        return f"{collector}: Healthy, {email_jobs} jobs in email"
    if status == "history_only":
        return f"{collector}: Healthy, {history_seen} jobs skipped by History"
    if status == "needs_detail_extraction":
        return f"{collector}: 0 real jobs; Recommendation: Detail Extraction"
    if status == "cleaner_removed":
        return f"{collector}: Cleaner removed all jobs; inspect URL patterns and result cleaning"
    if status == "no_real_jobs":
        return f"{collector}: 0 real jobs; Recommendation: Detail Extraction"
    if status == "error":
        return f"{collector}: collector returned no jobs or failed; inspect collector logs"
    if location_removed:
        return f"{collector}: {location_removed} jobs removed by location"
    return f"{collector}: inspect collector health"


def build_collector_health(collector_stats, candidate_pool=None):
    pool_counts = candidate_pool_counts(candidate_pool)
    rows = []
    for row in collector_stats or []:
        collector = str(row.get("collector") or "unknown")
        pool_count = int_value(row, "candidate_pool") if candidate_pool is None else pool_counts.get(collector, 0)
        status_row = dict(row)
        status_row["candidate_pool"] = pool_count
        status = health_status(status_row)
        health = {
            "collector": collector,
            "raw_collected": int_value(row, "collected"),
            "after_cleaner": int_value(row, "after_cleaner"),
            "real_jobs": int_value(row, "real_jobs"),
            "candidate_pool": pool_count,
            "new": int_value(row, "history_new"),
            "updated": int_value(row, "history_updated"),
            "seen": int_value(row, "history_seen"),
            "resurfaced": int_value(row, "history_resurfaced"),
            "email": int_value(row, "email_jobs"),
            "removed_by_cleaner": removed_by_cleaner(row),
            "removed_by_location": removed_by_location(row),
            "removed_by_history": int_value(row, "history_seen"),
            "collector_health_status": status,
            "collector_health_score": health_score(status_row, status),
        }
        health["recommendation"] = recommendation_for(status_row, status)
        rows.append(health)
    return sorted(rows, key=lambda item: item["collector"])


def write_recommendations(rows, output_path=DEFAULT_RECOMMENDATIONS_PATH):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Collector Recommendations", ""]
    for row in rows:
        lines.extend([
            f"## {row['collector']}",
            "",
            f"Status: {row['collector_health_status']}",
            "",
            f"Health score: {row['collector_health_score']}",
            "",
            row["recommendation"],
            "",
        ])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Saved {path}: {len(rows)} rows")


def export_collector_health(
    rows,
    output_path=DEFAULT_HEALTH_PATH,
    recommendations_path=DEFAULT_RECOMMENDATIONS_PATH,
):
    write_json(rows, output_path)
    xlsx_path = Path(output_path).with_suffix(".xlsx")
    table_rows = [[row.get(field, "") for field in HEALTH_FIELDS] for row in rows]
    write_xlsx(table_rows, HEALTH_FIELDS, xlsx_path, sheet_name="collector_health")
    write_recommendations(rows, recommendations_path)
