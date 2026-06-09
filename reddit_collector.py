import requests
import pandas as pd

from config_loader import load_queries_config


_QUERY_CONFIG = load_queries_config().get("reddit", {})

SUBREDDITS = _QUERY_CONFIG.get("subreddits", [
    "remotejobs",
    "remotework",
    "forhire",
    "DataAnnotationTech",
    "WorkOnline",
    "beermoney",
    "freelance",
])

HEADERS = {
    "User-Agent": "job-intelligence-script by Yurii"
}

all_posts = []
COLUMNS = ["source", "subreddit", "title", "author", "score", "created_utc", "url", "selftext"]

for subreddit in SUBREDDITS:
    url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=25"
    response = requests.get(url, headers=HEADERS, timeout=30)

    print(subreddit, "status:", response.status_code)
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        print("Reddit subreddit failed:", subreddit, "|", exc)
        continue

    data = response.json()

    posts = data.get("data", {}).get("children", [])

    for post in posts:
        item = post["data"]

        all_posts.append({
            "source": "reddit",
            "subreddit": subreddit,
            "title": item.get("title"),
            "author": item.get("author"),
            "score": item.get("score"),
            "created_utc": item.get("created_utc"),
            "url": "https://www.reddit.com" + item.get("permalink"),
            "selftext": item.get("selftext"),
        })


df = pd.DataFrame(all_posts, columns=COLUMNS)

print("Total posts:", len(df))
if not df.empty:
    print(df[["subreddit", "title", "score", "url"]].head(10))

df.to_csv("reddit_jobs.csv", index=False)

print("Saved to reddit_jobs.csv")
