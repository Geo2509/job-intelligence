import requests
import pandas as pd

from config_loader import load_queries_config
from job_queries import MARITIME_QUERIES


_QUERY_CONFIG = load_queries_config().get("remotefirstjobs", {})
URL = "https://remotefirstjobs.com/api/search-jobs"
MAX_PAGES = _QUERY_CONFIG.get("max_pages", 2)

BASE_QUERIES = _QUERY_CONFIG.get("base", [
    "data annotation",
    "data annotator",
    "ai data annotator",
    "ai annotation",
    "ai training",
    "ai trainer",
    "russian",
    "ukrainian",
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
    "china logistics",
    "asia logistics",
    "cargo operations",
])

QUERIES = list(dict.fromkeys(BASE_QUERIES + MARITIME_QUERIES))

HEADERS = {
    "User-Agent": "job-intelligence-script by Yurii",
}


all_jobs = []

for query in QUERIES:
    for page in range(MAX_PAGES):
        params = {
            "query": query,
            "page": page,
        }

        try:
            response = requests.get(URL, params=params, headers=HEADERS, timeout=30)
            print("Status code:", response.status_code, "Query:", query, "Page:", page)
            response.raise_for_status()
        except requests.RequestException as exc:
            print("RemoteFirstJobs query failed:", query, "Page:", page, "|", exc)
            break

        try:
            data = response.json()
        except ValueError as exc:
            print("RemoteFirstJobs JSON parse failed:", query, "Page:", page, "|", exc)
            break

        jobs = data.get("jobs") or []
        print("Jobs received:", len(jobs))

        for job in jobs:
            locations = job.get("locations") or []
            location = ", ".join(locations) if isinstance(locations, list) else locations

            all_jobs.append({
                "source": "remotefirstjobs",
                "query": query,
                "title": job.get("title"),
                "company": job.get("company_name"),
                "category": job.get("category"),
                "seniority": job.get("seniority"),
                "location": location,
                "salary_min": job.get("salary_min"),
                "salary_max": job.get("salary_max"),
                "url": job.get("url"),
                "posted_at": job.get("published_at"),
                "description": job.get("description"),
            })

        if not jobs:
            break


df = pd.DataFrame(all_jobs)

if not df.empty:
    df = df.drop_duplicates(subset=["url"], keep="first")

print("Total jobs:", len(df))
if not df.empty:
    print(df[["title", "company", "query", "location", "url"]].head(30))

df.to_csv("remotefirstjobs_jobs.csv", index=False)

print("Saved remotefirstjobs_jobs.csv")
