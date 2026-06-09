import requests
import pandas as pd


URL = "https://remotejobs.org/api/v1/jobs"
LIMIT = 50
MAX_PAGES = 4


all_jobs = []

for offset in range(0, LIMIT * MAX_PAGES, LIMIT):
    params = {
        "limit": LIMIT,
        "offset": offset,
    }

    response = requests.get(URL, params=params, timeout=30)
    print("Status code:", response.status_code, "Offset:", offset)
    response.raise_for_status()

    data = response.json()
    jobs = data.get("data", [])
    print("Jobs received:", len(jobs))

    for job in jobs:
        company = job.get("company") or {}
        category = job.get("category") or {}

        all_jobs.append({
            "source": "remotejobs_org",
            "title": job.get("title"),
            "company": company.get("name"),
            "category": category.get("name"),
            "location": job.get("location"),
            "salary_min": job.get("salary_min"),
            "salary_max": job.get("salary_max"),
            "salary_text": job.get("salary_text"),
            "job_type": job.get("type"),
            "url": job.get("url") or job.get("apply_url"),
            "posted_at": job.get("posted_at"),
            "description": job.get("description"),
        })

    pagination = data.get("pagination") or {}
    if not pagination.get("has_more"):
        break


df = pd.DataFrame(all_jobs)

print("Total jobs:", len(df))
if not df.empty:
    print(df[["title", "company", "category", "location", "url"]].head(20))

df.to_csv("remotejobs_org_jobs.csv", index=False)

print("Saved remotejobs_org_jobs.csv")
