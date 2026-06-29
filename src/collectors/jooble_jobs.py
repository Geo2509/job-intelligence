import argparse
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlsplit

import requests

from src.collectors.duckduckgo_jobs import get_ddgs_class
from src.job_matching import (
    combined_text,
    deduplicate_jobs,
    detect_category,
    detect_part_time,
    detect_priority_bucket,
    detect_remote,
    detect_remote_reason,
    is_bad_job,
    normalize_url,
    score_job,
)


SOURCE_NAME = "jooble"
JOOBLE_BASE_URL = "https://it.jooble.org"
DEFAULT_OUTPUT_PATH = "output/jooble_jobs.json"
DEFAULT_LIMIT = 5
DEFAULT_TOP = 50
REQUEST_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
DIRECT_QUERIES = [
    "data entry Napoli part time",
    "inserimento dati Napoli part time",
    "back office Napoli part time",
    "receptionist Napoli part time",
    "accoglienza Napoli part time",
    "magazziniere Napoli part time",
    "pulizie Napoli part time",
    "cameriere Napoli part time",
    "remote data entry Italia",
    "AI trainer remote Italia",
    "data annotator remote Italia",
]
FALLBACK_DUCKDUCKGO_QUERIES = [
    "site:it.jooble.org/jdp data entry Napoli part time",
    "site:it.jooble.org/jdp AI trainer remote Italia",
    "site:it.jooble.org/jdp data annotator remote Italia",
]
OUTPUT_FIELDS = [
    "title",
    "company",
    "location",
    "description",
    "url",
    "source",
    "query",
    "remote",
    "remote_reason",
    "part_time",
    "category",
    "priority_bucket",
    "score",
    "found_at",
]


def build_jooble_search_url(query):
    return f"{JOOBLE_BASE_URL}/SearchResult?ukw={quote_plus(str(query or '').strip())}"


def is_blocked_response(response):
    if response.status_code in {403, 429, 503}:
        return True
    text = response.text[:5000].lower()
    blocked_terms = ["captcha", "access denied", "too many requests", "verifica", "robot"]
    return any(term in text for term in blocked_terms)


def fetch_direct_search(url):
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        print(f"Jooble direct search failed: {url} | {exc}")
        return None

    if is_blocked_response(response):
        print(f"Jooble direct search blocked or unavailable: {url} | status {response.status_code}")
        return None
    if response.status_code >= 400:
        print(f"Jooble direct search failed: {url} | status {response.status_code}")
        return None
    return response.text


def clean_text(value):
    return " ".join(html.unescape(str(value or "")).split())


def anchor_text(anchor_html):
    text = re.sub(r"<[^>]+>", " ", anchor_html)
    return clean_text(text)


def is_jooble_job_detail_url(url):
    normalized = normalize_url(url)
    parsed = urlsplit(normalized)
    hostname = (parsed.hostname or "").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    if hostname not in {"jooble.org", "it.jooble.org"}:
        return False
    return "/jdp/" in parsed.path.lower()


def extract_title_from_url(url):
    path = str(url or "").rstrip("/").split("/")[-1]
    return clean_text(path.replace("-", " ")) or "Jooble job"


def parse_jooble_html(page_html, query):
    jobs = []
    seen_urls = set()
    for match in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page_html, re.DOTALL | re.IGNORECASE):
        href = html.unescape(match.group(1))
        url = normalize_url(urljoin(JOOBLE_BASE_URL, href))
        if not is_jooble_job_detail_url(url) or url in seen_urls:
            continue

        title = anchor_text(match.group(2)) or extract_title_from_url(url)
        if not title:
            continue

        seen_urls.add(url)
        jobs.append(normalize_jooble_result({
            "title": title,
            "company": "",
            "location": "",
            "url": url,
            "snippet": "",
        }, query))
    return deduplicate_jobs(jobs)


def normalize_jooble_result(result, query, found_at=None):
    title = result.get("title") or ""
    description = result.get("description") or result.get("snippet") or result.get("body") or ""
    company = result.get("company") or ""
    location = result.get("location") or ""
    url = normalize_url(result.get("url") or result.get("href") or result.get("link") or "")
    searchable = combined_text(title, " ".join([description, company, location]), query)
    remote = detect_remote(title, description, query, location=location, url=url, description=description)
    part_time = detect_part_time(title, description, query)
    return {
        "title": title,
        "company": company,
        "location": location,
        "description": description,
        "url": url,
        "source": SOURCE_NAME,
        "query": query,
        "remote": remote,
        "remote_reason": detect_remote_reason(title, description, query, location=location, url=url, description=description),
        "part_time": part_time,
        "category": detect_category(title, description, query),
        "priority_bucket": detect_priority_bucket(searchable, part_time, remote),
        "score": score_job(title, description, query),
        "found_at": found_at or datetime.now(timezone.utc).isoformat(),
    }


def collect_direct_jobs(limit=DEFAULT_LIMIT, pause_seconds=3):
    jobs = []
    target_count = limit * len(DIRECT_QUERIES)
    for query in DIRECT_QUERIES:
        if len(jobs) >= target_count:
            break
        search_url = build_jooble_search_url(query)
        print(f"Jooble direct search: {search_url}")
        page_html = fetch_direct_search(search_url)
        if page_html:
            for job in parse_jooble_html(page_html, query):
                if is_bad_job(job["title"], job.get("description", "")):
                    continue
                jobs.append(job)
                if len(jobs) >= target_count:
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
            print(f"Jooble fallback DuckDuckGo search: {query}")
            try:
                results = ddgs.text(
                    query,
                    region="it-it",
                    safesearch="moderate",
                    max_results=limit,
                ) or []
            except Exception as exc:
                print(f"Jooble fallback DuckDuckGo failed: {query} | {exc}")
                continue

            for result in results:
                title = result.get("title") or ""
                snippet = result.get("body") or result.get("snippet") or ""
                if is_bad_job(title, snippet):
                    continue
                job = normalize_jooble_result({
                    "title": title,
                    "company": "",
                    "location": "",
                    "url": result.get("href") or result.get("url") or result.get("link") or "",
                    "snippet": snippet,
                }, query, found_at)
                if not is_jooble_job_detail_url(job["url"]):
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
        print("Jooble direct search produced no jobs; using DuckDuckGo fallback.")
        jobs = collect_fallback_duckduckgo_jobs(limit)
    jobs = deduplicate_jobs(jobs)
    return sort_jobs(jobs, campania_part_time_first)[:top]


def write_jobs(jobs, output_path=DEFAULT_OUTPUT_PATH):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {path}: {len(jobs)} rows")


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
    write_jobs(jobs, args.output)


if __name__ == "__main__":
    main()
