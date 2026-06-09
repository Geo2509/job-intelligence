import pandas as pd
import re

from config_loader import load_scoring_config


_FILTER_CONFIG = load_scoring_config().get("filters", {}).get("himalayas", {})

df = pd.read_csv("himalayas_jobs.csv")


GOOD_KEYWORDS = _FILTER_CONFIG.get("good_keywords", [
    "shipping coordinator",
    "freight coordinator",
    "booking coordinator",
    "ocean freight coordinator",
    "logistics operations",
    "freight operations",
    "container booking",
    "shipment coordinator",
    "operations coordinator",
    "workflow automation",
    "shipping line",
    "carrier coordination",
    "local agent coordination",
    "port operations",
    "container shipping",
    "ocean export",
    "ocean import",
    "freight forwarding",
    "maritime logistics",
    "international logistics",
    "china logistics",
    "asia logistics",
    "cargo operations",
    "python",
    "data",
    "excel",
    "google sheets",
    "support",
    "analyst",
    "research",
    "annotation",
    "data annotation",
    "data annotator",
    "data operations",
    "reporting analyst",
    "operations analyst",
    "workflow analyst",
    "business operations",
    "crm/data quality",
    "crm data quality",
    "automation support",
    "ai data annotator",
    "ai annotation",
    "ai annotator",
    "ukrainian",
    "ukrainian language",
    "russian",
    "russian language",
    "украинский",
    "українська",
    "русский",
    "російська",
    "ai",
    "assistant",
    "admin",
    "customer support",
    "virtual assistant",
    "automation",
    "entry",
    "junior",
])


STRONG_KEYWORDS = _FILTER_CONFIG.get("strong_keywords", [
    "shipping coordinator",
    "freight coordinator",
    "booking coordinator",
    "ocean freight coordinator",
    "logistics operations",
    "freight operations",
    "container booking",
    "shipment coordinator",
    "operations coordinator",
    "workflow automation",
    "shipping line",
    "carrier coordination",
    "local agent coordination",
    "port operations",
    "container shipping",
    "ocean export",
    "ocean import",
    "freight forwarding",
    "maritime logistics",
    "international logistics",
    "china logistics",
    "asia logistics",
    "cargo operations",
    "data operations",
    "operations analyst",
    "reporting analyst",
    "workflow analyst",
    "business operations",
    "crm/data quality",
    "crm data quality",
    "automation support",
    "customer support",
    "data annotation",
    "data annotator",
    "ai data annotator",
    "ai annotation",
    "ai annotator",
    "linguistic ai",
    "ai auditor",
    "ukrainian",
    "ukrainian language",
    "russian",
    "russian language",
    "украинский",
    "українська",
    "русский",
    "російська",
])


BAD_KEYWORDS = _FILTER_CONFIG.get("bad_keywords", [
    "senior",
    "director",
    "vp",
    "principal",
    "manager",
    "cybersecurity",
    "pharmacist",
    "nurse",
    "salesforce",
    "supplier quality",
    "siteops",
    "inpatient coder",
    "software engineer",
    "developer",
    "devops",
    "machine learning engineer",
    "network engineer",
    "internal audit",
    "pure bi analyst",
    "data scientist",
    "sales",
    "medical",
    "relocation",
    "physiotherapist",
    "therapist",
    "head of supply chain",
    "investment banking",
    "rust engineer",
    "data architect",
    "dba",
    "team lead",
])


EUROPE_LOCATIONS = _FILTER_CONFIG.get("europe_locations", [
    "italy",
    "spain",
    "poland",
    "greece",
    "portugal",
    "europe",
    "remote",
    "worldwide",
    "emea",
])


def has_phrase(text, phrases):
    text = str(text).lower()

    for phrase in phrases:
        if re.search(r"\b" + re.escape(phrase.lower()) + r"\b", text):
            return True

    return False


def contains_good(text):
    return has_phrase(text, GOOD_KEYWORDS)


def contains_strong(text):
    return has_phrase(text, STRONG_KEYWORDS)


def contains_bad(text):
    return has_phrase(text, BAD_KEYWORDS)


def europe_check(text):
    return has_phrase(text, EUROPE_LOCATIONS)


df["search_text"] = (
    df["title"].fillna("") + " " +
    df["description"].fillna("")
)

df["good_match"] = df["search_text"].apply(contains_good)

df["strong_match"] = df["search_text"].apply(contains_strong)

df["bad_match"] = df["search_text"].apply(contains_bad)

df["europe_match"] = df["location"].apply(europe_check)

filtered = df[
    (
        (df["good_match"] == True) |
        (df["strong_match"] == True)
    ) &
    (df["bad_match"] == False) &
    (df["europe_match"] == True)
]

print("Original jobs:", len(df))
print("Filtered jobs:", len(filtered))

print(
    filtered[
        ["title", "company", "location"]
    ].head(30)
)

filtered.to_csv("filtered_himalayas_jobs.csv", index=False)

print("Saved filtered_himalayas_jobs.csv")
