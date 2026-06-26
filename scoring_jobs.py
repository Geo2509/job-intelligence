import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd

from config_loader import DEFAULT_SCORING_FILE, load_scoring_config
from src.csv_utils import set_csv_field_limit


OUTPUT_FILE = "scored_jobs.csv"
XLSX_OUTPUT_FILE = "scored_jobs.xlsx"
TOP_REPORT_LIMIT = 50
TOP_OUTPUT_FILE = "top_50_jobs.csv"
TOP_XLSX_OUTPUT_FILE = "top_50_jobs.xlsx"
SEARCH_DESCRIPTION_LIMIT = 6000
OUTPUT_COLUMNS = [
    "job_score",
    "apply_priority",
    "normalized_remote_category",
    "country_restriction",
    "employment_type",
    "salary_min",
    "salary_max",
    "currency",
    "salary_text",
    "source",
    "title",
    "company",
    "location",
    "url",
    "clickable",
    "positive_reason",
    "negative_reason",
    "score_reason",
]
TOP_JOBS_MIN_SCORE = 70
PRIORITY_HIGH_SCORE = 90
PRIORITY_MEDIUM_SCORE = 75

REMOTE_CATEGORY_RULES = [
    ("AI Training", ["ai trainer", "ai evaluator", "ai tutor", "search evaluator", "rlhf", "human feedback"]),
    ("AI Annotation", ["ai annotation", "ai annotator", "data annotation", "data annotator", "data labeling", "llm annotation"]),
    ("Data Entry", ["data entry", "data processing", "inserimento dati", "excel", "google sheets", "csv", "validation", "qa data"]),
    ("Virtual Assistant", ["virtual assistant", "administrative assistant", "back office", "admin assistant"]),
    ("Logistics", ["ocean freight", "shipping", "freight forwarding", "container", "supply chain", "logistics coordinator"]),
    ("Analytics", ["operations analyst", "junior analyst", "reporting analyst", "analytics", "dashboard", "reporting"]),
    ("Python", ["python", "automation", "pandas", "api"]),
    ("Customer Support", ["customer support", "customer service", "support specialist"]),
    ("Translation", ["translation", "translator", "localization", "localisation", "multilingual"]),
    ("Transcription", ["transcription", "transcriber", "speech", "audio annotation"]),
    ("Moderation", ["content moderator", "content moderation", "moderation", "content reviewer"]),
    ("Research", ["research assistant", "research", "web research"]),
]

COUNTRY_RESTRICTION_RULES = [
    ("US only", ["us only", "u.s. only", "usa only", "united states only", "must be based in the us", "us-based only"]),
    ("Canada only", ["canada only", "canadian only", "must be based in canada"]),
    ("Brazil only", ["brazil only", "brazilian only", "brasil only"]),
    ("LATAM only", ["latam only", "latin america only", "south america only"]),
    ("India only", ["india only", "india-based only", "must be based in india"]),
    ("Italy", ["italy only", "italia", "italy-based", "based in italy"]),
    ("Europe", ["europe only", "european time zones", "european timezone", "based in europe"]),
    ("EU", ["eu only", "european union"]),
    ("EMEA", ["emea"]),
    ("Worldwide", ["worldwide", "anywhere", "global", "fully remote", "work from anywhere"]),
]

EMPLOYMENT_TYPE_RULES = [
    ("Part-time", ["part-time", "part time", "tempo parziale"]),
    ("Full-time", ["full-time", "full time", "tempo pieno"]),
    ("Contract", ["contract", "contractor", "contratto"]),
    ("Freelance", ["freelance", "freelancer"]),
    ("Project", ["project based", "project-based", "per project"]),
    ("Temporary", ["temporary", "temp", "fixed term", "tempo determinato"]),
    ("Internship", ["internship", "intern", "stage", "tirocinio"]),
]

COUNTRY_SCORE_WEIGHTS = {
    "Worldwide": 20,
    "Europe": 15,
    "EU": 15,
    "Italy": 15,
    "EMEA": 10,
    "US only": -40,
    "Canada only": -35,
    "Brazil only": -40,
    "LATAM only": -40,
    "India only": -40,
}

REMOTE_POSITIVE_RULES = [
    ("AI Trainer", ["ai trainer", "ai evaluator", "ai tutor"], 45),
    ("AI Annotation", ["ai annotation", "data annotation", "data labeling", "human feedback", "rlhf", "llm"], 45),
    ("Data", ["data entry", "excel", "google sheets", "csv", "reporting", "dashboard", "validation", "qa data"], 35),
    ("Logistics", ["ocean freight", "shipping", "freight forwarding", "container", "supply chain", "operations analyst", "logistics coordinator"], 40),
    ("Languages", ["ukrainian", "russian", "english", "multilingual", "українська", "русский"], 20),
    ("Virtual Assistant", ["virtual assistant", "administrative", "back office"], 30),
]

REMOTE_NEGATIVE_RULES = [
    ("seniority", ["senior", "lead", "principal", "head", "director", "manager", "staff engineer"], -35),
    ("country", ["us only", "canada only", "latam only", "brazil only", "india only"], -40),
    ("restriction", ["relocation required", "security clearance", "licensed", "certification required"], -35),
    ("irrelevant", ["geopolitical", "intelligence analyst", "military", "cyber security", "cybersecurity", "soc analyst", "penetration testing"], -55),
    ("medical", ["physician", "medical doctor", "doctor", "nurse", "dentist", "pharmacist"], -60),
    ("low priority", ["sales", "marketing", "recruiter", "hr", "graphic design", "manual qa", "finance senior", "project manager"], -30),
]


POSITIVE_WEIGHTS = {
    "shipping coordinator": 45,
    "freight coordinator": 45,
    "booking coordinator": 45,
    "ocean freight coordinator": 50,
    "logistics": 25,
    "freight": 25,
    "logistics operations": 40,
    "freight operations": 40,
    "container booking": 45,
    "shipment coordinator": 45,
    "operations coordinator": 40,
    "workflow automation": 40,
    "shipping line": 40,
    "carrier coordination": 40,
    "local agent coordination": 40,
    "port operations": 40,
    "container shipping": 45,
    "ocean export": 45,
    "ocean import": 45,
    "freight forwarding": 45,
    "maritime": 30,
    "maritime logistics": 45,
    "international logistics": 40,
    "china logistics": 40,
    "asia logistics": 40,
    "cargo operations": 40,
    "container operations": 45,
    "vessel operations": 40,
    "terminal operator": 45,
    "port authority": 45,
    "shipping analyst": 50,
    "container analyst": 50,
    "trade analyst": 40,
    "intelligence": 20,
    "market intelligence": 40,
    "business intelligence": 35,
    "supply chain": 35,
    "supply chain operations": 40,
    "transport planning": 45,
    "dispatch": 35,
    "fleet coordination": 35,
    "export operations": 45,
    "import operations": 45,
    "customs": 30,
    "customs documentation": 40,
    "transportation": 30,
    "shipment tracking": 35,
    "booking management": 40,
    "carrier operations": 40,
    "trade operations": 40,
    "logistica": 35,
    "magazzino": 30,
    "ai training": 40,
    "ai trainer": 40,
    "ai data annotator": 50,
    "ai annotation": 45,
    "ai annotator": 45,
    "data annotation": 40,
    "data annotator": 45,
    "data labeling": 35,
    "annotation": 35,
    "ukrainian language": 60,
    "russian language": 60,
    "ukrainian": 50,
    "russian": 50,
    "украинский": 50,
    "українська": 50,
    "русский": 50,
    "російська": 50,
    "llm": 35,
    "prompt engineering": 30,
    "prompt": 25,
    "python": 35,
    "pandas": 35,
    "automation": 35,
    "api": 20,
    "csv": 15,
    "excel": 25,
    "google sheets": 35,
    "google sheet": 30,
    "spreadsheet": 20,
    "excel reporting": 35,
    "google workspace": 30,
    "dashboard": 25,
    "kpi": 25,
    "analytics": 25,
    "monitoring": 20,
    "data entry": 25,
    "inserimento dati": 35,
    "addetto inserimento dati": 45,
    "gestione dati": 30,
    "gestione documentale": 30,
    "controllo dati": 30,
    "data quality": 35,
    "quality assurance": 30,
    "data operations": 35,
    "data processing": 30,
    "reporting analyst": 35,
    "reporting": 25,
    "operations analyst": 40,
    "workflow analyst": 35,
    "workflow management": 35,
    "process improvement": 30,
    "business operations": 30,
    "crm/data quality": 35,
    "crm data quality": 35,
    "automation support": 35,
    "data analyst": 40,
    "analyst": 15,
    "osint": 25,
    "research assistant": 30,
    "research": 15,
    "customer support": 20,
    "support": 10,
    "supporto operativo": 30,
    "supporto amministrativo": 30,
    "virtual assistant": 20,
    "admin": 10,
    "administrative": 20,
    "documentation specialist": 35,
    "document control": 35,
    "operational support": 35,
    "administrative support": 35,
    "office administration": 30,
    "secretarial": 25,
    "impiegato amministrativo": 40,
    "amministrativo": 25,
    "amministrazione": 25,
    "amministrazione operativa": 35,
    "back office": 25,
    "back office amministrativo": 40,
    "back office commerciale": 20,
    "impiegato back office": 35,
    "ufficio operativo": 30,
    "operatore segretariale": 45,
    "coordinamento operativo": 40,
    "ufficio logistico": 40,
    "spedizioni": 40,
    "trasporti": 35,
    "import export": 40,
    "ufficio acquisti": 25,
    "buyer support": 20,
    "controllo qualità": 25,
    "qualità": 15,
    "customer operations": 30,
    "operations support": 35,
    "booking specialist": 40,
    "pricing analyst": 30,
    "rate management": 35,
    "remote": 20,
    "entry level": 20,
    "junior": 20,
    # Maritime / ocean freight
    "ocean freight": 25,
    "sea freight": 25,
    "shipping documentation": 24,
    "bill of lading": 28,
    "b/l": 20,
    "port agent": 26,
    "ship agent": 26,
    "vessel agent": 26,
    "shipping agency": 22,
    "husbandry": 24,
    "import documentation": 18,
    "export documentation": 18,
    "incoterms": 15,
    "cmr": 12,
    "packing list": 12,
    "commercial invoice": 12,
    # Language skills
    "russian speaking": 18,
    "ukrainian speaking": 18,
    # Naples local
    "naples": 15,
    "napoli": 15,
    "campania": 10,
}


COMBO_WEIGHTS = [
    (["ukrainian", "remote"], 60, "ukrainian + remote"),
    (["russian", "remote"], 60, "russian + remote"),
    (["украинский", "remote"], 60, "украинский + remote"),
    (["українська", "remote"], 60, "українська + remote"),
    (["русский", "remote"], 60, "русский + remote"),
    (["російська", "remote"], 60, "російська + remote"),
    (["ukrainian", "data annotation"], 75, "ukrainian + data annotation"),
    (["russian", "data annotation"], 75, "russian + data annotation"),
    (["ukrainian", "annotation"], 60, "ukrainian + annotation"),
    (["russian", "annotation"], 60, "russian + annotation"),
    (["ukrainian", "customer support"], 50, "ukrainian + customer support"),
    (["russian", "customer support"], 50, "russian + customer support"),
    (["ukrainian", "ai"], 55, "ukrainian + ai"),
    (["russian", "ai"], 55, "russian + ai"),
    (["python", "remote"], 25, "python + remote"),
    (["google sheets", "remote"], 25, "google sheets + remote"),
    (["shipping", "analyst"], 40, "shipping + analyst"),
    (["container", "analyst"], 45, "container + analyst"),
    (["logistics", "remote"], 25, "logistics + remote"),
    (["excel", "reporting"], 25, "excel + reporting"),
    (["operations", "remote"], 20, "operations + remote"),
    (["italian", "english"], 20, "italian + english"),
    (["logistics", "data"], 35, "logistics + data"),
    (["operations", "reporting"], 30, "operations + reporting"),
    (["google sheets", "automation"], 35, "google sheets + automation"),
    (["russian", "analyst"], 45, "russian + analyst"),
    (["russian", "monitoring"], 50, "russian + monitoring"),
    (["russian", "osint"], 60, "russian + osint"),
    (["ukrainian", "analyst"], 45, "ukrainian + analyst"),
    (["ukrainian", "monitoring"], 50, "ukrainian + monitoring"),
    (["ukrainian", "osint"], 60, "ukrainian + osint"),
    (["russian", "reporting"], 45, "russian + reporting"),
    (["ukrainian", "reporting"], 45, "ukrainian + reporting"),
    (["russian", "data"], 45, "russian + data"),
    (["ukrainian", "data"], 45, "ukrainian + data"),
    (["russian", "support"], 40, "russian + support"),
    (["ukrainian", "support"], 40, "ukrainian + support"),
    (["russian", "ai annotation"], 80, "russian + ai annotation"),
    (["ukrainian", "ai annotation"], 80, "ukrainian + ai annotation"),
    (["русский", "ai"], 55, "русский + ai"),
    (["українська", "ai"], 55, "українська + ai"),
    (["русский", "annotation"], 60, "русский + annotation"),
    (["українська", "annotation"], 60, "українська + annotation"),
    (["logistics", "analyst"], 40, "logistics + analyst"),
    (["supply chain", "analytics"], 40, "supply chain + analytics"),
    (["maritime", "intelligence"], 50, "maritime + intelligence"),
    (["freight", "operations"], 40, "freight + operations"),
    (["python", "automation"], 35, "python + automation"),
    (["monitoring", "reporting"], 35, "monitoring + reporting"),
    # Maritime combos
    (["ocean freight", "documentation"], 35, "ocean freight + documentation"),
    (["sea freight", "documentation"], 35, "sea freight + documentation"),
    (["bill of lading", "export"], 30, "bill of lading + export"),
    (["bill of lading", "import"], 30, "bill of lading + import"),
    (["freight forwarding", "russian"], 30, "freight forwarding + russian"),
    (["freight forwarding", "ukrainian"], 30, "freight forwarding + ukrainian"),
    (["shipping agency", "naples"], 35, "shipping agency + naples"),
    (["ship agent", "naples"], 40, "ship agent + naples"),
    (["port agent", "naples"], 40, "port agent + naples"),
    (["vessel agent", "naples"], 40, "vessel agent + naples"),
    (["husbandry", "naples"], 35, "husbandry + naples"),
    (["port operations", "naples"], 35, "port operations + naples"),
    (["remote", "ocean freight"], 30, "remote + ocean freight"),
    (["hybrid", "ocean freight"], 20, "hybrid + ocean freight"),
]


SIGNAL_PHRASES = sorted(
    set(POSITIVE_WEIGHTS) | {phrase for phrases, _, _ in COMBO_WEIGHTS for phrase in phrases},
    key=len,
    reverse=True,
)
SIGNAL_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(phrase.lower()) for phrase in SIGNAL_PHRASES) + r")\b"
)

NEGATIVE_WEIGHTS = {
    "for hire": -100,
    "[for hire]": -100,
    "looking for work": -80,
    "open to freelance": -80,
    "i'm available": -80,
    "resume builder": -70,
    "how do i": -60,
    "what should i do": -60,
    "advice": -50,
    "warning": -60,
    "do not work": -90,
    "stuck in a remote job": -90,
    "portfolio": -40,
    "freelance": -40,
    "freelancing": -50,
    "clients": -30,
    "message me": -40,
    "dm me with": -40,
    "music": -70,
    "tutor": -60,
    "chemistry": -60,
    "chatter": -80,
    "dating": -80,
    "onlyfans": -100,
    "senior": -25,
    "lead": -20,
    "manager": -15,
    "director": -35,
    "principal": -35,
    "crypto": -50,
    "blockchain": -50,
    "web3": -50,
    "nsfw": -80,
    "adult": -80,
    "sales": -20,
    "commerciale": -20,
    "vendite": -25,
    "commessi": -50,
    "autista": -35,
    "elettricista": -35,
    "saldatore": -50,
    "montatore": -40,
    "manutentore": -40,
    "tecnologo alimentare": -40,
    "medical": -30,
    "nurse": -50,
    "pharmacist": -40,
    "machine learning engineer": -80,
    "network engineer": -80,
    "internal audit": -60,
    "pure bi analyst": -60,
    "data scientist": -70,
    "cybersecurity": -80,
    "devops": -80,
    # Physical / delivery roles to exclude
    "warehouse picker": -20,
    "forklift": -25,
    "driver": -20,
    "courier": -25,
    "truck driver": -30,
    "delivery driver": -30,
    "senior software engineer": -40,
    "full stack developer": -40,
    "chef": -40,
    "sales manager only": -20,
}


HARD_EXCLUDE_TITLE = [
    "senior",
    "director",
    "principal",
    "lead",
    "devops",
    "machine learning engineer",
    "network engineer",
    "engineering",
    "full-stack",
    "full stack",
    "react developer",
    "developer",
    "developers",
    "designer",
    "software developer",
    "software engineer",
    "engineer",
    "architect",
    "manager",
    "member of technical staff",
    "penetration tester",
    "technician",
    "sourcer",
    "founder",
    "founders associate",
    "healthcare",
    "security",
    "soc analyst",
    "internal audit",
    "pure bi analyst",
    "data scientist",
    "cybersecurity",
]


PHRASE_PATTERNS = {
    phrase: re.compile(r"\b" + re.escape(phrase.lower()) + r"\b")
    for phrase in (
        set(POSITIVE_WEIGHTS)
        | set(NEGATIVE_WEIGHTS)
        | set(HARD_EXCLUDE_TITLE)
        | {phrase for phrases, _, _ in COMBO_WEIGHTS for phrase in phrases}
    )
}


SOURCE_BONUS = {
    "remotive": 15,
    "arbeitnow": 10,
    "himalayas": 10,
    "remotejobs_org": 15,
    "remotefirstjobs": 15,
    "jobicy": 15,
    "workanywhere": 15,
    "smartjobspa": 10,
    "attalgroup": 10,
    "direzionelavoro": 10,
    "duckduckgo": 5,
    "reddit": 0,
}


MIN_SCORE_BY_SOURCE = {
    "remotefirstjobs": 120,
    "smartjobspa": 60,
    "attalgroup": 60,
    "direzionelavoro": 60,
    "duckduckgo": 25,
}


def apply_scoring_config(config):
    global OUTPUT_FILE
    global XLSX_OUTPUT_FILE
    global TOP_REPORT_LIMIT
    global TOP_OUTPUT_FILE
    global TOP_XLSX_OUTPUT_FILE
    global SEARCH_DESCRIPTION_LIMIT
    global OUTPUT_COLUMNS
    global TOP_JOBS_MIN_SCORE
    global PRIORITY_HIGH_SCORE
    global PRIORITY_MEDIUM_SCORE
    global POSITIVE_WEIGHTS
    global COMBO_WEIGHTS
    global NEGATIVE_WEIGHTS
    global HARD_EXCLUDE_TITLE
    global SOURCE_BONUS
    global MIN_SCORE_BY_SOURCE
    global SIGNAL_PHRASES
    global SIGNAL_PATTERN
    global PHRASE_PATTERNS

    export = config.get("export", {})
    OUTPUT_FILE = export.get("output_file", OUTPUT_FILE)
    XLSX_OUTPUT_FILE = export.get("xlsx_output_file", XLSX_OUTPUT_FILE)
    TOP_REPORT_LIMIT = export.get("top_report_limit", TOP_REPORT_LIMIT)
    TOP_OUTPUT_FILE = export.get("top_output_file", TOP_OUTPUT_FILE)
    TOP_XLSX_OUTPUT_FILE = export.get("top_xlsx_output_file", TOP_XLSX_OUTPUT_FILE)
    SEARCH_DESCRIPTION_LIMIT = export.get("search_description_limit", SEARCH_DESCRIPTION_LIMIT)
    OUTPUT_COLUMNS = export.get("output_columns", OUTPUT_COLUMNS)
    TOP_JOBS_MIN_SCORE = export.get("top_jobs_min_score", TOP_JOBS_MIN_SCORE)

    priority = config.get("priority", {})
    PRIORITY_HIGH_SCORE = priority.get("high_score", PRIORITY_HIGH_SCORE)
    PRIORITY_MEDIUM_SCORE = priority.get("medium_score", PRIORITY_MEDIUM_SCORE)

    POSITIVE_WEIGHTS = config.get("positive_weights", POSITIVE_WEIGHTS)
    NEGATIVE_WEIGHTS = config.get("negative_weights", NEGATIVE_WEIGHTS)
    HARD_EXCLUDE_TITLE = config.get("hard_exclude_title", HARD_EXCLUDE_TITLE)
    SOURCE_BONUS = config.get("source_bonus", SOURCE_BONUS)
    MIN_SCORE_BY_SOURCE = config.get("min_score_by_source", MIN_SCORE_BY_SOURCE)
    COMBO_WEIGHTS = [
        (item["phrases"], item["points"], item["reason"])
        for item in config.get("combo_weights", [
            {"phrases": phrases, "points": points, "reason": reason}
            for phrases, points, reason in COMBO_WEIGHTS
        ])
    ]

    SIGNAL_PHRASES = sorted(
        set(POSITIVE_WEIGHTS) | {phrase for phrases, _, _ in COMBO_WEIGHTS for phrase in phrases},
        key=len,
        reverse=True,
    )
    SIGNAL_PATTERN = re.compile(
        r"\b(?:" + "|".join(re.escape(phrase.lower()) for phrase in SIGNAL_PHRASES) + r")\b"
    )
    PHRASE_PATTERNS = {
        phrase: re.compile(r"\b" + re.escape(phrase.lower()) + r"\b")
        for phrase in (
            set(POSITIVE_WEIGHTS)
            | set(NEGATIVE_WEIGHTS)
            | set(HARD_EXCLUDE_TITLE)
            | {phrase for phrases, _, _ in COMBO_WEIGHTS for phrase in phrases}
        )
    }


def phrase_matches(text, phrase):
    if phrase not in text:
        return False
    return PHRASE_PATTERNS[phrase].search(text) is not None


def normalize_text(value):
    return " ".join(str(value or "").lower().split())


def row_text(row):
    return normalize_text(" ".join([
        str(row.get("title", "") or ""),
        str(row.get("company", "") or ""),
        str(row.get("location", "") or ""),
        str(row.get("description", "") or ""),
        str(row.get("category", "") or ""),
        str(row.get("query", "") or ""),
    ]))


def contains_any(text, terms):
    return any(term in text for term in terms)


def detect_remote_category(row):
    text = row_text(row)
    for category, terms in REMOTE_CATEGORY_RULES:
        if contains_any(text, terms):
            return category
    return "Other"


def detect_country_restriction(row):
    text = row_text(row)
    location = normalize_text(row.get("location", ""))
    for restriction, terms in COUNTRY_RESTRICTION_RULES:
        if contains_any(text, terms) or contains_any(location, terms):
            return restriction
    if location in {"remote", "worldwide", "anywhere"}:
        return "Worldwide"
    return ""


def normalize_employment_type(row):
    text = row_text(row)
    for employment_type, terms in EMPLOYMENT_TYPE_RULES:
        if contains_any(text, terms):
            return employment_type
    existing = str(row.get("employment_type") or row.get("job_type") or "").strip()
    return existing


def parse_money(value):
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "").replace(" ", "")))
    except ValueError:
        return None


def extract_salary(row):
    existing_text = str(row.get("salary_text") or row.get("salary") or "")
    existing_min = parse_money(row.get("salary_min"))
    existing_max = parse_money(row.get("salary_max"))
    currency = str(row.get("currency") or "").strip()
    if existing_min or existing_max:
        return {
            "salary_min": existing_min or "",
            "salary_max": existing_max or existing_min or "",
            "currency": currency,
            "salary_text": existing_text,
        }

    text = row_text(row)
    salary_match = re.search(
        r"(?P<currency>€|\$|£|eur|usd|gbp)\s*(?P<min>\d[\d,\. ]{2,})(?:\s*(?:-|–|to|/)\s*(?:€|\$|£|eur|usd|gbp)?\s*(?P<max>\d[\d,\. ]{2,}))?",
        text,
        re.IGNORECASE,
    )
    if not salary_match:
        return {"salary_min": "", "salary_max": "", "currency": currency, "salary_text": existing_text}
    raw_currency = salary_match.group("currency")
    currency_map = {"€": "EUR", "$": "USD", "£": "GBP", "eur": "EUR", "usd": "USD", "gbp": "GBP"}
    salary_min = parse_money(salary_match.group("min"))
    salary_max = parse_money(salary_match.group("max")) or salary_min
    salary_text = existing_text or salary_match.group(0)
    return {
        "salary_min": salary_min or "",
        "salary_max": salary_max or "",
        "currency": currency_map.get(raw_currency.lower(), raw_currency.upper()),
        "salary_text": salary_text,
    }


def remote_quality_signals(row):
    text = row_text(row)
    score_delta = 0
    positive = []
    negative = []

    for label, terms, points in REMOTE_POSITIVE_RULES:
        matched = [term for term in terms if term in text]
        if matched:
            score_delta += points
            positive.append(f"+{points} {label}: {', '.join(matched[:3])}")

    country = detect_country_restriction(row)
    country_points = COUNTRY_SCORE_WEIGHTS.get(country, 0)
    if country_points:
        score_delta += country_points
        reason = f"{country_points:+d} country: {country}"
        if country_points > 0:
            positive.append(reason)
        else:
            negative.append(reason)

    salary = extract_salary(row)
    if salary.get("salary_min"):
        score_delta += 5
        positive.append("+5 salary present")

    for label, terms, points in REMOTE_NEGATIVE_RULES:
        matched = [term for term in terms if term in text]
        if matched:
            score_delta += points
            negative.append(f"{points} {label}: {', '.join(matched[:3])}")

    return {
        "remote_score_delta": score_delta,
        "normalized_remote_category": detect_remote_category(row),
        "country_restriction": country,
        "employment_type": normalize_employment_type(row),
        "salary_min": salary["salary_min"],
        "salary_max": salary["salary_max"],
        "currency": salary["currency"],
        "salary_text": salary["salary_text"],
        "positive_reason": "; ".join(positive),
        "negative_reason": "; ".join(negative),
    }


def enrich_remote_quality(row):
    enriched = dict(row)
    enriched.update(remote_quality_signals(enriched))
    return enriched


def has_signal_phrase(text):
    return any(phrase_matches(text, phrase) for phrase in SIGNAL_PHRASES)


def read_csv(path):
    if not Path(path).exists():
        print(f"Skipped missing file: {path}")
        return pd.DataFrame()

    try:
        set_csv_field_limit()
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        print(f"Skipped empty file: {path}")
        return pd.DataFrame()

    if df.empty:
        print(f"Skipped empty file: {path}")
    return df


def text_column(df, name, limit=None):
    if name not in df:
        return pd.Series("", index=df.index)

    column = df[name].fillna("").astype(str)
    if limit is not None:
        column = column.str.slice(0, limit)
    return column


def normalize_reddit():
    df = read_csv("filtered_jobs.csv")
    if df.empty:
        return df

    normalized = pd.DataFrame({
        "source": "reddit",
        "title": df.get("title", ""),
        "company": df.get("subreddit", ""),
        "location": "remote",
        "url": df.get("url", ""),
        "description": text_column(df, "selftext", SEARCH_DESCRIPTION_LIMIT),
        "source_score": df.get("score", 0),
    })
    return normalized


def normalize_remotive():
    df = read_csv("remotive_jobs.csv")
    if df.empty:
        return df

    normalized = pd.DataFrame({
        "source": "remotive",
        "title": df.get("title", ""),
        "company": df.get("company_name", ""),
        "location": df.get("candidate_required_location", ""),
        "url": df.get("url", ""),
        "description": text_column(df, "description", SEARCH_DESCRIPTION_LIMIT),
        "source_score": 0,
    })
    return normalized


def normalize_arbeitnow():
    df = read_csv("arbeitnow_jobs.csv")
    if df.empty:
        return df

    normalized = pd.DataFrame({
        "source": "arbeitnow",
        "title": df.get("title", ""),
        "company": df.get("company", ""),
        "location": df.get("location", ""),
        "url": df.get("url", ""),
        "description": text_column(df, "description", SEARCH_DESCRIPTION_LIMIT),
        "source_score": 0,
    })
    return normalized


def normalize_himalayas():
    df = read_csv("filtered_himalayas_jobs.csv")
    if df.empty:
        return df

    normalized = pd.DataFrame({
        "source": "himalayas",
        "title": df.get("title", ""),
        "company": df.get("company", ""),
        "location": df.get("location", ""),
        "url": df.get("url", ""),
        "description": text_column(df, "description", SEARCH_DESCRIPTION_LIMIT),
        "source_score": 0,
    })
    return normalized


def normalize_remotejobs_org():
    df = read_csv("remotejobs_org_jobs.csv")
    if df.empty:
        return df

    normalized = pd.DataFrame({
        "source": "remotejobs_org",
        "title": df.get("title", ""),
        "company": df.get("company", ""),
        "location": df.get("location", ""),
        "url": df.get("url", ""),
        "description": text_column(df, "description", SEARCH_DESCRIPTION_LIMIT),
        "source_score": 0,
    })
    return normalized


def normalize_jobicy():
    df = read_csv("jobicy_jobs.csv")
    if df.empty:
        return df

    normalized = pd.DataFrame({
        "source": "jobicy",
        "title": df.get("title", ""),
        "company": df.get("company", ""),
        "location": df.get("location", ""),
        "url": df.get("url", ""),
        "description": text_column(df, "description", SEARCH_DESCRIPTION_LIMIT),
        "source_score": 0,
    })
    return normalized


def normalize_remotefirstjobs():
    df = read_csv("remotefirstjobs_jobs.csv")
    if df.empty:
        return df

    normalized = pd.DataFrame({
        "source": "remotefirstjobs",
        "title": df.get("title", ""),
        "company": df.get("company", ""),
        "location": df.get("location", ""),
        "url": df.get("url", ""),
        "description": (
            text_column(df, "query") + " " +
            text_column(df, "description", SEARCH_DESCRIPTION_LIMIT)
        ),
        "source_score": 0,
    })
    return normalized


def normalize_workanywhere():
    df = read_csv("workanywhere_jobs.csv")
    if df.empty:
        return df

    normalized = pd.DataFrame({
        "source": "workanywhere",
        "title": df.get("title", ""),
        "company": df.get("company", ""),
        "location": df.get("location", ""),
        "url": df.get("url", ""),
        "description": text_column(df, "description", SEARCH_DESCRIPTION_LIMIT),
        "source_score": 0,
    })
    return normalized


def normalize_arca24(path, source):
    df = read_csv(path)
    if df.empty:
        return df

    normalized = pd.DataFrame({
        "source": source,
        "title": df.get("title", ""),
        "company": df.get("company", ""),
        "location": df.get("location", ""),
        "url": df.get("url", ""),
        "description": (
            text_column(df, "sector") + " " +
            text_column(df, "role") + " " +
            text_column(df, "contract") + " " +
            text_column(df, "description", SEARCH_DESCRIPTION_LIMIT)
        ),
        "source_score": 0,
    })
    return normalized


def normalize_smartjobspa():
    return normalize_arca24("smartjobspa_jobs.csv", "smartjobspa")


def normalize_attalgroup():
    return normalize_arca24("attalgroup_jobs.csv", "attalgroup")


def normalize_direzionelavoro():
    return normalize_arca24("direzionelavoro_jobs.csv", "direzionelavoro")


def normalize_duckduckgo():
    df = read_csv("duckduckgo_jobs.csv")
    if df.empty:
        return df

    normalized = pd.DataFrame({
        "source": "duckduckgo",
        "title": df.get("title", ""),
        "company": df.get("company", ""),
        "location": df.get("location", "Italy"),
        "url": df.get("url", ""),
        "description": text_column(df, "description", SEARCH_DESCRIPTION_LIMIT),
        "source_score": 0,
    })
    return normalized


def calculate_score(row):
    title_text = str(row.get("title", "")).lower()
    text = (
        title_text + " " +
        str(row.get("company", "")) + " " +
        str(row.get("location", "")) + " " +
        str(row.get("description", ""))
    ).lower()

    hard_exclusions = [
        phrase for phrase in HARD_EXCLUDE_TITLE
        if phrase_matches(title_text, phrase)
    ]
    if hard_exclusions:
        quality = remote_quality_signals(row)
        return pd.Series({
            "job_score": -100,
            "score_reason": "excluded title: " + ", ".join(hard_exclusions),
            "positive_reason": quality["positive_reason"],
            "negative_reason": "excluded title: " + ", ".join(hard_exclusions),
        })

    score = SOURCE_BONUS.get(row.get("source"), 0)
    reasons = []
    positive_reasons = []
    negative_reasons = []
    matched_signals = set()

    def add_signal(signal_id, points, reason):
        nonlocal score
        if signal_id in matched_signals:
            return
        matched_signals.add(signal_id)
        score += points
        reasons.append(reason)
        if points >= 0:
            positive_reasons.append(reason)
        else:
            negative_reasons.append(reason)

    for phrase, points in POSITIVE_WEIGHTS.items():
        if phrase_matches(text, phrase):
            add_signal(f"positive:{phrase}", points, f"+{points} {phrase}")

    for phrases, points, reason in COMBO_WEIGHTS:
        if all(phrase_matches(text, phrase) for phrase in phrases):
            signal_key = "combo:" + "|".join(phrases) + ":" + reason
            add_signal(signal_key, points, f"+{points} {reason}")

    for phrase, points in NEGATIVE_WEIGHTS.items():
        if phrase_matches(text, phrase):
            add_signal(f"negative:{phrase}", points, f"{points} {phrase}")

    quality = remote_quality_signals(row)
    score += int(quality["remote_score_delta"] or 0)
    if quality["positive_reason"]:
        positive_reasons.append(quality["positive_reason"])
    if quality["negative_reason"]:
        negative_reasons.append(quality["negative_reason"])

    all_reasons = reasons + [
        reason
        for reason in [quality["positive_reason"], quality["negative_reason"]]
        if reason
    ]
    return pd.Series({
        "job_score": score,
        "score_reason": ", ".join(all_reasons),
        "positive_reason": "; ".join(positive_reasons),
        "negative_reason": "; ".join(negative_reasons),
    })


def column_name(index):
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def write_xlsx_with_links(df, path, columns, link_column, sheet_name="scored_jobs"):
    link_index = columns.index(link_column) + 1

    rows_xml = []
    sheet_rows = [columns] + list(df[columns].itertuples(index=False, name=None))
    for row_number, row in enumerate(sheet_rows, start=1):
        cells = []
        for column_number, value in enumerate(row, start=1):
            cell_ref = f"{column_name(column_number)}{row_number}"
            text = "" if pd.isna(value) else str(value)
            style = ' s="1"' if column_number == link_index and row_number > 1 else ""
            cells.append(
                f'<c r="{cell_ref}" t="inlineStr"{style}>'
                f"<is><t>{escape(text)}</t></is></c>"
            )
        rows_xml.append(f'<row r="{row_number}">{"".join(cells)}</row>')

    hyperlinks = []
    relationships = []
    for row_number, url in enumerate(df["url"].fillna("").astype(str), start=2):
        if not url:
            continue
        rel_id = f"rId{row_number - 1}"
        cell_ref = f"{column_name(link_index)}{row_number}"
        hyperlinks.append(f'<hyperlink ref="{cell_ref}" r:id="{rel_id}"/>')
        relationships.append(
            f'<Relationship Id="{rel_id}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
            f'Target="{escape(url)}" TargetMode="External"/>'
        )

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheetData>{"".join(rows_xml)}</sheetData>'
        f'<hyperlinks>{"".join(hyperlinks)}</hyperlinks>'
        "</worksheet>"
    )

    sheet_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{"".join(relationships)}'
        "</Relationships>"
    )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )

    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )

    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        "</Relationships>"
    )

    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
        '<font><u/><color rgb="FF0563C1"/><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2"><xf fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
        "</styleSheet>"
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as xlsx:
        xlsx.writestr("[Content_Types].xml", content_types_xml)
        xlsx.writestr("_rels/.rels", root_rels_xml)
        xlsx.writestr("xl/workbook.xml", workbook_xml)
        xlsx.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        xlsx.writestr("xl/styles.xml", styles_xml)
        xlsx.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        xlsx.writestr("xl/worksheets/_rels/sheet1.xml.rels", sheet_rels_xml)


def export_report(df, csv_path, xlsx_path, sheet_name):
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    Path(xlsx_path).parent.mkdir(parents=True, exist_ok=True)
    report_df = df.reindex(columns=OUTPUT_COLUMNS)
    report_df.to_csv(csv_path, index=False)
    print(f"Saved {csv_path}")
    write_xlsx_with_links(report_df, xlsx_path, OUTPUT_COLUMNS, "clickable", sheet_name)
    print(f"Saved {xlsx_path}")


def apply_priority(score):
    if score >= PRIORITY_HIGH_SCORE:
        return "HIGH"
    if score >= PRIORITY_MEDIUM_SCORE:
        return "MEDIUM"
    return "LOW"


def top_score_stats(top_df):
    if top_df.empty:
        return {"min": 0, "max": 0, "average": 0}
    scores = top_df["job_score"]
    return {
        "min": int(scores.min()),
        "max": int(scores.max()),
        "average": round(float(scores.mean()), 2),
    }


def score_jobs(
    scoring_file=DEFAULT_SCORING_FILE,
    csv_path=None,
    xlsx_path=None,
    top_csv_path=None,
    top_xlsx_path=None,
):
    apply_scoring_config(load_scoring_config(scoring_file))

    frames = [
        normalize_reddit(),
        normalize_remotive(),
        normalize_arbeitnow(),
        normalize_himalayas(),
        normalize_remotejobs_org(),
        normalize_remotefirstjobs(),
        normalize_jobicy(),
        normalize_workanywhere(),
        normalize_smartjobspa(),
        normalize_attalgroup(),
        normalize_direzionelavoro(),
        normalize_duckduckgo(),
    ]

    df = pd.concat([frame for frame in frames if not frame.empty], ignore_index=True)
    source_counts = {}
    if not df.empty:
        source_counts = df["source"].value_counts().sort_index().to_dict()
    collected = len(df)

    csv_path = csv_path or OUTPUT_FILE
    xlsx_path = xlsx_path or XLSX_OUTPUT_FILE
    top_csv_path = top_csv_path or TOP_OUTPUT_FILE
    top_xlsx_path = top_xlsx_path or TOP_XLSX_OUTPUT_FILE

    if df.empty:
        print("No jobs found to score.")
        empty_df = pd.DataFrame(columns=OUTPUT_COLUMNS)
        export_report(empty_df, csv_path, xlsx_path, "scored_jobs")
        export_report(empty_df, top_csv_path, top_xlsx_path, "top_50_jobs")
        return {
            "source_counts": source_counts,
            "collected": 0,
            "after_deduplication": 0,
            "after_filtering": 0,
            "after_scoring_threshold": 0,
            "after_scoring": 0,
            "top_jobs_emailed": 0,
            "priority_counts": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
            "top_jobs_score_stats": {"min": 0, "max": 0, "average": 0},
            "scored_jobs": empty_df,
            "top_jobs": empty_df,
            "output_columns": OUTPUT_COLUMNS,
        }

    df = df.drop_duplicates(subset=["url"], keep="first")
    df = df.drop_duplicates(subset=["source", "title", "company"], keep="first")
    after_deduplication = len(df)
    quality_rows = df.apply(lambda row: pd.Series(remote_quality_signals(row)), axis=1)
    for column in quality_rows.columns:
        df[column] = quality_rows[column]
    signal_text = (
        df["title"].fillna("").astype(str) + " " +
        df["company"].fillna("").astype(str) + " " +
        df["location"].fillna("").astype(str) + " " +
        df["description"].fillna("").astype(str)
    ).str.lower()
    df = df[
        signal_text.apply(has_signal_phrase)
        | (df["normalized_remote_category"].fillna("") != "Other")
    ]
    after_filtering = len(df)
    df[["job_score", "score_reason"]] = df.apply(calculate_score, axis=1)
    df = df[
        df.apply(
            lambda row: row["job_score"] >= MIN_SCORE_BY_SOURCE.get(
                row["source"],
                45,
            ),
            axis=1,
        )
    ]
    df = df.sort_values(by="job_score", ascending=False)
    df["apply_priority"] = df["job_score"].apply(apply_priority)
    df["clickable"] = "Open"
    top_df = df[df["job_score"] >= TOP_JOBS_MIN_SCORE].head(TOP_REPORT_LIMIT)
    priority_counts = (
        top_df["apply_priority"]
        .value_counts()
        .reindex(["HIGH", "MEDIUM", "LOW"], fill_value=0)
        .to_dict()
    )
    score_stats = top_score_stats(top_df)

    print("Scored jobs:", len(df))
    print(df[OUTPUT_COLUMNS].head(30).to_string(index=False))

    export_report(df, csv_path, xlsx_path, "scored_jobs")
    export_report(top_df, top_csv_path, top_xlsx_path, "top_50_jobs")

    return {
        "source_counts": source_counts,
        "collected": collected,
        "after_deduplication": after_deduplication,
        "after_filtering": after_filtering,
        "after_scoring_threshold": len(df),
        "after_scoring": len(df),
        "top_jobs_emailed": min(len(top_df), 20),
        "priority_counts": priority_counts,
        "top_jobs_score_stats": score_stats,
        "scored_jobs": df,
        "top_jobs": top_df,
        "output_columns": OUTPUT_COLUMNS,
    }


def main():
    score_jobs()


if __name__ == "__main__":
    main()
