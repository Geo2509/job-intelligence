import requests
import pandas as pd


BASE_URL = "https://himalayas.app/jobs/api"

all_jobs = []


def convert_timestamp(value):
    return pd.to_datetime(value, unit="s", errors="coerce")


for offset in range(0, 1000, 20):
    params = {
        "limit": 20,
        "offset": offset,
    }

    response = requests.get(BASE_URL, params=params, timeout=30)

    print("Status:", response.status_code, "Offset:", offset)
    response.raise_for_status()

    data = response.json()

    jobs = data.get("jobs", [])

    print("Current total collected:", len(all_jobs))

    print("Jobs received:", len(jobs))

    for job in jobs:
        all_jobs.append({
            "source": "himalayas",
            "title": job.get("title"),
            "company": job.get("companyName"),
            "location": job.get("locationRestrictions"),
            "url": job.get("applicationLink") or job.get("url"),
            "pub_date": convert_timestamp(job.get("pubDate")),
            "description": job.get("description"),
        })


df = pd.DataFrame(all_jobs)

print("Total jobs:", len(df))
if not df.empty:
    print(df[["title", "company", "location", "url"]].head(20))

df.to_csv("himalayas_jobs.csv", index=False)

print("Saved himalayas_jobs.csv")
