import pandas as pd

from legacy_request_utils import safe_get, safe_json


BASE_URL = "https://himalayas.app/jobs/api"
COLUMNS = ["source", "title", "company", "location", "url", "pub_date", "description"]

all_jobs = []


def convert_timestamp(value):
    return pd.to_datetime(value, unit="s", errors="coerce")


for offset in range(0, 1000, 20):
    params = {
        "limit": 20,
        "offset": offset,
    }

    response = safe_get("himalayas", BASE_URL, params=params, timeout=30)
    if response is None:
        break

    print("Status:", response.status_code, "Offset:", offset)

    data = safe_json("himalayas", response)
    if data is None:
        break

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


df = pd.DataFrame(all_jobs, columns=COLUMNS)

print("Total jobs:", len(df))
if not df.empty:
    print(df[["title", "company", "location", "url"]].head(20))

df.to_csv("himalayas_jobs.csv", index=False)

print("Saved himalayas_jobs.csv")
