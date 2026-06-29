import argparse
import csv
import html
import json
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin
from xml.sax.saxutils import escape

import requests

from src.collectors.duckduckgo_jobs import get_ddgs_class
from src.job_matching import (
    combined_text,
    deduplicate_jobs,
    detect_category,
    detect_part_time,
    detect_priority_bucket,
    detect_remote,
    is_bad_job,
    normalize_url,
    score_job,
)


SOURCE_NAME = "indeed"
INDEED_BASE_URL = "https://it.indeed.com"
DEFAULT_OUTPUT_PATH = "output/indeed_jobs.json"
DEFAULT_LIMIT = 5
DEFAULT_TOP = 50
REQUEST_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
DIRECT_QUERIES = [
    ("data entry part time", "Napoli, Campania"),
    ("inserimento dati part time", "Napoli, Campania"),
    ("back office part time", "Pozzuoli, Campania"),
    ("lavoro da casa data entry", "Italia"),
    ("smart working data entry", "Italia"),
]
FALLBACK_DUCKDUCKGO_QUERIES = [
    "site:it.indeed.com/viewjob data entry Napoli part time",
    "site:it.indeed.com/viewjob inserimento dati Napoli part time",
    "site:it.indeed.com/viewjob back office Pozzuoli part time",
    "site:it.indeed.com/viewjob lavoro da casa data entry Italia",
    "site:it.indeed.com/viewjob smart working data entry Italia",
]
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


def build_indeed_search_url(query, location="", start=0):
    params = {"q": query}
    if location:
        params["l"] = location
    if start:
        params["start"] = str(start)
    return f"{INDEED_BASE_URL}/jobs?{urlencode(params)}"


def is_blocked_response(response):
    if response.status_code in {403, 429, 503}:
        return True
    text = response.text[:5000].lower()
    return "captcha" in text or "unusual traffic" in text or "verify" in text


def fetch_direct_search(url):
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        print(f"Indeed direct search failed: {url} | {exc}")
        return None

    if is_blocked_response(response):
        print(f"Indeed direct search blocked or unavailable: {url} | status {response.status_code}")
        return None
    if response.status_code >= 400:
        print(f"Indeed direct search failed: {url} | status {response.status_code}")
        return None
    return response.text


def extract_meta_value(block, keys):
    for key in keys:
        match = re.search(rf'{key}="([^"]+)"', block)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def parse_indeed_html(page_html, query):
    jobs = []
    seen_urls = set()
    for match in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page_html, re.DOTALL | re.IGNORECASE):
        href = html.unescape(match.group(1))
        if not ("/viewjob" in href or "/rc/clk" in href or "jk=" in href):
            continue

        block = match.group(0)
        title = extract_meta_value(block, ["aria-label", "title"])
        if not title:
            title = re.sub(r"<[^>]+>", " ", match.group(2))
            title = " ".join(html.unescape(title).split())
        if not title:
            continue

        url = normalize_url(urljoin(INDEED_BASE_URL, href))
        if url in seen_urls:
            continue
        seen_urls.add(url)
        jobs.append(normalize_indeed_result({
            "title": title,
            "company": "",
            "location": "",
            "url": url,
            "snippet": "",
        }, query))
    return deduplicate_jobs(jobs)


def is_indeed_job_detail_url(url):
    normalized = normalize_url(url)
    if "it.indeed.com" not in normalized:
        return False
    return "/viewjob" in normalized or "/rc/clk" in normalized or "jk=" in normalized


def normalize_indeed_result(result, query, found_at=None):
    title = result.get("title") or ""
    snippet = result.get("snippet") or result.get("body") or result.get("source") or ""
    company = result.get("company") or ""
    location = result.get("location") or ""
    searchable = combined_text(title, " ".join([snippet, company, location]), query)
    remote = detect_remote(title, snippet, query)
    part_time = detect_part_time(title, snippet, query)
    return {
        "title": title,
        "company": company,
        "location": location,
        "url": normalize_url(result.get("url") or result.get("href") or result.get("link") or ""),
        "source": SOURCE_NAME,
        "query": query,
        "remote": remote,
        "part_time": part_time,
        "category": detect_category(title, snippet, query),
        "priority_bucket": detect_priority_bucket(searchable, part_time, remote),
        "score": score_job(title, snippet, query),
        "found_at": found_at or datetime.now(timezone.utc).isoformat(),
    }


def collect_direct_jobs(limit=DEFAULT_LIMIT, pause_seconds=3):
    jobs = []
    for query, location in DIRECT_QUERIES:
        search_url = build_indeed_search_url(query, location)
        print(f"Indeed direct search: {search_url}")
        page_html = fetch_direct_search(search_url)
        if page_html:
            for job in parse_indeed_html(page_html, query):
                if is_bad_job(job["title"], ""):
                    continue
                jobs.append(job)
                if len(jobs) >= limit * len(DIRECT_QUERIES):
                    break
        if pause_seconds:
            time.sleep(pause_seconds)
    return deduplicate_jobs(jobs)


def collect_fallback_duckduckgo_jobs(limit=DEFAULT_LIMIT):
    DDGS = get_ddgs_class()
    if DDGS is None:
        return []

    jobs = []
    found_at = datetime.now(timezone.utc).isoformat()
    with DDGS() as ddgs:
        for query in FALLBACK_DUCKDUCKGO_QUERIES:
            print(f"Indeed fallback DuckDuckGo search: {query}")
            try:
                results = ddgs.text(
                    query,
                    region="it-it",
                    safesearch="moderate",
                    max_results=limit,
                ) or []
            except Exception as exc:
                print(f"Indeed fallback DuckDuckGo failed: {query} | {exc}")
                continue

            for result in results:
                title = result.get("title") or ""
                snippet = result.get("body") or result.get("snippet") or ""
                if is_bad_job(title, snippet):
                    continue
                job = normalize_indeed_result({
                    "title": title,
                    "company": "",
                    "location": "",
                    "url": result.get("href") or result.get("url") or result.get("link") or "",
                    "snippet": snippet,
                }, query, found_at)
                if not is_indeed_job_detail_url(job["url"]):
                    continue
                jobs.append(job)
    return deduplicate_jobs(jobs)


def sort_jobs(jobs, campania_part_time_first=False):
    if campania_part_time_first:
        return sorted(
            jobs,
            key=lambda job: (
                0 if job.get("priority_bucket") == "campania_part_time" else 1,
                0 if job.get("remote") else 1,
                -job.get("score", 0),
            ),
        )
    return sorted(jobs, key=lambda job: job.get("score", 0), reverse=True)


def collect_jobs(limit=DEFAULT_LIMIT, top=DEFAULT_TOP, campania_part_time_first=False, direct_pause_seconds=3):
    jobs = collect_direct_jobs(limit, direct_pause_seconds)
    if not jobs:
        print("Indeed direct search produced no jobs; using DuckDuckGo fallback.")
        jobs = collect_fallback_duckduckgo_jobs(limit)
    jobs = deduplicate_jobs(jobs)
    return sort_jobs(jobs, campania_part_time_first)[:top]


def write_json(jobs, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {path}: {len(jobs)} rows")


def sibling_output_path(output_path, suffix):
    path = Path(output_path)
    return path.with_suffix(suffix)


def write_csv(jobs, output_path):
    path = sibling_output_path(output_path, ".csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for job in jobs:
            writer.writerow({field: job.get(field, "") for field in OUTPUT_FIELDS})
    print(f"Saved {path}: {len(jobs)} rows")


def write_xlsx(jobs, output_path):
    path = sibling_output_path(output_path, ".xlsx")
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [OUTPUT_FIELDS] + [
        [str(job.get(field, "")) for field in OUTPUT_FIELDS]
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
  <sheets><sheet name="indeed_jobs" sheetId="1" r:id="rId1"/></sheets>
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
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP)
    parser.add_argument("--campania-part-time-first", action="store_true")
    parser.add_argument("--direct-pause-seconds", type=float, default=3)
    return parser.parse_args(argv)


def main():
    args = parse_args()
    jobs = collect_jobs(
        limit=args.limit,
        top=args.top,
        campania_part_time_first=args.campania_part_time_first,
        direct_pause_seconds=args.direct_pause_seconds,
    )
    export_jobs(jobs, args.output)


if __name__ == "__main__":
    main()
