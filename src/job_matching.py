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
    "da remoto",
    "smart working",
    "smartworking",
    "lavoro da casa",
    "work from home",
    "home based",
    "100% remote",
    "full remote",
    "ibrido",
    "hybrid",
    "telelavoro",
    "online",
]
NEGATIVE_REMOTE_TERMS = [
    "in sede",
    "presenza",
    "in presenza",
    "on site",
    "onsite",
    "non remoto",
    "no smart working",
    "no smartworking",
    "sede di lavoro",
]
PART_TIME_TERMS = [
    "part-time",
    "part time",
    "tempo parziale",
    "4 ore",
    "6 ore",
    "20 ore",
]
CATEGORY_RULES = [
    ("hr_recruiting", ["talent acquisition", "recruiter", "recruiting", "risorse umane", "human resources"]),
    ("design", ["grafico", "graphic designer", "designer", "photoshop", "illustrator"]),
    ("accounting", ["contabile", "contabilità", "contabilita", "ciclo attivo", "ciclo passivo", "tesoreria", "sap contabile"]),
    ("logistics", ["logistica", "spedizioni", "spedizioni aeree", "supply chain", "trasporti", "shipping", "freight forwarding"]),
    ("facilities", ["facilities", "facility", "maintenance office", "servizi generali"]),
    ("security", ["security", "vigilanza", "sicurezza", "sorveglianza"]),
    ("customer_service", ["customer service", "call center", "operatori inbound", "operatore inbound", "assistenza clienti", "servizio clienti"]),
    ("data_entry", ["data entry", "inserimento dati", "back office data entry"]),
    ("administration", ["ufficio amministrativo", "impiegato amministrativo", "addetto amministrativo", "ufficio acquisti", "acquisti", "amministrativo", "amministrativa", "amministrazione"]),
    ("back_office", ["back office", "segreteria", "segretaria"]),
    ("reception", ["receptionist", "reception", "front office", "accoglienza"]),
    ("hotel", ["boutique hotel", "housekeeping", "portiere", "hotel", "albergo"]),
    ("cleaning", ["pulizie", "addetto pulizie", "addetta pulizie", "sanificazione", "cleaning", "cleaner"]),
    ("warehouse", ["magazziniere", "magazzino", "picking", "scaffalista", "carico scarico", "carico/scarico", "warehouse"]),
    ("gdo", ["addetto vendita", "addetta vendita", "cassiere", "cassiera", "gdo", "supermercato"]),
    ("sales", ["sales", "venditore", "commerciale", "addetto vendite", "addetta vendite"]),
    ("technical", ["tecnico", "elettricista", "idraulico", "manutentore", "meccanico", "montatore"]),
]
DATA_TERMS = [
    "data entry",
    "inserimento dati",
    "back office data entry",
    "excel",
    "google sheets",
]
OFFICE_DATA_GUARD_TERMS = [
    "data entry",
    "inserimento dati",
    "back office",
    "amministrativo",
    "amministrativa",
    "contabile",
    "logistica",
    "spedizioni",
    "excel",
    "google sheets",
]
GENERIC_OFFICE_TERMS = ["office", "ufficio", "consultant", "junior officer", "specialist"]
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


def remote_reason_from_fields(fields):
    for label, value in fields:
        text = str(value or "").lower()
        for term in NEGATIVE_REMOTE_TERMS:
            if term in text:
                return False, f"negative: {term}"
    for label, value in fields:
        text = str(value or "").lower()
        for term in REMOTE_TERMS:
            if term in text:
                return True, f"{label}: {term}"
    return False, "none"


def detect_remote_reason(
    title="",
    snippet="",
    query="",
    location="",
    url="",
    description="",
    include_query=False,
):
    fields = [
        ("title", title),
        ("description", description),
        ("snippet", snippet),
        ("location", location),
        ("url", url),
    ]
    if include_query:
        fields.append(("query", query))
    return remote_reason_from_fields(fields)[1]


def detect_remote(title="", snippet="", query="", location="", url="", description="", include_query=False):
    fields = [
        ("title", title),
        ("description", description),
        ("snippet", snippet),
        ("location", location),
        ("url", url),
    ]
    if include_query:
        fields.append(("query", query))
    return remote_reason_from_fields(fields)[0]


def detect_part_time(title="", snippet="", query=""):
    return has_any(combined_text(title, snippet, query), PART_TIME_TERMS)


def detect_category(title="", snippet="", query=""):
    text = combined_text(title, snippet, "")
    if has_any(text, AI_TERMS):
        return "ai_annotation"
    if has_any(text, DATA_TERMS) and (
        has_any(text, OFFICE_DATA_GUARD_TERMS) or not has_any(text, GENERIC_OFFICE_TERMS)
    ):
        return "data_entry"
    for category, terms in CATEGORY_RULES:
        if category == "data_entry":
            continue
        if has_any(text, terms):
            return category
    if has_any(text, ECOMMERCE_TERMS):
        return "ecommerce"
    if has_any(text, REMOTE_TERMS):
        return "remote_data"
    if has_any(text, PART_TIME_TERMS):
        return "part_time"
    return "other"


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
