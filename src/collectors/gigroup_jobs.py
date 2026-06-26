import argparse
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit

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
    detect_remote_reason,
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
PLACE_TERMS = [
    "Napoli",
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
    "/offerte-lavoro-dettaglio/",
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
    "category",
    "normalized_category",
    "remote",
    "remote_reason",
    "part_time",
    "priority_bucket",
    "score",
    "student_score",
    "candidate_score",
    "match_score",
    "location_fit",
    "found_at",
]
DETAIL_FIELDS = [
    "description",
    "contract_type",
    "employment_type",
    "working_hours",
    "salary",
    "experience",
    "skills",
]
GIGROUP_DETAIL_PATH_RE = re.compile(
    r"^/offerte-lavoro-dettaglio/[^/]+/(?:\d+|a\d+)/?$",
    re.IGNORECASE,
)


def build_gigroup_search_url(query):
    query = clean_text(query)
    place = ""
    job = query
    for term in PLACE_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", query, re.IGNORECASE):
            place = term
            job = clean_text(re.sub(rf"\b{re.escape(term)}\b", " ", query, flags=re.IGNORECASE))
            break
    if job.lower() in {"lavoro", "offerte lavoro"}:
        job = ""
    params = {
        "job": job,
        "placeOfWork": place,
        "radius": "25",
    }
    return f"{GIGROUP_BASE_URL}/offerte-lavoro/?{urlencode(params)}"


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


def fetch_detail_page(url):
    return fetch_direct_search(url)


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
    path = urlsplit(normalized).path.lower()
    if GIGROUP_DETAIL_PATH_RE.match(path):
        return True
    if path.rstrip("/") in {"", "/", "/offerte-lavoro", "/lavora-con-noi", "/candidati"}:
        return False
    if any(part in path for part in CAREER_PAGE_PARTS):
        return False
    if any(part in normalized for part in ["/offerte-lavoro?", "/cerca-lavoro", "/risultati-ricerca", "/search"]):
        return False
    if any(part in path for part in JOB_DETAIL_PARTS):
        return True
    return False


def extract_title_from_url(url):
    path = str(url or "").rstrip("/").split("/")[-1]
    title = path.split("_", 1)[0]
    title = re.sub(r"\d+$", "", title)
    return clean_text(title.replace("-", " "))


def extract_first(pattern, text, flags=re.DOTALL | re.IGNORECASE):
    match = re.search(pattern, text, flags)
    if not match:
        return ""
    return clean_text(re.sub(r"<[^>]+>", " ", match.group(1)))


def visible_text(page_html):
    text = re.sub(r"<script\b.*?</script>", " ", page_html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:p|div|li|section|article|h[1-6])>", ". ", text, flags=re.IGNORECASE)
    return clean_text(re.sub(r"<[^>]+>", " ", text))


def extract_meta_description(page_html):
    return extract_first(
        r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\']([^"\']+)["\']',
        page_html,
    ) or extract_first(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'](?:description|og:description)["\']',
        page_html,
    )


def extract_label_value(text, labels):
    labels_pattern = "|".join(re.escape(label) for label in sorted(labels, key=len, reverse=True))
    pattern = rf"(?:{labels_pattern})\s*:?\s+(.+?)(?=\s+(?:{labels_pattern})\s*:|\s{{2,}}|$)"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return ""
    return clean_text(match.group(1).split(". ", 1)[0])


def extract_skills(text):
    terms = [
        "excel",
        "office",
        "google sheets",
        "data entry",
        "back office",
        "inglese",
        "italiano",
        "customer service",
        "gestionale",
        "sap",
    ]
    found = []
    lowered = text.lower()
    for term in terms:
        if term in lowered:
            found.append(term)
    return ", ".join(found)


def parse_gigroup_detail_html(page_html):
    text = visible_text(page_html)
    description = (
        extract_first(r'<section[^>]*class="[^"]*(?:job-description|description)[^"]*"[^>]*>(.*?)</section>', page_html)
        or extract_first(r'<div[^>]*class="[^"]*(?:job-description|description|content)[^"]*"[^>]*>(.*?)</div>', page_html)
        or extract_meta_description(page_html)
        or text
    )
    contract_type = extract_label_value(text, ["Contratto", "Tipologia contrattuale", "Tipo di contratto"])
    employment_type = extract_label_value(text, ["Categoria professionale", "Area professionale", "Settore"])
    working_hours = extract_label_value(text, ["Orario di lavoro", "Orario", "Disponibilita oraria", "Disponibilità oraria"])
    salary = extract_label_value(text, ["Retribuzione", "RAL", "Stipendio", "Salary"])
    experience = extract_label_value(text, ["Esperienza", "Anni di esperienza", "Requisiti"])
    location = extract_label_value(text, ["Luogo di lavoro", "Sede di lavoro", "Location"])
    company = extract_label_value(text, ["Azienda", "Company"]) or "Gi Group"
    skills = extract_label_value(text, ["Competenze", "Skills"]) or extract_skills(text)
    smart_working = bool(re.search(r"\b(smart working|full remote|remoto|lavoro da casa|ibrid[oa])\b", text, re.IGNORECASE))
    full_time = bool(re.search(r"\b(full time|tempo pieno)\b", text, re.IGNORECASE))
    return {
        "description": description,
        "contract_type": contract_type,
        "employment_type": employment_type,
        "working_hours": working_hours,
        "salary": salary,
        "experience": experience,
        "skills": skills,
        "smart_working": smart_working,
        "full_time": full_time,
        "location": location,
        "company": company,
    }


def detail_text(result):
    return " ".join(
        str(result.get(field, "") or "")
        for field in DETAIL_FIELDS + ["snippet", "body", "source"]
    )


def enrich_gigroup_job(job):
    detail_html = fetch_detail_page(job.get("url", ""))
    if not detail_html:
        return job
    details = parse_gigroup_detail_html(detail_html)
    enriched = dict(job)
    for field, value in details.items():
        if value not in ("", None, False) or field in {"smart_working", "full_time"}:
            if field in {"location", "company"} and enriched.get(field):
                continue
            enriched[field] = value
    return normalize_gigroup_result(enriched, enriched.get("query", ""), enriched.get("found_at"))


def parse_data_job(anchor_html):
    match = re.search(r"\sdata-job='([^']+)'", anchor_html, re.IGNORECASE)
    if not match:
        return {}
    try:
        return json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError:
        return {}


def job_article_blocks(page_html):
    blocks = re.findall(
        r'<article\b[^>]*class="[^"]*\bggp-job-item\b[^"]*"[^>]*>.*?</article>',
        page_html,
        re.DOTALL | re.IGNORECASE,
    )
    if blocks:
        return blocks
    return [page_html]


def extract_location_from_article(article_html):
    return extract_first(
        r"Luogo di lavoro:\s*</span>\s*<span[^>]*>(.*?)</span>",
        article_html,
    )


def extract_detail_anchors(block_html):
    anchors = []
    for match in re.finditer(r'<a\b([^>]*)>(.*?)</a>', block_html, re.DOTALL | re.IGNORECASE):
        attrs = match.group(1)
        href_match = re.search(r'href=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
        if not href_match:
            continue
        href = html.unescape(href_match.group(1))
        url = normalize_url(urljoin(GIGROUP_BASE_URL, href))
        if not is_gigroup_job_detail_url(url):
            continue
        anchors.append({
            "attrs": attrs,
            "body": match.group(2),
            "url": url,
            "data_job": parse_data_job(attrs),
        })
    return anchors


def title_from_anchor(anchor):
    return (
        anchor.get("data_job", {}).get("offerTitle")
        or extract_first(r"<h[1-6][^>]*>(.*?)</h[1-6]>", anchor.get("body", ""))
        or anchor_text(anchor.get("body", ""))
        or extract_title_from_url(anchor.get("url", ""))
    )


def parse_gigroup_html(page_html, query):
    jobs = []
    seen_urls = set()
    for block in job_article_blocks(page_html):
        location = extract_location_from_article(block)
        for anchor in extract_detail_anchors(block):
            url = anchor["url"]
            if url in seen_urls:
                continue

            title = title_from_anchor(anchor)
            if not title:
                continue

            data_job = anchor.get("data_job", {})
            snippet = " ".join(
                value
                for value in [
                    data_job.get("industry"),
                    data_job.get("professionalArea"),
                    extract_first(r'<div[^>]*class="[^"]*\bggp-job-keywords\b[^"]*"[^>]*>(.*?)</div>', block),
                    anchor_text(block),
                ]
                if value
            )
            seen_urls.add(url)
            jobs.append(normalize_gigroup_result({
                "title": title,
                "company": "Gi Group",
                "location": location or data_job.get("province", ""),
                "url": url,
                "snippet": snippet,
            }, query))
    return jobs


def normalize_gigroup_result(result, query, found_at=None):
    title = result.get("title") or ""
    snippet = detail_text(result)
    company = result.get("company") or "Gi Group"
    location = result.get("location") or ""
    searchable = combined_text(title, " ".join([snippet, company, location]), query)
    url = normalize_url(result.get("url") or result.get("href") or result.get("link") or "")
    remote = detect_remote(title, snippet, "", location=location, url=url, description=result.get("description", ""))
    category = detect_category(title, snippet, query)
    part_time = detect_part_time(title, snippet, "")
    job = {
        "title": title,
        "company": company,
        "location": location,
        "description": result.get("description", ""),
        "contract_type": result.get("contract_type", ""),
        "employment_type": result.get("employment_type", ""),
        "working_hours": result.get("working_hours", ""),
        "salary": result.get("salary", ""),
        "experience": result.get("experience", ""),
        "skills": result.get("skills", ""),
        "smart_working": bool(result.get("smart_working")) or remote,
        "full_time": bool(result.get("full_time")),
        "url": url,
        "source": SOURCE_NAME,
        "query": query,
        "category": category,
        "normalized_category": category,
        "remote": remote,
        "remote_reason": detect_remote_reason(title, snippet, "", location=location, url=url, description=result.get("description", "")),
        "part_time": part_time,
        "priority_bucket": detect_priority_bucket(searchable, part_time, remote),
        "score": score_job(title, snippet, ""),
        "found_at": found_at or datetime.now(timezone.utc).isoformat(),
    }
    job["location_fit"] = detect_location_fit(job, load_student_profile())
    job["student_score"] = int(evaluate_student_score(job))
    job["candidate_score"] = int(evaluate_candidate_score(job))
    job["match_score"] = calculate_match_score(job["student_score"], job["candidate_score"])
    return job


def collect_direct_jobs(limit=DEFAULT_LIMIT, pause_seconds=3):
    jobs = []
    seen_urls = set()
    target_count = limit * len(DIRECT_QUERIES)
    for query in DIRECT_QUERIES:
        if len(jobs) >= target_count:
            break
        search_url = build_gigroup_search_url(query)
        print(f"Gi Group direct search: {search_url}")
        page_html = fetch_direct_search(search_url)
        if page_html:
            for job in parse_gigroup_html(page_html, query):
                if is_bad_job(job["title"], ""):
                    continue
                if job["url"] in seen_urls:
                    continue
                seen_urls.add(job["url"])
                jobs.append(enrich_gigroup_job(job))
                if len(jobs) >= target_count:
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
                url = result.get("href") or result.get("url") or result.get("link") or ""
                if not is_gigroup_job_detail_url(url):
                    continue
                job = normalize_gigroup_result({
                    "title": title,
                    "company": "Gi Group",
                    "location": "",
                    "url": url,
                    "snippet": snippet,
                }, query, found_at)
                jobs.append(enrich_gigroup_job(job))
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
