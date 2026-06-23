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
    "concorso",
    "scuola",
    "istituto",
    "liceo",
    "motocross",
    "partita",
    "campionato",
    "posti agente",
    "comune di",
    "circolare",
]
TRUSTED_SOFT_SOURCES = [
    ("subito.it", "/offerte-lavoro"),
    ("subito.it", "/annunci-"),
    ("lavoro.lidl.it", "/annunci-di-lavoro"),
    ("lavoro.lidl.it", "/punti-vendita/"),
    ("eurospin.it", "/lavora-con-noi"),
    ("randstad.it", "/offerte-lavoro/"),
    ("manpower.it", "/trova-lavoro"),
]
EUROSPIN_ROLE_TERMS = [
    "addetto",
    "addetta",
    "vendita",
    "vendite",
    "cassiere",
    "cassiera",
    "scaffalista",
    "magazziniere",
    "responsabile",
    "store manager",
    "vice store",
    "operatore",
    "operatrice",
]
RANDSTAD_SEARCH_PATH_PARTS = [
    "/q-",
    "/re-",
    "/ci-",
]
MANPOWER_VACANCY_PATH_PARTS = [
    "/annuncio-lavoro/",
    "/offerte-lavoro/",
    "/job/",
    "/jobs/",
]
RESULT_TYPES = [
    "job",
    "search_page",
    "category_page",
    "aggregator_page",
    "article",
    "profile",
    "company_page",
    "career_page",
    "excluded_domain",
    "unknown",
]
URL_REMOVED_RESULT_TYPES = {
    "search_page",
    "category_page",
    "aggregator_page",
    "article",
    "profile",
    "company_page",
    "career_page",
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


def normalized_hostname(hostname):
    hostname = lower_text(hostname)
    if hostname.startswith("www."):
        return hostname[4:]
    return hostname


def is_trusted_soft_result(job):
    parsed = urlsplit(str(job.get("url", "") or ""))
    hostname = normalized_hostname(parsed.hostname or "")
    path = lower_text(parsed.path)
    return any(
        hostname == trusted_host and trusted_path in path
        for trusted_host, trusted_path in TRUSTED_SOFT_SOURCES
    )


def is_generic_lavora_con_noi_title(title):
    title = lower_text(title)
    generic_titles = {
        "lavora con noi",
        "eurospin lavora con noi",
        "lavora con noi eurospin",
    }
    return title in generic_titles


def has_concrete_eurospin_role(job):
    title = lower_text(job.get("title", ""))
    if is_generic_lavora_con_noi_title(title):
        return False
    return any(term in title for term in EUROSPIN_ROLE_TERMS)


def is_randstad_vacancy_url(path):
    if not path.startswith("/offerte-lavoro/"):
        return False
    if path.rstrip("/") == "/offerte-lavoro":
        return False
    if any(part in path for part in RANDSTAD_SEARCH_PATH_PARTS):
        return False
    return len([part for part in path.strip("/").split("/") if part]) >= 2


def is_manpower_vacancy_url(path):
    if path.rstrip("/").endswith("/trova-lavoro"):
        return False
    return any(part in path for part in MANPOWER_VACANCY_PATH_PARTS)


def is_cerco_lavoro_page(job):
    parsed = urlsplit(str(job.get("url", "") or ""))
    text = lower_text(" ".join([
        normalized_hostname(parsed.hostname or ""),
        parsed.path,
        job.get("title", ""),
        snippet_text(job),
    ]))
    return "cerco-lavoro" in text or "cerco lavoro" in text


def is_email_trusted_result(job):
    if job.get("url_result_type") == "real_job" and job.get("result_type") == "job":
        return True

    parsed = urlsplit(str(job.get("url", "") or ""))
    hostname = normalized_hostname(parsed.hostname or "")
    path = lower_text(parsed.path)

    if hostname == "lavoro.lidl.it" and "/punti-vendita/" in path:
        return True
    if hostname == "eurospin.it" and "/lavora-con-noi" in path:
        return has_concrete_eurospin_role(job)
    if hostname == "randstad.it":
        return is_randstad_vacancy_url(path)
    if hostname == "manpower.it":
        return is_manpower_vacancy_url(path)
    return False


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
    return "unknown"


def detect_result_type(job, patterns=None):
    patterns = patterns if patterns is not None else load_url_patterns()
    url_result_type = classify_url(job.get("url", ""), patterns)
    if title_or_snippet_has_article_blacklist(job):
        return "article"
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


def keep_cleaned_job(job, strict_job_detail_only=False, email_clean_results=False):
    if strict_job_detail_only:
        return job.get("url_result_type") == "real_job" and job.get("result_type") == "job"
    if email_clean_results:
        if is_cerco_lavoro_page(job):
            return False
        return is_email_trusted_result(job)
    if job.get("result_type") == "job":
        return True
    if job.get("result_type") in {"article", "profile", "excluded_domain", "unknown"}:
        return False
    return is_trusted_soft_result(job)


def clean_results(jobs, strict_job_detail_only=False, email_clean_results=False):
    patterns = load_url_patterns()
    cleaned = [clean_job(job, patterns) for job in jobs]
    return [
        job
        for job in cleaned
        if keep_cleaned_job(
            job,
            strict_job_detail_only=strict_job_detail_only,
            email_clean_results=email_clean_results,
        )
    ]


def clean_results_with_summary(jobs, strict_job_detail_only=False, email_clean_results=False):
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
        if keep_cleaned_job(
            job,
            strict_job_detail_only=strict_job_detail_only,
            email_clean_results=email_clean_results,
        ):
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
    print(f"Removed company_page: {summary['removed_company_page']}")
    print(f"Removed career_page: {summary['removed_career_page']}")
    print(f"Removed excluded_domain: {summary['removed_excluded_domain']}")
    print(f"Removed unknown: {summary['removed_unknown']}")
    print(f"Total after cleaning: {summary['total_after']}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--email-clean-results", action="store_true")
    parser.add_argument("--strict-job-detail-only", action="store_true")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    jobs = load_jobs(args.input)
    cleaned, summary = clean_results_with_summary(
        jobs,
        strict_job_detail_only=args.strict_job_detail_only,
        email_clean_results=args.email_clean_results,
    )
    print_cleaning_summary(summary)
    write_jobs(cleaned, args.output)


if __name__ == "__main__":
    main()
