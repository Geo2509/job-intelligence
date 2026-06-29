from urllib.parse import parse_qsl, urlsplit


LISTING_TITLE_TERMS = [
    "hiring now",
    "job search",
    "search results",
    "jobs found",
    "open jobs",
    "vacancies",
]
LISTING_TITLE_PREFIXES = [
    "top ",
]
LISTING_URL_PATTERNS = [
    "/jobs/search",
    "/job-search",
    "/search",
    "/careers/search",
    "/offerte-lavoro",
]
LISTING_PATH_EXACT_OR_PREFIX = [
    "/jobs",
    "/remote-jobs",
]
SEARCH_QUERY_KEYS = {"q", "query", "keyword", "keywords", "what", "where"}
GENERIC_LISTING_HOSTS = [
    "indeed.",
    "jooble.",
    "linkedin.",
    "virtualvocations.com",
]
MISMATCH_LANGUAGE_TERMS = [
    "korean",
    "japanese",
    "german",
    "french",
    "spanish",
    "dutch",
    "portuguese",
    "arabic",
    "hindi",
    "chinese",
    "swedish",
    "norwegian",
    "polish",
    "czech",
    "turkish",
]
TARGET_LANGUAGE_TERMS = ["russian", "ukrainian", "русский", "украинский"]


def normalized_text(value):
    return " ".join(str(value or "").lower().split())


def candidate_text(job):
    return " ".join(
        normalized_text(job.get(field, ""))
        for field in ("title", "company", "location", "description", "score_reason", "url", "source")
    )


def title_text(job):
    return normalized_text(job.get("title", ""))


def has_any(text, terms):
    return any(term in text for term in terms)


def hostname(url):
    host = urlsplit(str(url or "")).hostname or ""
    if host.startswith("www."):
        return host[4:]
    return host.lower()


def is_search_like_url(url):
    parsed = urlsplit(str(url or ""))
    path = parsed.path.lower().rstrip("/")
    query_keys = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    host = hostname(url)

    if any(pattern in path for pattern in LISTING_URL_PATTERNS):
        return True
    if any(path == pattern or path.startswith(f"{pattern}/") for pattern in LISTING_PATH_EXACT_OR_PREFIX):
        if SEARCH_QUERY_KEYS.intersection(query_keys) or len(query_keys) >= 3:
            return True
    if "/q-" in path:
        return True
    if SEARCH_QUERY_KEYS.intersection(query_keys) and any(marker in host for marker in GENERIC_LISTING_HOSTS):
        return True
    return False


def is_search_page(job):
    title = title_text(job)
    text = candidate_text(job)
    url = str(job.get("url", "") or "")
    if any(title.startswith(prefix) for prefix in LISTING_TITLE_PREFIXES) and " job" in title:
        return True
    if has_any(text, LISTING_TITLE_TERMS):
        return True
    if "remote jobs" in title or "jobs in " in title:
        return True
    return is_search_like_url(url)


def has_language_mismatch(job):
    title = title_text(job)
    if not has_any(title, MISMATCH_LANGUAGE_TERMS):
        return False
    return not has_any(title, TARGET_LANGUAGE_TERMS)


def build_remote_match_summary(job):
    text = candidate_text(job)
    summary = []
    if has_any(text, ["remote", "work from home", "worldwide", "home based"]):
        summary.append("Remote")
    if has_any(text, ["russian", "russian language", "русский"]):
        summary.append("Russian language")
    if has_any(text, ["ukrainian", "ukrainian language", "украинский"]):
        summary.append("Ukrainian language")
    if has_any(text, ["data annotation", "data annotator", "annotation", "ai trainer", "ai annotator"]):
        summary.append("AI Data Annotation")
    if "data labeling" in text:
        summary.append("Data Labeling")
    if has_any(text, ["transcription", "audio"]):
        summary.append("Transcription")
    if "virtual assistant" in text:
        summary.append("Virtual Assistant")
    if has_any(text, ["admin", "administrative", "back office"]):
        summary.append("Administration / Back Office")
    if "data entry" in text:
        summary.append("Data Entry")
    return list(dict.fromkeys(summary))


def classify_remote_email_candidate(job):
    classified = dict(job)
    flags = []
    result_type = "job"
    rejection_reason = ""

    if is_search_page(classified):
        result_type = "search_page"
        rejection_reason = "search_page"
        flags.append("search_or_listing_page")
    elif has_language_mismatch(classified):
        result_type = "language_mismatch"
        rejection_reason = "language_mismatch"
        flags.append("title_language_mismatch")

    classified["remote_email_result_type"] = result_type
    classified["remote_email_rejection_reason"] = rejection_reason
    classified["remote_email_quality_flags"] = flags
    classified["remote_match_summary"] = build_remote_match_summary(classified)
    return classified


def is_remote_email_eligible(job):
    return not classify_remote_email_candidate(job)["remote_email_rejection_reason"]


def clean_remote_email_candidates(jobs):
    return [
        classified
        for classified in (classify_remote_email_candidate(job) for job in jobs)
        if not classified["remote_email_rejection_reason"]
    ]


def remote_email_cleaning_stats(jobs):
    classified_rows = [classify_remote_email_candidate(job) for job in jobs]
    rejected = [
        job
        for job in classified_rows
        if job["remote_email_rejection_reason"]
    ]
    return {
        "quality_rejected": len(rejected),
        "rejected_search_pages": sum(1 for job in rejected if job["remote_email_rejection_reason"] == "search_page"),
        "rejected_language_mismatch": sum(
            1 for job in rejected if job["remote_email_rejection_reason"] == "language_mismatch"
        ),
        "rejected_low_quality": sum(
            1
            for job in rejected
            if job["remote_email_rejection_reason"] not in {"search_page", "language_mismatch"}
        ),
    }
