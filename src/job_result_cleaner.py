import argparse
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from src.job_url_patterns import classify_url, load_url_patterns


DEFAULT_INPUT_PATH = "output/v2_jobs.json"
DEFAULT_OUTPUT_PATH = "output/v2_jobs_clean.json"
SEARCH_URL_PATTERNS = [
    "/search",
]
CATEGORY_URL_PATTERNS = [
    "/cerca",
]
SEARCH_QUERY_KEYS = {
    "q",
}
SEARCH_QUERY_PATHS = [
    "/jobs",
    "/offerte",
]
TITLE_PREFIXES = [
    "più di",
    "offerte di lavoro",
    "lavoro urgente",
    "trova lavoro",
    "annunci",
]
SNIPPET_TERMS = [
    "offerte di lavoro",
    "annunci",
    "trova lavoro",
    "risultati",
    "jobs found",
    "more than",
]
ARTICLE_BLACKLIST_TERMS = [
    "captcha entry",
    "captcha job",
    "open data",
    "dataset",
    "fatturazione elettronica",
    "marcatempo",
    "rilevazione presenze",
    "treasure in the phlegrean",
    "turismo",
    "travel guide",
    "comune di napoli",
    "elenco dei dataset",
]
RESULT_TYPES = [
    "job",
    "search_page",
    "category_page",
    "aggregator_page",
    "article",
    "profile",
    "excluded_domain",
    "unknown",
]
URL_REMOVED_RESULT_TYPES = {
    "search_page",
    "category_page",
    "aggregator_page",
    "article",
    "profile",
    "excluded_domain",
}


def lower_text(value):
    return str(value or "").strip().lower()


def snippet_text(job):
    return " ".join(
        str(job.get(field, "") or "")
        for field in ["snippet", "description", "body", "summary"]
    )


def url_has_search_pattern(url):
    parsed = urlsplit(str(url or ""))
    path = parsed.path.lower()
    query_keys = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}

    if SEARCH_QUERY_KEYS.intersection(query_keys):
        return True
    if any(pattern in path for pattern in SEARCH_URL_PATTERNS):
        return True
    if parsed.query and any(path.endswith(pattern) or path == pattern for pattern in SEARCH_QUERY_PATHS):
        return True
    return False


def url_has_category_pattern(url):
    parsed = urlsplit(str(url or ""))
    path = parsed.path.lower()
    return any(pattern in path for pattern in CATEGORY_URL_PATTERNS)


def title_has_search_prefix(title):
    title = lower_text(title)
    return any(title.startswith(prefix) for prefix in TITLE_PREFIXES)


def snippet_has_aggregator_terms(snippet):
    snippet = lower_text(snippet)
    return any(term in snippet for term in SNIPPET_TERMS)


def title_or_snippet_has_article_blacklist(job):
    text = lower_text(" ".join([str(job.get("title", "") or ""), snippet_text(job)]))
    return any(term in text for term in ARTICLE_BLACKLIST_TERMS)


def fallback_result_type(job):
    url = job.get("url", "")
    title = job.get("title", "")
    snippet = snippet_text(job)

    if title_or_snippet_has_article_blacklist(job):
        return "article"
    if url_has_search_pattern(url):
        return "search_page"
    if url_has_category_pattern(url):
        return "category_page"
    if title_has_search_prefix(title):
        return "aggregator_page"
    if snippet_has_aggregator_terms(snippet):
        return "aggregator_page"
    if not url and not title:
        return "unknown"
    return "job"


def detect_result_type(job, patterns=None):
    patterns = patterns if patterns is not None else load_url_patterns()
    url_result_type = classify_url(job.get("url", ""), patterns)
    if url_result_type == "real_job":
        return "job"
    if url_result_type in URL_REMOVED_RESULT_TYPES:
        return url_result_type
    return fallback_result_type(job)


def clean_job(job, patterns=None):
    job = dict(job)
    patterns = patterns if patterns is not None else load_url_patterns()
    job["url_result_type"] = classify_url(job.get("url", ""), patterns)
    job["result_type"] = detect_result_type(job, patterns)
    return job


def clean_results(jobs):
    patterns = load_url_patterns()
    cleaned = [clean_job(job, patterns) for job in jobs]
    return [job for job in cleaned if job["result_type"] == "job"]


def clean_results_with_summary(jobs):
    patterns = load_url_patterns()
    cleaned = [clean_job(job, patterns) for job in jobs]
    summary = {
        "total_before": len(cleaned),
        "total_after": 0,
    }
    for result_type in RESULT_TYPES:
        if result_type != "job":
            summary[f"removed_{result_type}"] = 0

    job_results = []
    for job in cleaned:
        result_type = job["result_type"]
        if result_type == "job":
            job_results.append(job)
        else:
            summary[f"removed_{result_type}"] = summary.get(f"removed_{result_type}", 0) + 1

    summary["total_after"] = len(job_results)
    return job_results, summary


def load_jobs(input_path):
    path = Path(input_path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return data


def write_jobs(jobs, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {path}: {len(jobs)} rows")


def print_cleaning_summary(summary):
    print(f"Total before cleaning: {summary['total_before']}")
    print(f"Removed search_page: {summary['removed_search_page']}")
    print(f"Removed category_page: {summary['removed_category_page']}")
    print(f"Removed aggregator_page: {summary['removed_aggregator_page']}")
    print(f"Removed article: {summary['removed_article']}")
    print(f"Removed profile: {summary['removed_profile']}")
    print(f"Removed excluded_domain: {summary['removed_excluded_domain']}")
    print(f"Removed unknown: {summary['removed_unknown']}")
    print(f"Total after cleaning: {summary['total_after']}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args(argv)


def main():
    args = parse_args()
    jobs = load_jobs(args.input)
    cleaned, summary = clean_results_with_summary(jobs)
    print_cleaning_summary(summary)
    write_jobs(cleaned, args.output)


if __name__ == "__main__":
    main()
