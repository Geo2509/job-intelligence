from arca24_collector import collect_jobs


collect_jobs(
    base_url="https://careers.attalgroup.it",
    source="attalgroup",
    company="ATTAL Group",
    output_file="attalgroup_jobs.csv",
    referer="https://www.attalgroup.it/",
    params={"country": "109"},
    max_pages=20,
)
