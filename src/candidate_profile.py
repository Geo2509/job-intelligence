from pathlib import Path
import re

import yaml


DEFAULT_PROFILE_PATH = Path(__file__).resolve().parents[1] / "configs" / "candidate_profile.yaml"

BONUSES = [
    (["data entry", "inserimento dati"], 20),
    (["back office"], 20),
    (["office", "ufficio", "office assistant"], 20),
    (["administration", "amministrazione", "amministrativo", "segreteria"], 20),
    (["reception", "receptionist", "front office"], 15),
    (["excel"], 20),
    (["google sheets"], 20),
    (["python"], 15),
    (["logistics", "logistica", "spedizioni", "shipping", "freight forwarding"], 15),
    (["warehouse", "magazzino", "magazziniere"], 10),
    (["customer service", "assistenza clienti", "servizio clienti"], 10),
    (["hotel", "albergo", "hotel reception"], 10),
]
PENALTIES = [
    (["laurea obbligatoria", "laurea richiesta", "laurea necessaria"], -25),
    (["5 anni", "5+ anni", "almeno 5 anni", "minimo 5 anni"], -15),
    (["night shift", "turno notte", "notturno", "notte"], -20),
    (["english c1", "inglese c1", "c1 english", "c1 inglese"], -20),
]
PART_TIME_TERMS = ["part time", "part-time", "tempo parziale"]
STAGE_TERMS = ["stage", "tirocinio", "internship"]
ITALIAN_B2_TERMS = ["italian b2", "italiano b2", "b2 italiano", "b2 italian"]
ITALIAN_C1_TERMS = ["italian c1", "italiano c1", "c1 italiano", "c1 italian"]


def load_candidate_profile(path=DEFAULT_PROFILE_PATH):
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def normalized_text(value):
    text = str(value or "").lower()
    text = re.sub(r"[-_'/]+", " ", text)
    text = re.sub(r"[^a-z0-9àèéìòù]+", " ", text)
    return " ".join(text.split())


def job_text(job):
    return normalized_text(
        " ".join(
            str(job.get(field, "") or "")
            for field in (
                "title",
                "company",
                "location",
                "url",
                "category",
                "query",
                "description",
                "snippet",
                "summary",
            )
        )
    )


def has_any(text, terms):
    return any(normalized_text(term) in text for term in terms)


def evaluate_candidate_score(job):
    text = job_text(job)
    score = 50

    for terms, bonus in BONUSES:
        if has_any(text, terms):
            score += bonus

    if bool(job.get("part_time")) or has_any(text, PART_TIME_TERMS):
        score += 10
    if has_any(text, STAGE_TERMS):
        score += 5

    if has_any(text, ITALIAN_B2_TERMS):
        score -= 10
    if has_any(text, ITALIAN_C1_TERMS):
        score -= 20

    for terms, penalty in PENALTIES:
        if has_any(text, terms):
            score += penalty

    return max(0, min(100, int(score)))


def calculate_match_score(student_score, candidate_score):
    return int(round(0.45 * int(student_score or 0) + 0.55 * int(candidate_score or 0)))
