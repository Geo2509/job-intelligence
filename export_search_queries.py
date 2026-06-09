import csv
from urllib.parse import quote_plus

from job_queries import MARITIME_QUERIES, NAPLES_MARITIME_COMPANY_QUERIES


OUTPUT_FILE = "search_queries.csv"


def google_search_url(query):
    return "https://www.google.com/search?q=" + quote_plus(query)


def build_rows():
    rows = []

    for query in MARITIME_QUERIES:
        rows.append({
            "category": "maritime",
            "query": query,
            "google_url": google_search_url(query),
        })

    for query in NAPLES_MARITIME_COMPANY_QUERIES:
        rows.append({
            "category": "naples_maritime_company",
            "query": query,
            "google_url": google_search_url(query),
        })

    return rows


def main():
    rows = build_rows()

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=["category", "query", "google_url"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {OUTPUT_FILE}: {len(rows)} queries")


if __name__ == "__main__":
    main()
