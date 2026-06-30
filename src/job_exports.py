import csv
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


DEFAULT_OUTPUT_PATH = "output/v2_jobs.json"
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
