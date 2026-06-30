from pathlib import Path
import re

import yaml


DEFAULT_PROFILE_PATH = Path(__file__).resolve().parents[1] / "configs" / "student_profile.yaml"
PREFERRED_TITLE_BONUS = 7

LOCATION_BONUSES = {
    "napoli": 20,
    "pozzuoli": 20,
    "bacoli": 20,
    "monte di procida": 20,
    "casoria": 15,
    "caivano": 15,
    "arzano": 15,
    "marano di napoli": 15,
}
CATEGORY_BONUSES = {
    "data_office": 20,
    "data_entry": 20,
    "back_office": 20,
    "administration": 20,
    "accounting": 15,
    "logistics": 15,
    "customer_service": 15,
    "reception": 15,
    "hotel": 15,
    "hospitality": 15,
    "cleaning": 10,
    "maintenance": 10,
    "warehouse": 5,
    "gdo": 5,
    "facilities": 5,
}
KEYWORD_BONUSES = {
    "mattina": 15,
    "lun-ven": 10,
    "tempo parziale": 10,
}
PENALTIES = {
    "notturno": -40,
    "sera": -20,
    "night": -40,
}
CATEGORY_TERMS = {
    "data_office": [
        "data office",
        "data entry",
        "inserimento dati",
        "back office",
        "ufficio",
        "excel",
        "google sheets",
    ],
    "administration": [
        "administration",
        "administrative",
        "amministrazione",
        "amministrativo",
        "segreteria",
        "segretaria",
    ],
    "reception": ["reception", "receptionist", "front office"],
    "hotel": ["hotel", "albergo"],
    "hospitality": ["hospitality", "ristorante", "bar", "cameriere", "turismo"],
    "cleaning": ["cleaning", "cleaner", "pulizie", "addetto pulizie", "addetta pulizie"],
    "maintenance": ["maintenance", "manutenzione", "manutentore"],
    "warehouse": ["warehouse", "magazzino", "magazziniere", "logistica"],
    "gdo": ["gdo", "supermercato", "scaffalista", "cassiere", "addetto vendita"],
    "accounting": ["contabile", "contabilità", "contabilita", "ciclo attivo", "ciclo passivo", "tesoreria"],
    "logistics": ["logistica", "spedizioni", "supply chain", "trasporti"],
    "customer_service": ["customer service", "assistenza clienti", "servizio clienti", "call center"],
    "facilities": ["facilities", "facility", "servizi generali"],
}
CATEGORY_ALIASES = {
    "ai_data": "ai_annotation",
    "data_entry": "data_office",
    "campania_part_time_data": "data_office",
    "office": "data_office",
    "admin": "administration",
    "pulizie": "cleaning",
    "manutenzione": "maintenance",
    "logistics": "warehouse",
}
REMOTE_TERMS = [
    "remote",
    "remoto",
    "smart working",
    "full remote",
    "lavoro da casa",
]


def load_student_profile(path=DEFAULT_PROFILE_PATH):
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def job_text(job):
    return " ".join(
        str(job.get(field, "") or "")
        for field in (
            "title",
            "company",
            "location",
            "url",
            "category",
            "description",
            "snippet",
            "summary",
        )
    ).lower()


def profile_config(profile):
    return profile.get("profile", profile or {})


def normalized_match_text(value):
    text = str(value or "").lower()
    text = re.sub(r"[-_'/]+", " ", text)
    text = re.sub(r"[^a-z0-9àèéìòù]+", " ", text)
    return " ".join(text.split())


def text_has_any(text, terms):
    normalized_text = normalized_match_text(text)
    normalized_terms = [
        normalized_match_text(term)
        for term in terms or []
    ]
    return any(term in normalized_text for term in normalized_terms if term)


def matching_keyword(text, terms):
    normalized_text = normalized_match_text(text)
    for term in terms or []:
        normalized_term = normalized_match_text(term)
        if normalized_term and normalized_term in normalized_text:
            return str(term)
    return None


def detect_location_fit(job, profile):
    profile = profile_config(profile)
    local_text = " ".join(
        str(job.get(field, "") or "")
        for field in ("location", "title", "url")
    )

    if bool(job.get("remote")):
        return "remote"
    if text_has_any(local_text, profile.get("allowed_locations", [])):
        return "allowed_local"
    if text_has_any(local_text, profile.get("excluded_locations", [])):
        return "excluded_far"
    return "unknown"


def normalized_category(job):
    category = str(job.get("category", "") or "").lower()
    return CATEGORY_ALIASES.get(category, category)


def has_category_signal(job, category, text):
    if normalized_category(job) == category:
        return True
    return any(term in text for term in CATEGORY_TERMS.get(category, []))


def evaluate_student_score(job):
    profile = load_student_profile()
    profile_settings = profile_config(profile)
    title = str(job.get("title", "") or "")
    unwanted_keyword = matching_keyword(title, profile_settings.get("unwanted_titles", []))
    if unwanted_keyword:
        job["profile_match"] = False
        job["selection_rejection_reason"] = "unwanted_title"
        job["profile_reason"] = "unwanted_title"
        job["matched_keyword"] = unwanted_keyword
        job["candidate_score"] = 0
        job["negative_reason"] = "excluded title unwanted_title"
        return 0

    location_fit = job.get("location_fit") or detect_location_fit(job, profile)
    text = job_text(job)
    score = 50
    preferred_keyword = matching_keyword(title, profile_settings.get("preferred_titles", []))

    if bool(job.get("remote")):
        score += 30
    if bool(job.get("remote")) and "full remote" in text:
        score += 30
    if bool(job.get("part_time")) or "part time" in text or "part-time" in text:
        score += 25

    for location, bonus in LOCATION_BONUSES.items():
        if location in text:
            score += bonus

    for category, bonus in CATEGORY_BONUSES.items():
        if has_category_signal(job, category, text):
            score += bonus

    for keyword, bonus in KEYWORD_BONUSES.items():
        if keyword in text:
            score += bonus

    for keyword, penalty in PENALTIES.items():
        if keyword in text:
            score += penalty

    if preferred_keyword:
        score += PREFERRED_TITLE_BONUS
        job["profile_match"] = True
        job["profile_reason"] = "preferred_title"
        job["matched_keyword"] = preferred_keyword

    if location_fit == "excluded_far":
        score = min(score, 40)
    elif location_fit == "unknown":
        score = min(score, 70)

    return max(0, min(100, int(score)))
