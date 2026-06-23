from pathlib import Path
from urllib.parse import urlsplit

import yaml


DEFAULT_URL_PATTERNS_PATH = "configs/job_url_patterns.yaml"
URL_RESULT_TYPES = {
    "real_job",
    "search_page",
    "category_page",
    "aggregator_page",
    "article",
    "profile",
    "company_page",
    "career_page",
    "excluded_domain",
    "unknown",
}
PATTERN_RESULT_TYPES = [
    "job",
    "search",
    "category_page",
    "aggregator_page",
    "article",
    "profile",
    "company_page",
    "career_page",
]


def load_url_patterns(path=DEFAULT_URL_PATTERNS_PATH):
    pattern_path = Path(path)
    if not pattern_path.exists():
        return {}
    data = yaml.safe_load(pattern_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {pattern_path}")
    return data


def normalize_hostname(hostname):
    hostname = str(hostname or "").strip().lower()
    if hostname.startswith("www."):
        return hostname[4:]
    return hostname


def normalized_url_parts(url):
    parsed = urlsplit(str(url or ""))
    hostname = normalize_hostname(parsed.hostname or "")
    path = parsed.path or "/"
    target = path
    if parsed.query:
        target = f"{target}?{parsed.query}"
    return hostname, target.lower()


def normalized_domains(domains):
    return {normalize_hostname(domain) for domain in domains or []}


def domain_matches(hostname, domains):
    normalized = normalized_domains(domains)
    return hostname in normalized


def pattern_matches(target, pattern):
    return str(pattern or "").lower() in target


def more_specific_search_match(target, job_patterns, search_patterns):
    matching_search = [
        str(pattern or "").lower()
        for pattern in search_patterns or []
        if pattern_matches(target, pattern)
    ]
    matching_job = [
        str(pattern or "").lower()
        for pattern in job_patterns or []
        if pattern_matches(target, pattern)
    ]
    return any(
        search_pattern.startswith(job_pattern) and len(search_pattern) > len(job_pattern)
        for search_pattern in matching_search
        for job_pattern in matching_job
    )


def classify_url(url, patterns):
    hostname, target = normalized_url_parts(url)
    if not hostname:
        return "unknown"

    excluded_domains = normalized_domains(patterns.get("general_exclude_domains", []))
    if hostname in excluded_domains:
        return "excluded_domain"

    for source_name, source_patterns in patterns.items():
        if source_name == "general_exclude_domains":
            continue
        if not domain_matches(hostname, source_patterns.get("domains", [])):
            continue

        job_patterns = source_patterns.get("job", [])
        search_patterns = source_patterns.get("search", [])
        if more_specific_search_match(target, job_patterns, search_patterns):
            return "search_page"

        for pattern_type in PATTERN_RESULT_TYPES:
            result_type = "real_job" if pattern_type == "job" else pattern_type
            if pattern_type == "search":
                result_type = "search_page"
            for pattern in source_patterns.get(pattern_type, []):
                if pattern_matches(target, pattern):
                    return result_type
        return "unknown"

    return "unknown"
