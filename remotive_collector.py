import pandas as pd

from legacy_request_utils import safe_get, safe_json


URL = "https://remotive.com/api/remote-jobs"
COLUMNS = ["title", "company_name", "candidate_required_location", "url", "description"]

response = safe_get("remotive", URL, timeout=30)
if response is None:
    df = pd.DataFrame(columns=COLUMNS)
else:
    print("Status code:", response.status_code)

    data = safe_json("remotive", response)
    if data is None:
        df = pd.DataFrame(columns=COLUMNS)
    else:
        print("Keys:", data.keys())
        print("Job count from API:", data.get("job-count"))

        jobs = data.get("jobs", [])
        print("Jobs received:", len(jobs))

        df = pd.DataFrame(jobs)

print("Columns:")
print(df.columns.tolist())

if not df.empty:
    print("\nFirst jobs:")
    print(df[["title", "company_name", "candidate_required_location", "url"]].head(10))

df.to_csv("remotive_jobs.csv", index=False)

print("\nSaved to remotive_jobs.csv")
