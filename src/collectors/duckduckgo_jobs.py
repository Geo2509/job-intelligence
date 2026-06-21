import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

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


SOURCE_NAME = "duckduckgo"
DEFAULT_CONFIG_PATH = "configs/job_sources.yaml"
DEFAULT_OUTPUT_PATH = "output/duckduckgo_jobs.json"
DEFAULT_TOP = 50


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


def get_priority_bucket(text, part_time, remote):
    return detect_priority_bucket(text, part_time, remote)


def score_result(title="", snippet="", query=""):
    return score_job(title, snippet, query)


def is_campania_part_time_job(job):
    return job.get("priority_bucket") == "campania_part_time"


def campania_part_time_sort_key(job):
    return (
        0 if is_campania_part_time_job(job) else 1,
        0 if job.get("remote") else 1,
        -job.get("score", 0),
    )


def normalize_result(result, query, found_at=None):
    title = result.get("title") or ""
    snippet = result.get("body") or result.get("snippet") or result.get("source") or ""
    text = combined_text(title, snippet, query)
    part_time = detect_part_time(title, snippet, query)
    remote = detect_remote(title, snippet, query)
    return {
        "title": title,
        "company": "",
        "location": "",
        "url": result_url(result),
        "source": SOURCE_NAME,
        "query": query,
        "remote": remote,
        "part_time": part_time,
        "category": detect_category(title, snippet, query),
        "score": score_job(title, snippet, query),
        "priority_bucket": get_priority_bucket(text, part_time, remote),
        "found_at": found_at or datetime.now(timezone.utc).isoformat(),
    }


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


def collect_jobs(config_path=DEFAULT_CONFIG_PATH, limit=3, pause_seconds=1, top=DEFAULT_TOP, campania_part_time_first=False):
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
    if campania_part_time_first:
        jobs = sorted(jobs, key=campania_part_time_sort_key)
    else:
        jobs = sorted(jobs, key=lambda job: job["score"], reverse=True)
    return jobs[:top]


def write_jobs(jobs, output_path=DEFAULT_OUTPUT_PATH):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(jobs, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Saved {path}: {len(jobs)} rows")


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--pause-seconds", type=float, default=1)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP,
                        help="Maximum number of jobs to save to output (default: 50)")
    parser.add_argument("--campania-part-time-first", action="store_true",
                        help="Sort campania part-time jobs first, then remote, then score desc")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    jobs = collect_jobs(
        args.config,
        args.limit,
        args.pause_seconds,
        top=args.top,
        campania_part_time_first=args.campania_part_time_first,
    )
    write_jobs(jobs, args.output)


if __name__ == "__main__":
    main()
