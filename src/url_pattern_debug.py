import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

from src.job_result_cleaner import clean_job
from src.job_url_patterns import classify_url_detail, load_url_patterns


DEFAULT_DEBUG_PATH = "output/url_pattern_debug.json"
DEFAULT_UNKNOWN_URLS_PATH = "output/unknown_urls.xlsx"
DEFAULT_RECOMMENDATIONS_PATH = "output/url_pattern_recommendations.md"
DEBUG_FIELDS = [
    "collector",
    "url",
    "title",
    "detected_type",
    "matched_pattern",
    "classification",
    "final_status",
    "rejection_reason",
]
UNKNOWN_FIELDS = [
    "URL",
    "Title",
    "HTML Title",
    "URL Path",
    "Detected Type",
    "Rejection Reason",
]
EXPLORER_FIELDS = [
    "Collector",
    "URL",
    "Title",
    "Detected Type",
    "Matched Pattern",
    "Classification",
    "Final Status",
    "Rejection Reason",
]
REMOVED_REASON_BY_TYPE = {
    "search_page": "matched_search_page",
    "category_page": "matched_category_page",
    "aggregator_page": "matched_category_page",
    "company_page": "matched_company_page",
    "career_page": "matched_company_page",
    "profile": "matched_profile",
    "article": "matched_article",
    "excluded_domain": "matched_excluded_domain",
}


def url_key(job):
    url = str(job.get("url") or "").strip().lower()
    if url:
        return url
    return "|".join([
        str(job.get("collector") or job.get("source") or "").strip().lower(),
        str(job.get("title") or "").strip().lower(),
        str(job.get("company") or "").strip().lower(),
        str(job.get("location") or "").strip().lower(),
    ])


def collector_name(job):
    return str(job.get("collector") or job.get("source") or "unknown").strip() or "unknown"


def score_value(job, field):
    try:
        return int(job.get(field) or 0)
    except (TypeError, ValueError):
        return 0


def rejection_reason(job, duplicate=False):
    if duplicate:
        return "duplicate"
    result_type = job.get("result_type")
    if result_type in REMOVED_REASON_BY_TYPE:
        return REMOVED_REASON_BY_TYPE[result_type]
    if job.get("url_result_type") == "unknown" or result_type == "unknown":
        return "unknown_pattern"
    if job.get("location_fit") == "excluded_far":
        return "excluded_location"
    if job.get("location_fit") == "unknown" and not bool(job.get("remote")):
        return "excluded_location"
    if job.get("history_status") == "SEEN":
        return "history_seen"
    if score_value(job, "match_score") and score_value(job, "match_score") < 70:
        return "low_score"
    return ""


def detected_type_for_job(job):
    url_result_type = job.get("url_result_type")
    result_type = job.get("result_type")
    if url_result_type and url_result_type != "unknown":
        return url_result_type
    if result_type == "job":
        return "real_job"
    return result_type or url_result_type or "unknown"


def final_status_for_job(job, email_keys, duplicate=False):
    if duplicate:
        return "rejected"
    key = url_key(job)
    if key in email_keys:
        return "email"
    if job.get("result_type") == "job" and job.get("url_result_type") == "real_job":
        return "candidate_pool"
    return "rejected"


def classification_for_status(final_status):
    if final_status in {"email", "candidate_pool"}:
        return "accepted"
    return "rejected"


def build_url_pattern_debug_rows(raw_jobs, classified_jobs=None, email_jobs=None):
    patterns = load_url_patterns()
    classified_by_key = {
        url_key(job): job
        for job in classified_jobs or []
    }
    email_keys = {url_key(job) for job in email_jobs or []}
    seen = set()
    rows = []

    for raw_job in raw_jobs:
        key = url_key(raw_job)
        duplicate = key in seen
        seen.add(key)
        classified = classified_by_key.get(key)
        if classified is None:
            classified = clean_job(raw_job, patterns)
        detail = classify_url_detail(raw_job.get("url", ""), patterns)
        matched_pattern = detail.get("matched_pattern") or "none"
        detected_type = detected_type_for_job(classified)
        final_status = final_status_for_job(classified, email_keys, duplicate=duplicate)
        reason = rejection_reason(classified, duplicate=duplicate)
        rows.append({
            "collector": collector_name(raw_job),
            "url": raw_job.get("url", ""),
            "title": raw_job.get("title", ""),
            "detected_type": detected_type,
            "matched_pattern": matched_pattern,
            "classification": classification_for_status(final_status),
            "final_status": final_status,
            "rejection_reason": reason,
        })
    return rows


def write_json(rows, output_path=DEFAULT_DEBUG_PATH):
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
        widths.append(min(max(width + 2, 10), 80))
    return widths


def safe_sheet_name(name, used):
    cleaned = re.sub(r"[\[\]:*?/\\]", " ", str(name or "Sheet")).strip() or "Sheet"
    cleaned = cleaned[:31]
    candidate = cleaned
    counter = 2
    while candidate in used:
        suffix = f" {counter}"
        candidate = f"{cleaned[:31 - len(suffix)]}{suffix}"
        counter += 1
    used.add(candidate)
    return candidate


def sheet_xml(headers, rows):
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
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        f'<cols>{cols_xml}</cols>'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        f'<autoFilter ref="A1:{last_column}{last_row}"/>'
        '</worksheet>'
    )


def workbook_xml(sheet_names):
    sheets = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheet_names, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheets}</sheets>"
        "</workbook>"
    )


def workbook_rels_xml(sheet_count):
    rels = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    )
    rels += (
        f'<Relationship Id="rId{sheet_count + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{rels}</Relationships>"
    )


def content_types_xml(sheet_count):
    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f"{overrides}"
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '</Types>'
    )


ROOT_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def write_workbook(sheets, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    used = set()
    sheet_names = [safe_sheet_name(name, used) for name, _, _ in sheets]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as xlsx:
        xlsx.writestr("[Content_Types].xml", content_types_xml(len(sheets)))
        xlsx.writestr("_rels/.rels", ROOT_RELS_XML)
        xlsx.writestr("xl/workbook.xml", workbook_xml(sheet_names))
        xlsx.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml(len(sheets)))
        xlsx.writestr("xl/styles.xml", STYLES_XML)
        for index, (_, headers, rows) in enumerate(sheets, start=1):
            xlsx.writestr(f"xl/worksheets/sheet{index}.xml", sheet_xml(headers, rows))
    print(f"Saved {path}")


def write_debug_xlsx(rows, output_path):
    table_rows = [[row.get(field, "") for field in DEBUG_FIELDS] for row in rows]
    explorer_rows = [
        [
            row.get("collector", ""),
            row.get("url", ""),
            row.get("title", ""),
            row.get("detected_type", ""),
            row.get("matched_pattern", ""),
            row.get("classification", ""),
            row.get("final_status", ""),
            row.get("rejection_reason", ""),
        ]
        for row in rows
    ]
    write_workbook(
        [
            ("URL Debug", DEBUG_FIELDS, table_rows),
            ("Pattern Explorer", EXPLORER_FIELDS, explorer_rows),
        ],
        output_path,
    )


def unknown_rows_by_collector(rows):
    grouped = defaultdict(list)
    for row in rows:
        if row.get("detected_type") != "unknown" and row.get("rejection_reason") != "unknown_pattern":
            continue
        parsed = urlsplit(str(row.get("url") or ""))
        grouped[row.get("collector") or "unknown"].append([
            row.get("url", ""),
            row.get("title", ""),
            row.get("html_title") or row.get("title", ""),
            parsed.path or "/",
            row.get("detected_type", ""),
            row.get("rejection_reason", ""),
        ])
    return grouped


def write_unknown_urls_xlsx(rows, output_path=DEFAULT_UNKNOWN_URLS_PATH):
    grouped = unknown_rows_by_collector(rows)
    sheets = []
    for collector, collector_rows in sorted(grouped.items()):
        sheets.append((collector, UNKNOWN_FIELDS, collector_rows))
    if not sheets:
        sheets = [("Unknown URLs", UNKNOWN_FIELDS, [])]
    write_workbook(sheets, output_path)


def path_candidates(url):
    path = urlsplit(str(url or "")).path or "/"
    parts = [part for part in path.split("/") if part]
    candidates = []
    if path and path != "/":
        candidates.append(path if path.endswith("/") else f"{path}/")
    for size in range(1, min(len(parts), 3) + 1):
        candidates.append("/" + "/".join(parts[:size]) + "/")
    return candidates


def recommendation_counts(rows):
    grouped = defaultdict(Counter)
    for row in rows:
        if row.get("detected_type") != "unknown" and row.get("rejection_reason") != "unknown_pattern":
            continue
        for candidate in path_candidates(row.get("url", "")):
            grouped[row.get("collector") or "unknown"][candidate] += 1
    return grouped


def pattern_usage(rows):
    counts = Counter(row.get("matched_pattern") or "none" for row in rows)
    return counts


def write_recommendations(rows, output_path=DEFAULT_RECOMMENDATIONS_PATH):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    grouped_rows = defaultdict(list)
    for row in rows:
        grouped_rows[row.get("collector") or "unknown"].append(row)
    counts_by_collector = recommendation_counts(rows)
    lines = ["# URL Pattern Recommendations", ""]
    for collector, collector_rows in sorted(grouped_rows.items()):
        unknown_count = sum(
            1
            for row in collector_rows
            if row.get("detected_type") == "unknown" or row.get("rejection_reason") == "unknown_pattern"
        )
        lines.extend([
            f"## Collector: {collector}",
            "",
            f"{len(collector_rows)} URLs",
            "",
            f"{unknown_count} unknown",
            "",
        ])
        recommendations = counts_by_collector.get(collector, Counter()).most_common(10)
        if recommendations:
            lines.append("Detected repeated URL path patterns:")
            lines.append("")
            for pattern, count in recommendations:
                lines.append(f"- `{pattern}`: {count}")
            top_pattern, top_count = recommendations[0]
            lines.extend([
                "",
                "Recommended addition candidate:",
                "",
                "```yaml",
                "real_job:",
                f"  - \"{top_pattern}\"  # seen {top_count} times",
                "```",
                "",
            ])
        else:
            lines.append("No unknown URL path patterns detected.")
            lines.append("")
    lines.extend(["## Existing Pattern Usage", ""])
    for pattern, count in sorted(pattern_usage(rows).items()):
        lines.append(f"- `{pattern}`: {count}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Saved {path}")


def export_url_pattern_debug(rows, output_path=DEFAULT_DEBUG_PATH):
    output_path = Path(output_path)
    write_json(rows, output_path)
    write_debug_xlsx(rows, output_path.with_suffix(".xlsx"))
    write_unknown_urls_xlsx(rows, output_path.parent / Path(DEFAULT_UNKNOWN_URLS_PATH).name)
    write_recommendations(rows, output_path.parent / Path(DEFAULT_RECOMMENDATIONS_PATH).name)
