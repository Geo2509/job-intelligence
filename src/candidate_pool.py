import argparse
import json
import zipfile
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from src.job_result_cleaner import clean_job


DEFAULT_POOL_PATH = "output/v2_candidate_pool.json"
DEFAULT_COLLECTOR_STATS_PATH = "output/v2_collector_stats.json"
MATCH_THRESHOLD = 70
POOL_FIELDS = [
    ("Match Score", "match_score"),
    ("Student Score", "student_score"),
    ("Candidate Score", "candidate_score"),
    ("Base Score", "score"),
    ("Title", "title"),
    ("Company", "company"),
    ("Location", "location"),
    ("Location Fit", "location_fit"),
    ("Source", "source"),
    ("Collector", "collector"),
    ("Category", "category"),
    ("Priority Bucket", "priority_bucket"),
    ("URL", "url"),
    ("History Status", "history_status"),
    ("Rejection Reason", "rejection_reason"),
    ("First Seen", "first_seen"),
    ("Last Seen", "last_seen"),
    ("Last Sent", "last_sent"),
    ("Sent Count", "sent_count"),
    ("Job ID", "job_id"),
    ("Content Hash", "content_hash"),
    ("Action", "action"),
]
COLLECTOR_STAT_FIELDS = [
    "collector",
    "collected",
    "after_cleaner",
    "real_jobs",
    "allowed_local",
    "remote",
    "excluded_far",
    "unknown_location",
    "search_pages",
    "category_pages",
    "career_pages",
    "company_pages",
    "articles",
    "excluded_domains",
    "history_seen",
    "history_updated",
    "history_new",
    "email_jobs",
]


def score_value(job, field):
    try:
        return int(job.get(field) or 0)
    except (TypeError, ValueError):
        return 0


def sort_pool(jobs):
    return sorted(
        jobs,
        key=lambda job: (
            -score_value(job, "match_score"),
            -score_value(job, "student_score"),
            -score_value(job, "candidate_score"),
            -score_value(job, "score"),
        ),
    )


def is_real_job(job):
    return job.get("result_type") == "job" and job.get("url_result_type") == "real_job"


def classify_candidates(jobs):
    return [clean_job(job) for job in jobs]


def apply_history_fields(job, history):
    job = dict(job)
    record = history.get(job.get("job_id"), {}) if history else {}
    found_at = job.get("found_at", "")
    job["first_seen"] = record.get("first_seen") or found_at
    job["last_seen"] = record.get("last_seen") or found_at
    job["last_sent"] = record.get("last_sent") or ""
    job["sent_count"] = int(record.get("sent_count") or 0)
    return job


def rejection_reason(job, email_job_ids):
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
    if job.get("job_id") in email_job_ids:
        return "passed"
    if job.get("location_fit") == "excluded_far":
        return "excluded_far"
    if job.get("location_fit") == "unknown" and not bool(job.get("remote")):
        return "unknown_location"
    if job.get("history_status") == "SEEN":
        return "history_seen"
    if score_value(job, "match_score") < MATCH_THRESHOLD:
        return "low_match"
    return "email_limit"


def build_candidate_pool(candidates, email_jobs=None, history=None):
    email_job_ids = {job.get("job_id") for job in email_jobs or [] if job.get("job_id")}
    pool = []
    for job in candidates:
        if not is_real_job(job):
            continue
        item = apply_history_fields(job, history or {})
        item["collector"] = item.get("collector") or item.get("source", "")
        item["rejection_reason"] = rejection_reason(item, email_job_ids)
        item.setdefault("action", "")
        pool.append(item)
    return sort_pool(pool)


def collector_name(job):
    return str(job.get("collector") or job.get("source") or "unknown").lower()


def new_collector_stats(name):
    stats = {field: 0 for field in COLLECTOR_STAT_FIELDS if field != "collector"}
    stats["collector"] = name
    return stats


def build_collector_stats(collected_counts, candidates, email_jobs=None):
    stats_by_collector = {
        name: new_collector_stats(name)
        for name in collected_counts
    }
    for name, count in collected_counts.items():
        stats_by_collector[name]["collected"] = count

    for job in candidates:
        name = collector_name(job)
        stats = stats_by_collector.setdefault(name, new_collector_stats(name))
        result_type = job.get("result_type")
        if is_real_job(job):
            stats["after_cleaner"] += 1
            stats["real_jobs"] += 1
            location_fit = job.get("location_fit")
            if location_fit == "allowed_local":
                stats["allowed_local"] += 1
            elif location_fit == "remote" or bool(job.get("remote")):
                stats["remote"] += 1
            elif location_fit == "excluded_far":
                stats["excluded_far"] += 1
            elif location_fit == "unknown":
                stats["unknown_location"] += 1

            status = job.get("history_status")
            if status == "SEEN":
                stats["history_seen"] += 1
            elif status == "UPDATED":
                stats["history_updated"] += 1
            elif status == "NEW":
                stats["history_new"] += 1
        elif result_type == "search_page":
            stats["search_pages"] += 1
        elif result_type == "category_page":
            stats["category_pages"] += 1
        elif result_type == "career_page":
            stats["career_pages"] += 1
        elif result_type == "company_page":
            stats["company_pages"] += 1
        elif result_type == "article":
            stats["articles"] += 1
        elif result_type == "excluded_domain":
            stats["excluded_domains"] += 1

    for job in email_jobs or []:
        name = collector_name(job)
        stats = stats_by_collector.setdefault(name, new_collector_stats(name))
        stats["email_jobs"] += 1

    return [
        {field: stats.get(field, 0) for field in COLLECTOR_STAT_FIELDS}
        for _, stats in sorted(stats_by_collector.items())
    ]


def write_json(rows, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {path}: {len(rows)} rows")


def column_letter(index):
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def cell_xml(column_index, row_index, value, style=None):
    cell_ref = f"{column_letter(column_index)}{row_index}"
    style_attr = f' s="{style}"' if style is not None else ""
    if isinstance(value, int):
        return f'<c r="{cell_ref}"{style_attr}><v>{value}</v></c>'
    return f'<c r="{cell_ref}" t="inlineStr"{style_attr}><is><t>{escape(str(value or ""))}</t></is></c>'


def auto_widths(rows):
    widths = []
    column_count = max((len(row) for row in rows), default=0)
    for index in range(column_count):
        width = max((len(str(row[index] or "")) for row in rows if index < len(row)), default=8)
        widths.append(min(max(width + 2, 10), 60))
    return widths


def load_existing_actions(xlsx_path):
    path = Path(xlsx_path)
    if not path.exists():
        return {}
    try:
        with zipfile.ZipFile(path) as xlsx:
            sheet_xml = xlsx.read("xl/worksheets/sheet1.xml")
    except (KeyError, zipfile.BadZipFile):
        return {}

    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ElementTree.fromstring(sheet_xml)
    rows = []
    for row in root.findall(".//m:sheetData/m:row", ns):
        values = []
        for cell in row.findall("m:c", ns):
            text_node = cell.find("m:is/m:t", ns)
            value_node = cell.find("m:v", ns)
            values.append((text_node.text if text_node is not None else value_node.text if value_node is not None else "") or "")
        rows.append(values)
    if not rows:
        return {}
    headers = rows[0]
    try:
        job_id_index = headers.index("Job ID")
        action_index = headers.index("Action")
    except ValueError:
        return {}
    actions = {}
    for row in rows[1:]:
        if len(row) <= max(job_id_index, action_index):
            continue
        if row[job_id_index] and row[action_index]:
            actions[row[job_id_index]] = row[action_index]
    return actions


def apply_preserved_actions(jobs, xlsx_path):
    actions = load_existing_actions(xlsx_path)
    if not actions:
        return jobs
    updated = []
    for job in jobs:
        item = dict(job)
        if item.get("job_id") in actions:
            item["action"] = actions[item["job_id"]]
        updated.append(item)
    return updated


def workbook_xml(sheet_name):
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""


CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""
ROOT_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
WORKBOOK_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""
STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>
  <dxfs count="4">
    <dxf><fill><patternFill patternType="solid"><fgColor rgb="FFC6EFCE"/><bgColor indexed="64"/></patternFill></fill></dxf>
    <dxf><fill><patternFill patternType="solid"><fgColor rgb="FFFFEB9C"/><bgColor indexed="64"/></patternFill></fill></dxf>
    <dxf><fill><patternFill patternType="solid"><fgColor rgb="FFF4B183"/><bgColor indexed="64"/></patternFill></fill></dxf>
    <dxf><fill><patternFill patternType="solid"><fgColor rgb="FFFFC7CE"/><bgColor indexed="64"/></patternFill></fill></dxf>
  </dxfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def write_xlsx(rows, headers, output_path, sheet_name="candidate_pool", conditional_match=False):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = [headers] + rows
    widths = auto_widths(table)
    cols_xml = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    )
    sheet_rows = []
    for row_index, row in enumerate(table, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            style = 1 if row_index == 1 else None
            cells.append(cell_xml(column_index, row_index, value, style=style))
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    last_column = column_letter(len(headers))
    last_row = max(len(table), 1)
    data_ref = f"A1:{last_column}{last_row}"
    match_ref = f"A2:A{last_row}" if last_row >= 2 else "A2:A2"
    conditional_xml = ""
    if conditional_match:
        conditional_xml = (
            f'<conditionalFormatting sqref="{match_ref}">'
            '<cfRule type="cellIs" dxfId="0" priority="1" operator="greaterThanOrEqual"><formula>90</formula></cfRule>'
            '<cfRule type="cellIs" dxfId="1" priority="2" operator="between"><formula>80</formula><formula>89</formula></cfRule>'
            '<cfRule type="cellIs" dxfId="2" priority="3" operator="between"><formula>70</formula><formula>79</formula></cfRule>'
            '<cfRule type="cellIs" dxfId="3" priority="4" operator="lessThan"><formula>70</formula></cfRule>'
            '</conditionalFormatting>'
        )
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        f'<cols>{cols_xml}</cols>'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        f'<autoFilter ref="{data_ref}"/>'
        f'{conditional_xml}'
        '</worksheet>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as xlsx:
        xlsx.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        xlsx.writestr("_rels/.rels", ROOT_RELS_XML)
        xlsx.writestr("xl/workbook.xml", workbook_xml(sheet_name))
        xlsx.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS_XML)
        xlsx.writestr("xl/styles.xml", STYLES_XML)
        xlsx.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    print(f"Saved {path}: {len(rows)} rows")


def export_candidate_pool(pool, output_path=DEFAULT_POOL_PATH):
    xlsx_path = Path(output_path).with_suffix(".xlsx")
    pool = apply_preserved_actions(pool, xlsx_path)
    write_json(pool, output_path)
    headers = [label for label, _ in POOL_FIELDS]
    rows = [
        [
            score_value(job, field) if field in {"match_score", "student_score", "candidate_score", "score", "sent_count"} else job.get(field, "")
            for _, field in POOL_FIELDS
        ]
        for job in pool
    ]
    write_xlsx(rows, headers, xlsx_path, conditional_match=True)
    return pool


def export_collector_stats(stats, output_path=DEFAULT_COLLECTOR_STATS_PATH):
    write_json(stats, output_path)
    rows = [[row.get(field, 0) for field in COLLECTOR_STAT_FIELDS] for row in stats]
    write_xlsx(rows, COLLECTOR_STAT_FIELDS, Path(output_path).with_suffix(".xlsx"), sheet_name="collector_stats")


def load_pool(input_path=DEFAULT_POOL_PATH):
    path = Path(input_path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return data


def filter_pool(jobs, source=None, location=None, reason=None, top=None):
    filtered = deepcopy(jobs)
    if source:
        source = str(source).lower()
        filtered = [
            job
            for job in filtered
            if str(job.get("source") or job.get("collector") or "").lower() == source
        ]
    if location:
        location = str(location).lower()
        filtered = [
            job
            for job in filtered
            if str(job.get("location_fit") or "").lower() == location
        ]
    if reason:
        reason = str(reason).lower()
        filtered = [
            job
            for job in filtered
            if str(job.get("rejection_reason") or "").lower() == reason
        ]
    if top is not None:
        filtered = filtered[:top]
    return filtered


def print_pool(jobs):
    for job in jobs:
        print(
            "\t".join(
                [
                    str(job.get("match_score", "")),
                    str(job.get("source", "")),
                    str(job.get("location_fit", "")),
                    str(job.get("rejection_reason", "")),
                    str(job.get("title", "")),
                    str(job.get("url", "")),
                ]
            )
        )


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=DEFAULT_POOL_PATH)
    parser.add_argument("--source", default=None)
    parser.add_argument("--location", default=None)
    parser.add_argument("--reason", default=None)
    parser.add_argument("--top", type=int, default=None)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    jobs = filter_pool(
        load_pool(args.input),
        source=args.source,
        location=args.location,
        reason=args.reason,
        top=args.top,
    )
    print_pool(jobs)


if __name__ == "__main__":
    main()
