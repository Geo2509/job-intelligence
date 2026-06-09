import pandas as pd
import re

from config_loader import load_scoring_config


_FILTER_CONFIG = load_scoring_config().get("filters", {}).get("reddit", {})

INPUT_COLUMNS = ["source", "subreddit", "title", "author", "score", "created_utc", "url", "selftext"]

try:
    df = pd.read_csv("reddit_jobs.csv")
except pd.errors.EmptyDataError:
    df = pd.DataFrame(columns=INPUT_COLUMNS)

for column in INPUT_COLUMNS:
    if column not in df:
        df[column] = ""

KEYWORDS = _FILTER_CONFIG.get("keywords", [
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
    "remote",
    "support",
    "analyst",
    "entry",
    "assistant",
    "admin",
    "virtual assistant",
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
])

HIRING_KEYWORDS = _FILTER_CONFIG.get("hiring_keywords", [
    "hiring",
    "[hiring]",
    "job",
    "jobs",
    "opening",
    "role",
    "position",
    "vacancy",
    "we are looking",
    "apply",
])

EXCLUDED = _FILTER_CONFIG.get("excluded", [
    "senior",
    "blockchain",
    "crypto",
    "machine learning engineer",
    "network engineer",
    "internal audit",
    "pure bi analyst",
    "data scientist",
    "cybersecurity",
    "devops",
    "nsfw",
    "onlyfans",
    "adult",
    "web3",
    "for hire",
    "[for hire]",
    "looking for work",
    "open to freelance",
    "available for",
    "resume builder",
    "how do i",
    "what should i do",
    "any recommendations",
    "advice",
    "warning",
    "do not work",
    "stuck in a remote job",
    "microphone recommendations",
    "workstation check",
    "doom scrolling",
    "grocery haul",
    "tutor",
    "chemistry",
    "music tutor",
])


def has_phrase(text, phrases):
    text = str(text).lower()

    for phrase in phrases:
        if re.search(r"\b" + re.escape(phrase.lower()) + r"\b", text):
            return True

    return False


def check_keywords(text):
    return has_phrase(text, KEYWORDS)


def check_hiring(text):
    return has_phrase(text, HIRING_KEYWORDS)


def check_excluded(text):
    return has_phrase(text, EXCLUDED)


df["search_text"] = (
    df["title"].fillna("") + " " + df["selftext"].fillna("")
)

df["match"] = df["search_text"].apply(check_keywords)
df["hiring_match"] = df["search_text"].apply(check_hiring)
df["excluded"] = df["search_text"].apply(check_excluded)

filtered = df[
    (df["match"] == True) &
    (df["hiring_match"] == True) &
    (df["excluded"] == False)
]

print("Original posts:", len(df))
print("Filtered posts:", len(filtered))

print(filtered[["subreddit", "title", "score", "url"]].head(20))

filtered.to_csv("filtered_jobs.csv", index=False)

print("Saved filtered_jobs.csv")
