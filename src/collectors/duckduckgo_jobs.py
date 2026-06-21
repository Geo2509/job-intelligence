import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import yaml


SOURCE_NAME = "duckduckgo"
DEFAULT_CONFIG_PATH = "configs/job_sources.yaml"
DEFAULT_OUTPUT_PATH = "output/duckduckgo_jobs.json"
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
}
BAD_JOB_TERMS = [
    "solo provvigioni",
    "agente commerciale",
    "porta a porta",
    "network marketing",
    "investimento iniziale",
    "corso a pagamento",
    "forex",
    "crypto",
    "trading",
]
REMOTE_TERMS = [
    "remote",
    "remoto",
    "smart working",
    "lavoro da casa",
    "full remote",
]
PART_TIME_TERMS = [
    "part-time",
    "part time",
    "tempo parziale",
    "4 ore",
    "6 ore",
    "20 ore",
]
DATA_TERMS = [
    "data entry",
    "inserimento dati",
    "back office",
    "excel",
    "google sheets",
]
LOCAL_TERMS = [
    "napoli",
    "pozzuoli",
    "bacoli",
    "monte di procida",
    "quarto",
    "fuorigrotta",
    "campi flegrei",
]
AI_TERMS = [
    "ai trainer",
    "ai annotator",
    "transcription",
    "trascrizione",
]
ECOMMERCE_TERMS = [
    "e-commerce",
    "ecommerce",
    "catalogo prodotti",
]


def load_discovery_queries(config_path=DEFAULT_CONFIG_PATH):
    data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    return list(data.get("duckduckgo_discovery_queries") or [])


def result_url(result):
    url = (
        result.get("href")
        or result.get("url")
        or result.get("link")
        or result.get("source")
        or ""
    )
    return normalize_url(url)


def normalize_url(url):
    if not url:
        return ""

    parsed = urlsplit(str(url).strip())
    redirect_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    redirect_url = redirect_params.get("uddg") or redirect_params.get("url")
    if redirect_url:
        parsed = urlsplit(unquote(redirect_url))

    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in TRACKING_PARAMS
        ],
        doseq=True,
    )
    path = parsed.path.rstrip("/") or parsed.path
    return urlunsplit((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        query,
        "",
    ))


def combined_text(title="", snippet="", query=""):
    return " ".join([str(title or ""), str(snippet or ""), str(query or "")]).lower()


def has_any(text, terms):
    return any(term in text for term in terms)


def is_bad_job(title="", snippet=""):
    return has_any(combined_text(title, snippet), BAD_JOB_TERMS)


def score_result(title="", snippet="", query=""):
    text = combined_text(title, snippet, query)
    score = 0
    if has_any(text, REMOTE_TERMS):
        score += 30
    if has_any(text, PART_TIME_TERMS):
        score += 25
    if has_any(text, DATA_TERMS):
        score += 25
    if has_any(text, LOCAL_TERMS):
        score += 20
    if has_any(text, AI_TERMS):
        score += 15
    if has_any(text, ECOMMERCE_TERMS):
        score += 10
    if has_any(text, BAD_JOB_TERMS):
        score -= 30
    return score


def detect_category(title="", snippet="", query=""):
    text = combined_text(title, snippet, query)
    if has_any(text, AI_TERMS):
        return "ai_data"
    if has_any(text, DATA_TERMS):
        return "data_entry"
    if has_any(text, ECOMMERCE_TERMS):
        return "ecommerce"
    if has_any(text, REMOTE_TERMS):
        return "remote"
    if has_any(text, PART_TIME_TERMS):
        return "part_time"
    return "general"


def normalize_result(result, query, found_at=None):
    title = result.get("title") or ""
    snippet = result.get("body") or result.get("snippet") or result.get("source") or ""
    text = combined_text(title, snippet, query)
    return {
        "title": title,
        "company": "",
        "location": "",
        "url": result_url(result),
        "source": SOURCE_NAME,
        "query": query,
        "remote": has_any(text, REMOTE_TERMS),
        "part_time": has_any(text, PART_TIME_TERMS),
        "category": detect_category(title, snippet, query),
        "score": score_result(title, snippet, query),
        "found_at": found_at or datetime.now(timezone.utc).isoformat(),
    }


def dedup_key(job):
    if job.get("url"):
        return job["url"]
    return f"{str(job.get('title', '')).strip().lower()}|{str(job.get('query', '')).strip().lower()}"


def deduplicate_jobs(jobs):
    deduped = []
    seen = set()
    for job in jobs:
        key = dedup_key(job)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(job)
    return deduped


def get_ddgs_class():
    try:
        from ddgs import DDGS
    except ImportError:
        print("ddgs package not installed")
        return None
    return DDGS


def search_query(ddgs, query, limit):
    try:
        return ddgs.text(
            query,
            region="it-it",
            safesearch="moderate",
            max_results=limit,
        ) or []
    except Exception as exc:
        print(f"DuckDuckGo query failed: {query} | {exc}")
        return []


def collect_jobs(config_path=DEFAULT_CONFIG_PATH, limit=3, pause_seconds=1):
    DDGS = get_ddgs_class()
    if DDGS is None:
        return []

    queries = load_discovery_queries(config_path)
    jobs = []
    found_at = datetime.now(timezone.utc).isoformat()

    with DDGS() as ddgs:
        for query in queries:
            print(f"Searching DuckDuckGo: {query}")
            for result in search_query(ddgs, query, limit):
                title = result.get("title") or ""
                snippet = result.get("body") or result.get("snippet") or ""
                if is_bad_job(title, snippet):
                    continue
                job = normalize_result(result, query, found_at)
                if not job["url"] and not job["title"]:
                    continue
                jobs.append(job)
            if pause_seconds:
                time.sleep(pause_seconds)

    jobs = deduplicate_jobs(jobs)
    return sorted(jobs, key=lambda job: job["score"], reverse=True)


def write_jobs(jobs, output_path=DEFAULT_OUTPUT_PATH):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(jobs, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Saved {path}: {len(jobs)} rows")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--pause-seconds", type=float, default=1)
    return parser.parse_args()


def main():
    args = parse_args()
    jobs = collect_jobs(args.config, args.limit, args.pause_seconds)
    write_jobs(jobs, args.output)


if __name__ == "__main__":
    main()
