import argparse
import csv
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

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


DEFAULT_OUTPUT_PATH = "output/v2_jobs.json"
DEFAULT_LIMIT = 5
DEFAULT_TOP = 50
PRIORITY_ORDER = {
    "campania_part_time": 0,
    "remote_data": 1,
    "local_general": 2,
    "other": 3,
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
    "score",
    "found_at",
]
RESULT_TYPE_OUTPUT_FIELDS = OUTPUT_FIELDS + ["result_type", "url_result_type"]


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


def normalize_job(job):
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


def sort_jobs(jobs):
    return sorted(
        jobs,
        key=lambda job: (
            PRIORITY_ORDER.get(job.get("priority_bucket"), PRIORITY_ORDER["other"]),
            -int(job.get("score") or 0),
        ),
    )


def aggregate_jobs(
    collector_names=None,
    limit=DEFAULT_LIMIT,
    top=DEFAULT_TOP,
    campania_part_time_first=False,
    clean_results=False,
):
    jobs = []
    collector_names = collector_names or enabled_collectors()
    for name in collector_names:
        collector_jobs = run_collector(name, limit, top, campania_part_time_first)
        print(f"Collector {name} returned: {len(collector_jobs)} jobs")
        jobs.extend(normalize_job(job) for job in collector_jobs)

    jobs = deduplicate_jobs(jobs)
    jobs = sort_jobs(jobs)
    if clean_results:
        jobs, summary = clean_results_with_summary(jobs)
        print_cleaning_summary(summary)
    return jobs[:top]


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
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP)
    parser.add_argument("--campania-part-time-first", action="store_true")
    parser.add_argument("--clean-results", action="store_true")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    jobs = aggregate_jobs(
        parse_collectors(args.collectors),
        limit=args.limit,
        top=args.top,
        campania_part_time_first=args.campania_part_time_first,
        clean_results=args.clean_results,
    )
    export_jobs(jobs, args.output)


if __name__ == "__main__":
    main()
