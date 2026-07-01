import requests
import pandas as pd


URL = "https://remotejobs.org/api/v1/jobs"
LIMIT = 50
MAX_PAGES = 4
COLUMNS = [
    "source",
    "title",
    "company",
    "category",
    "location",
    "salary_min",
    "salary_max",
    "salary_text",
    "job_type",
    "url",
    "posted_at",
    "description",
]


def empty_jobs_frame():
    return pd.DataFrame(columns=COLUMNS)


def request_url(params):
    return requests.Request("GET", URL, params=params).prepare().url


def collect_jobs():
    all_jobs = []

    for offset in range(0, LIMIT * MAX_PAGES, LIMIT):
        params = {
            "limit": LIMIT,
            "offset": offset,
        }
        url = request_url(params)

        try:
            response = requests.get(URL, params=params, timeout=30)
            print("Status code:", response.status_code, "Offset:", offset)
            response.raise_for_status()
        except (requests.exceptions.HTTPError, requests.exceptions.RequestException) as exc:
            print(f"Warning: remotejobs.org API request failed for {url}: {exc}")
            return empty_jobs_frame()

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

    return pd.DataFrame(all_jobs, columns=COLUMNS)


def main():
    df = collect_jobs()

    print("Total jobs:", len(df))
    if not df.empty:
        print(df[["title", "company", "category", "location", "url"]].head(20))

    df.to_csv("remotejobs_org_jobs.csv", index=False)

    print("Saved remotejobs_org_jobs.csv")


if __name__ == "__main__":
    main()
