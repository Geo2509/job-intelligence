from arca24_collector import collect_jobs


collect_jobs(
    base_url="https://careers.smartjobspa.it",
    source="smartjobspa",
    company="SMART JOB SPA",
    output_file="smartjobspa_jobs.csv",
    referer="https://www.smartjobspa.it/",
    max_pages=20,
)
