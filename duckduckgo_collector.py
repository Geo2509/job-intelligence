import time
from urllib.parse import parse_qs, unquote, urlparse

import pandas as pd
from ddgs import DDGS

from config_loader import load_queries_config
from job_queries import MARITIME_QUERIES, NAPLES_MARITIME_COMPANY_QUERIES


_QUERY_CONFIG = load_queries_config().get("duckduckgo", {})
OUTPUT_FILE = "duckduckgo_jobs.csv"
MAX_RESULTS_PER_QUERY = _QUERY_CONFIG.get("max_results_per_query", 25)

BASE_ITALY_DDG_QUERIES = _QUERY_CONFIG.get("base_italy", [
    '"impiegato import export" Napoli lavoro',
    '"back office commerciale" Napoli lavoro',
    '"impiegato amministrativo" Napoli lavoro',
    '"data entry" remoto Italia',
    '"virtual assistant" remote Italy',
    '"google sheets" remote job Italy',
    '"freight forwarding" Italy job',
    '"sea freight" Italy job',
    '"ocean freight" Italy job',
    '"shipping documentation" Italy job',
    '"shipping agency" Napoli lavoro',
    '"port agent" Napoli lavoro',
    '"vessel agent" Napoli lavoro',
    '"russian speaking" logistics Italy job',
    '"ukrainian speaking" logistics Italy job',
    '"import export specialist" Italy job',
    '"logistics coordinator" Italy remote',
    'site:it.indeed.com "import export" Napoli',
    'site:infojobs.it "import export" Napoli',
    'site:linkedin.com/jobs "freight forwarding" Italy',
    'site:linkedin.com/jobs "russian speaking" Italy job',
])

REMOTE_DATA_DDG_QUERIES = _QUERY_CONFIG.get("remote_data", [
    '"data annotation" remote job',
    '"data annotator" remote job',
    '"ai data annotator" remote job',
    '"ai annotation" remote job',
    '"ai annotator" remote job',
    '"ai training" remote job',
    '"ai trainer" remote job',
    '"data annotation" remote Italy',
    '"data annotator" remote Italy',
    '"ai data annotator" remote Italy',
    '"russian" "data annotation" remote',
    '"ukrainian" "data annotation" remote',
    '"russian language" "data annotator" remote',
    '"ukrainian language" "data annotator" remote',
    '"data analyst" remote Italy',
    '"data operations" remote job',
    '"reporting analyst" remote job',
    '"operations analyst" remote job',
    '"workflow analyst" remote job',
    '"business operations" remote job',
    '"data quality analyst" remote job',
    '"crm data quality" remote job',
    '"research assistant" remote job',
    '"customer support" remote Italy',
    '"virtual assistant" remote job',
    '"administrative support" remote Italy',
    '"automation support" remote job',
    '"workflow automation" remote job',
    '"google sheets" remote job',
    '"google sheets" "data entry" remote',
    '"google sheets" "virtual assistant" remote',
    '"google workspace" remote job',
    '"excel" "data entry" remote',
    '"excel reporting" remote job',
    '"spreadsheet" remote job',
    '"spreadsheet" "operations" remote',
    '"python" "automation" remote job',
    '"pandas" "data" remote job',
])

JOB_BOARD_DDG_QUERIES = _QUERY_CONFIG.get("job_board", [
    'site:himalayas.app/jobs "data analyst" remote',
    'site:himalayas.app/jobs "data annotation" remote',
    'site:himalayas.app/jobs "operations analyst" remote',
    'site:remotive.com/remote-jobs "data analyst"',
    'site:remotive.com/remote-jobs "data entry"',
    'site:remotejobs.org "data analyst"',
    'site:remotejobs.org "data entry"',
    'site:jobicy.com/jobs "data analyst"',
    'site:jobicy.com/jobs "data entry"',
    'site:workanywhere.pro/jobs "data analyst"',
    'site:workanywhere.pro/jobs "data entry"',
    'site:workanywhere.pro/jobs "google sheets"',
    'site:linkedin.com/jobs "data annotator" remote',
    'site:linkedin.com/jobs "data analyst" remote Italy',
    'site:linkedin.com/jobs "google sheets" remote',
    'site:it.indeed.com "data entry" remoto',
    'site:it.indeed.com "data analyst" remoto',
    'site:infojobs.it "data entry" remoto',
    'site:infojobs.it "impiegato amministrativo" Napoli',
])

REMOTE_FIRST_STYLE_DDG_QUERIES = [
    f'"{query}" remote job'
    for query in _QUERY_CONFIG.get("remote_first_terms", [
        "data annotation",
        "data annotator",
        "ai data annotator",
        "ai annotation",
        "ai training",
        "ai trainer",
        "russian remote",
        "ukrainian remote",
        "customer support",
        "virtual assistant",
        "research assistant",
        "data analyst",
        "data operations",
        "reporting analyst",
        "operations analyst",
        "workflow analyst",
        "business operations",
        "automation support",
        "workflow automation",
        "shipping coordinator",
        "freight coordinator",
        "booking coordinator",
        "ocean freight coordinator",
        "logistics operations",
        "freight operations",
        "container booking",
        "shipment coordinator",
        "operations coordinator",
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
        "cargo operations",
    ])
]

MARITIME_DDG_QUERIES = [
    f'"{query}" Italy job'
    for query in MARITIME_QUERIES
] + [
    f'"{query}"'
    for query in NAPLES_MARITIME_COMPANY_QUERIES
]

ITALY_DDG_QUERIES = list(dict.fromkeys(
    BASE_ITALY_DDG_QUERIES
    + REMOTE_DATA_DDG_QUERIES
    + JOB_BOARD_DDG_QUERIES
    + REMOTE_FIRST_STYLE_DDG_QUERIES
    + MARITIME_DDG_QUERIES
))

BAD_DOMAINS = _QUERY_CONFIG.get("bad_domains", [
    "facebook.com",
    "instagram.com",
    "pinterest.",
    "youtube.com",
    "tiktok.com",
    "reddit.com",
    "amazon.",
    "wikipedia.org",
])

GOOD_DOMAINS = _QUERY_CONFIG.get("good_domains", [
    "indeed.",
    "infojobs.",
    "linkedin.com/jobs",
    "jooble.",
    "talent.com",
    "glassdoor.",
    "monster.",
    "azienda",
    "careers",
    "lavora-con-noi",
])

COLUMNS = ["source", "title", "company", "location", "url", "description"]


def normalize_url(url):
    if not url:
        return ""

    url = str(url).strip()
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    redirect_url = query_params.get("uddg") or query_params.get("url")
    if redirect_url:
        url = unquote(redirect_url[0])

    return url.strip()


def is_bad_url(url):
    parsed = urlparse(url)
    searchable = f"{parsed.netloc}{parsed.path}".lower()
    return any(domain in searchable for domain in BAD_DOMAINS)


def is_preferred_url(url):
    searchable = url.lower()
    return any(domain in searchable for domain in GOOD_DOMAINS)


def result_url(result):
    return normalize_url(
        result.get("href")
        or result.get("url")
        or result.get("link")
        or result.get("source")
    )


def collect_duckduckgo_jobs(queries=None, max_results=MAX_RESULTS_PER_QUERY):
    queries = queries or ITALY_DDG_QUERIES
    jobs = []
    seen_urls = set()

    with DDGS() as ddgs:
        for query in queries:
            print(f"Searching DuckDuckGo: {query}")
            try:
                results = ddgs.text(
                    query,
                    region="it-it",
                    safesearch="moderate",
                    max_results=max_results,
                )
            except Exception as exc:
                print(f"DuckDuckGo query failed: {query} | {exc}")
                time.sleep(2)
                continue

            count = 0
            for result in results or []:
                url = result_url(result)
                if not url or url in seen_urls or is_bad_url(url):
                    continue

                seen_urls.add(url)
                title = result.get("title") or ""
                description = result.get("body") or result.get("snippet") or ""
                if is_preferred_url(url):
                    description = f"{description} preferred_domain".strip()

                jobs.append({
                    "source": "duckduckgo",
                    "title": title,
                    "company": "",
                    "location": "Italy",
                    "url": url,
                    "description": description,
                })
                count += 1

            print(f"Accepted results: {count}")
            time.sleep(2)

    return jobs


def save_csv(jobs, path=OUTPUT_FILE):
    df = pd.DataFrame(jobs, columns=COLUMNS)
    if not df.empty:
        df = df.drop_duplicates(subset=["url"], keep="first")
    df.to_csv(path, index=False)
    print(f"Saved {path}: {len(df)} rows")


if __name__ == "__main__":
    save_csv(collect_duckduckgo_jobs())
