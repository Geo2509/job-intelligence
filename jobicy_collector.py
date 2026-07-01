import pandas as pd

from config_loader import load_queries_config
from legacy_request_utils import safe_get, safe_json


URL = "https://jobicy.com/api/v2/remote-jobs"
COLUMNS = [
    "source",
    "title",
    "company",
    "category",
    "location",
    "job_type",
    "url",
    "posted_at",
    "description",
]
_QUERY_CONFIG = load_queries_config().get("jobicy", {})

QUERIES = _QUERY_CONFIG.get("params", [
    {"count": 50, "industry": "data-science"},
    {"count": 50, "industry": "supporting"},
    {"count": 50, "tag": "python"},
    {"count": 50, "tag": "data"},
    {"count": 50, "tag": "assistant"},
])


all_jobs = []

for params in QUERIES:
    response = safe_get("jobicy", URL, params=params, timeout=30)
    if response is None:
        break
    print("Status code:", response.status_code, "Params:", params)

    data = safe_json("jobicy", response)
    if data is None:
        break
    jobs = data.get("jobs", [])
    print("Jobs received:", len(jobs))

    for job in jobs:
        all_jobs.append({
            "source": "jobicy",
            "title": job.get("jobTitle"),
            "company": job.get("companyName"),
            "category": job.get("jobIndustry"),
            "location": job.get("jobGeo"),
            "job_type": job.get("jobType"),
            "url": job.get("url"),
            "posted_at": job.get("pubDate"),
            "description": job.get("jobDescription"),
        })


df = pd.DataFrame(all_jobs, columns=COLUMNS)

if not df.empty:
    df = df.drop_duplicates(subset=["url"], keep="first")

print("Total jobs:", len(df))
if not df.empty:
    print(df[["title", "company", "category", "location", "url"]].head(20))

df.to_csv("jobicy_jobs.csv", index=False)

print("Saved jobicy_jobs.csv")
