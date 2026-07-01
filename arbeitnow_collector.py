import pandas as pd

from legacy_request_utils import safe_get, safe_json


URL = "https://www.arbeitnow.com/api/job-board-api"
COLUMNS = ["title", "company", "location", "remote", "url", "tags", "job_types", "description"]


response = safe_get("arbeitnow", URL, timeout=30)

if response is None:
    jobs = []
else:
    print("Status code:", response.status_code)

    data = safe_json("arbeitnow", response)
    if data is None:
        jobs = []
    else:
        print("Keys:", data.keys())

        jobs = data.get("data", [])

print("Jobs received:", len(jobs))


all_jobs = []

for job in jobs:

    all_jobs.append({
        "title": job.get("title"),
        "company": job.get("company_name"),
        "location": job.get("location"),
        "remote": job.get("remote"),
        "url": job.get("url"),
        "tags": job.get("tags"),
        "job_types": job.get("job_types"),
        "description": job.get("description"),
    })


df = pd.DataFrame(all_jobs, columns=COLUMNS)

if not df.empty:
    print(df[[
        "title",
        "company",
        "location",
        "remote"
    ]].head(20))

df.to_csv("arbeitnow_jobs.csv", index=False)

print("Saved arbeitnow_jobs.csv")
