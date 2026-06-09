import requests
import pandas as pd


URL = "https://www.arbeitnow.com/api/job-board-api"


response = requests.get(URL, timeout=30)

print("Status code:", response.status_code)
response.raise_for_status()

data = response.json()

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


df = pd.DataFrame(all_jobs)

if not df.empty:
    print(df[[
        "title",
        "company",
        "location",
        "remote"
    ]].head(20))

df.to_csv("arbeitnow_jobs.csv", index=False)

print("Saved arbeitnow_jobs.csv")
