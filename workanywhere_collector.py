import html
import time
import xml.etree.ElementTree as ET

import pandas as pd

from config_loader import load_queries_config
from legacy_request_utils import safe_get


_QUERY_CONFIG = load_queries_config().get("workanywhere", {})
COLUMNS = [
    "source",
    "feed_category",
    "title",
    "company",
    "location",
    "url",
    "posted_at",
    "description",
]

FEEDS = [
    (feed["category"], feed["url"])
    for feed in _QUERY_CONFIG.get("feeds", [
    ("all", "https://workanywhere.pro/rss.xml"),
    ("support", "https://workanywhere.pro/rss/support.xml"),
    ("data_ai", "https://workanywhere.pro/rss/data-ai.xml"),
    ])
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
}


def text_from(item, tag):
    value = item.findtext(tag)
    if value is None:
        return ""
    return html.unescape(value).strip()


def split_title(value):
    separators = [" at ", " - "]

    for separator in separators:
        if separator in value:
            title, company = value.split(separator, 1)
            return title.strip(), company.strip()

    return value.strip(), ""


all_jobs = []

for category, url in FEEDS:
    response = safe_get("workanywhere", url, headers=HEADERS, timeout=30)
    if response is None:
        print("Skipped unavailable feed:", category)
        continue
    print("Status code:", response.status_code, "Feed:", category)

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        print(f"workanywhere: invalid XML for {getattr(response, 'url', url)}: {exc}")
        continue
    items = root.findall("./channel/item")
    print("Jobs received:", len(items))

    for item in items:
        raw_title = text_from(item, "title")
        title, company = split_title(raw_title)

        all_jobs.append({
            "source": "workanywhere",
            "feed_category": category,
            "title": title,
            "company": company,
            "location": "remote",
            "url": text_from(item, "link"),
            "posted_at": text_from(item, "pubDate"),
            "description": text_from(item, "description"),
        })

    time.sleep(2)


df = pd.DataFrame(all_jobs, columns=COLUMNS)

if not df.empty:
    df = df.drop_duplicates(subset=["url"], keep="first")

print("Total jobs:", len(df))
if not df.empty:
    print(df[["title", "company", "feed_category", "url"]].head(20))

df.to_csv("workanywhere_jobs.csv", index=False)

print("Saved workanywhere_jobs.csv")
