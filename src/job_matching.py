from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit


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
    "campania",
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


def detect_remote(title="", snippet="", query=""):
    return has_any(combined_text(title, snippet, query), REMOTE_TERMS)


def detect_part_time(title="", snippet="", query=""):
    return has_any(combined_text(title, snippet, query), PART_TIME_TERMS)


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


def score_job(title="", snippet="", query=""):
    text = combined_text(title, snippet, query)
    score = 0
    if has_any(text, PART_TIME_TERMS):
        score += 40
    if has_any(text, LOCAL_TERMS):
        score += 35
    if has_any(text, DATA_TERMS):
        score += 30
    if has_any(text, REMOTE_TERMS):
        score += 25
    if has_any(text, AI_TERMS):
        score += 15
    if has_any(text, ECOMMERCE_TERMS):
        score += 10
    if has_any(text, BAD_JOB_TERMS):
        score -= 30
    return score


def detect_priority_bucket(text="", part_time=False, remote=False):
    searchable = str(text or "").lower()
    if part_time and has_any(searchable, LOCAL_TERMS):
        return "campania_part_time"
    if remote:
        return "remote_data"
    if has_any(searchable, LOCAL_TERMS):
        return "local_general"
    return "other"


def dedup_key(job):
    if job.get("url"):
        return normalize_url(job["url"])
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


dedup = deduplicate_jobs
