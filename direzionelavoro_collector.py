from arca24_collector import collect_jobs


collect_jobs(
    base_url="https://careers.direzionelavorogroup.it",
    source="direzionelavoro",
    company="Direzione Lavoro Group SpA",
    output_file="direzionelavoro_jobs.csv",
    referer="https://www.direzionelavoro.it/",
    max_pages=20,
)
