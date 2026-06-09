import requests
import pandas as pd


URL = "https://remotive.com/api/remote-jobs"

response = requests.get(URL, timeout=30)
print("Status code:", response.status_code)
response.raise_for_status()

data = response.json()

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
