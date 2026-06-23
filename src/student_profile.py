from pathlib import Path

import yaml


DEFAULT_PROFILE_PATH = Path(__file__).resolve().parents[1] / "configs" / "student_profile.yaml"

LOCATION_BONUSES = {
    "napoli": 20,
    "pozzuoli": 20,
    "bacoli": 20,
    "monte di procida": 20,
}
CATEGORY_BONUSES = {
    "data_office": 20,
    "administration": 20,
    "reception": 15,
    "hotel": 15,
    "hospitality": 15,
    "cleaning": 10,
    "maintenance": 10,
    "warehouse": 5,
    "gdo": 5,
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
}
CATEGORY_ALIASES = {
    "data_entry": "data_office",
    "campania_part_time_data": "data_office",
    "office": "data_office",
    "admin": "administration",
    "pulizie": "cleaning",
    "manutenzione": "maintenance",
    "logistics": "warehouse",
}


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
            "category",
            "query",
            "description",
            "snippet",
            "summary",
        )
    ).lower()


def normalized_category(job):
    category = str(job.get("category", "") or "").lower()
    return CATEGORY_ALIASES.get(category, category)


def has_category_signal(job, category, text):
    if normalized_category(job) == category:
        return True
    return any(term in text for term in CATEGORY_TERMS.get(category, []))


def evaluate_student_score(job):
    text = job_text(job)
    score = 50

    if bool(job.get("remote")) or "remote" in text or "remoto" in text or "smart working" in text:
        score += 30
    if "full remote" in text:
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

    return max(0, min(100, int(score)))
