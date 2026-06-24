import argparse
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urljoin

import requests

from src.candidate_profile import calculate_match_score, evaluate_candidate_score
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
from src.student_profile import detect_location_fit, evaluate_student_score, load_student_profile


SOURCE_NAME = "gigroup"
GIGROUP_BASE_URL = "https://www.gigroup.it"
DEFAULT_OUTPUT_PATH = "output/gigroup_jobs.json"
DEFAULT_LIMIT = 5
DEFAULT_TOP = 50
REQUEST_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
DIRECT_QUERIES = [
    "lavoro Napoli",
    "offerte lavoro Napoli",
    "back office Napoli",
    "impiegato amministrativo Napoli",
    "receptionist Napoli",
    "magazziniere Napoli",
    "part time Napoli",
    "Pozzuoli",
    "Bacoli",
    "Casoria",
]
FALLBACK_DUCKDUCKGO_QUERIES = [
    "site:gigroup.it lavoro Napoli",
    "site:gigroup.it offerte lavoro Napoli",
    "site:gigroup.it back office Napoli",
    "site:gigroup.it impiegato amministrativo Napoli",
    "site:gigroup.it receptionist Napoli",
    "site:gigroup.it magazziniere Napoli",
    "site:gigroup.it part time Napoli",
    "site:gigroup.it Pozzuoli",
    "site:gigroup.it Bacoli",
    "site:gigroup.it Casoria",
]
JOB_DETAIL_PARTS = [
    "/offerte-lavoro/dettaglio-offerta/",
    "/offerte-lavoro/job-detail/",
    "/annunci/",
    "/jobs/",
    "/job/",
]
CAREER_PAGE_PARTS = [
    "/lavora-con-noi",
    "/candidati",
    "/career",
]
OUTPUT_FIELDS = [
    "title",
    "company",
    "location",
    "url",
    "source",
    "query",
    "category",
    "remote",
    "part_time",
    "priority_bucket",
    "score",
    "student_score",
    "candidate_score",
    "match_score",
    "location_fit",
    "found_at",
]


def build_gigroup_search_url(query):
    return f"{GIGROUP_BASE_URL}/offerte-lavoro/?q={quote_plus(str(query or '').strip())}"


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
        print(f"Gi Group direct search failed: {url} | {exc}")
        return None

    if is_blocked_response(response):
        print(f"Gi Group direct search blocked or unavailable: {url} | status {response.status_code}")
        return None
    if response.status_code >= 400:
        print(f"Gi Group direct search failed: {url} | status {response.status_code}")
        return None
    return response.text


def clean_text(value):
    return " ".join(html.unescape(str(value or "")).split())


def anchor_text(anchor_html):
    text = re.sub(r"<[^>]+>", " ", anchor_html)
    return clean_text(text)


def is_gigroup_domain(url):
    normalized = normalize_url(url)
    return "gigroup.it" in normalized


def is_gigroup_job_detail_url(url):
    normalized = normalize_url(url)
    if not is_gigroup_domain(normalized):
        return False
    path = normalized.split("gigroup.it", 1)[-1].split("?", 1)[0].lower()
    if path.rstrip("/") in {"", "/", "/offerte-lavoro", "/lavora-con-noi", "/candidati"}:
        return False
    if any(part in path for part in CAREER_PAGE_PARTS):
        return False
    if any(part in normalized for part in ["/offerte-lavoro?", "/cerca-lavoro", "/risultati-ricerca", "/search"]):
        return False
    if any(part in path for part in JOB_DETAIL_PARTS):
        return True
    return "/offerte-lavoro/" in path and len([part for part in path.split("/") if part]) >= 2


def extract_title_from_url(url):
    path = str(url or "").rstrip("/").split("/")[-1]
    title = path.split("_", 1)[0]
    title = re.sub(r"\d+$", "", title)
    return clean_text(title.replace("-", " "))


def parse_gigroup_html(page_html, query):
    jobs = []
    seen_urls = set()
    for match in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page_html, re.DOTALL | re.IGNORECASE):
        href = html.unescape(match.group(1))
        url = normalize_url(urljoin(GIGROUP_BASE_URL, href))
        if not is_gigroup_job_detail_url(url) or url in seen_urls:
            continue

        title = anchor_text(match.group(2)) or extract_title_from_url(url)
        if not title:
            continue

        seen_urls.add(url)
        jobs.append(normalize_gigroup_result({
            "title": title,
            "company": "Gi Group",
            "location": "",
            "url": url,
            "snippet": "",
        }, query))
    return jobs


def normalize_gigroup_result(result, query, found_at=None):
    title = result.get("title") or ""
    snippet = result.get("snippet") or result.get("body") or result.get("source") or ""
    company = result.get("company") or "Gi Group"
    location = result.get("location") or ""
    searchable = combined_text(title, " ".join([snippet, company, location]), query)
    remote = detect_remote(title, snippet, query)
    part_time = detect_part_time(title, snippet, query)
    job = {
        "title": title,
        "company": company,
        "location": location,
        "url": normalize_url(result.get("url") or result.get("href") or result.get("link") or ""),
        "source": SOURCE_NAME,
        "query": query,
        "category": detect_category(title, snippet, query),
        "remote": remote,
        "part_time": part_time,
        "priority_bucket": detect_priority_bucket(searchable, part_time, remote),
        "score": score_job(title, snippet, query),
        "found_at": found_at or datetime.now(timezone.utc).isoformat(),
    }
    job["location_fit"] = detect_location_fit(job, load_student_profile())
    job["student_score"] = int(evaluate_student_score(job))
    job["candidate_score"] = int(evaluate_candidate_score(job))
    job["match_score"] = calculate_match_score(job["student_score"], job["candidate_score"])
    return job


def collect_direct_jobs(limit=DEFAULT_LIMIT, pause_seconds=3):
    jobs = []
    for query in DIRECT_QUERIES:
        search_url = build_gigroup_search_url(query)
        print(f"Gi Group direct search: {search_url}")
        page_html = fetch_direct_search(search_url)
        if page_html:
            for job in parse_gigroup_html(page_html, query):
                if is_bad_job(job["title"], ""):
                    continue
                jobs.append(job)
                if len(jobs) >= limit * len(DIRECT_QUERIES):
                    break
        if pause_seconds:
            time.sleep(pause_seconds)
    return jobs


def collect_fallback_duckduckgo_jobs(limit=DEFAULT_LIMIT):
    DDGS = get_ddgs_class()
    if DDGS is None:
        return []

    jobs = []
    found_at = datetime.now(timezone.utc).isoformat()
    with DDGS() as ddgs:
        for query in FALLBACK_DUCKDUCKGO_QUERIES:
            print(f"Gi Group fallback DuckDuckGo search: {query}")
            try:
                results = ddgs.text(
                    query,
                    region="it-it",
                    safesearch="moderate",
                    max_results=limit,
                ) or []
            except Exception as exc:
                print(f"Gi Group fallback DuckDuckGo failed: {query} | {exc}")
                continue

            for result in results:
                title = result.get("title") or ""
                snippet = result.get("body") or result.get("snippet") or ""
                if is_bad_job(title, snippet):
                    continue
                job = normalize_gigroup_result({
                    "title": title,
                    "company": "Gi Group",
                    "location": "",
                    "url": result.get("href") or result.get("url") or result.get("link") or "",
                    "snippet": snippet,
                }, query, found_at)
                if not is_gigroup_domain(job["url"]):
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
                -job.get("match_score", 0),
                -job.get("student_score", 0),
                -job.get("score", 0),
            ),
        )
    return sorted(
        jobs,
        key=lambda job: (
            job.get("match_score", 0),
            job.get("student_score", 0),
            job.get("score", 0),
        ),
        reverse=True,
    )


def collect_jobs(limit=DEFAULT_LIMIT, top=DEFAULT_TOP, campania_part_time_first=False, direct_pause_seconds=3):
    jobs = collect_direct_jobs(limit, direct_pause_seconds)
    if not jobs:
        print("Gi Group direct search produced no jobs; using DuckDuckGo fallback.")
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
