import argparse
import html
import json
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode
from xml.etree import ElementTree

import requests


SOURCE_NAME = "reddit"
DEFAULT_OUTPUT_PATH = "output/reddit_jobs.json"
DEFAULT_REDDIT_LIMIT = 50
MAX_RESULTS = 100
MAX_REQUEST_WARNINGS = 10
REQUEST_TIMEOUT_SECONDS = 10
OLD_POST_DAYS = 30
MAX_POST_DAYS = 90
USER_AGENT = "job-intelligence-reddit-rss-collector/1.0"

DEFAULT_SUBREDDITS = [
    "WorkOnline",
    "remotework",
    "RemoteJobs",
    "forhire",
    "hiring",
    "VirtualAssistant",
    "DataAnnotation",
    "freelance_forhire",
    "beermoney",
]
DEFAULT_QUERIES = [
    "remote data entry",
    "AI annotation",
    "AI trainer",
    "LLM evaluator",
    "virtual assistant",
    "web research",
    "transcription",
    "Ukrainian",
    "Russian",
    "hiring remote",
    "paid task",
    "remote assistant",
    "data labeling",
    "language evaluator",
    "content moderator",
]

REMOTE_TERMS = [
    "remote",
    "work from home",
    "wfh",
    "anywhere",
    "worldwide",
    "fully remote",
    "online",
    "async",
]
ONSITE_TERMS = [
    "onsite",
    "on-site",
    "in office",
    "hybrid only",
    "relocation required",
    "local only",
]
CATEGORY_TERMS = {
    "ai_data": [
        "ai annotator",
        "ai trainer",
        "ai evaluator",
        "llm evaluator",
        "data annotation",
        "data labeling",
        "data entry",
    ],
    "back_office_va": [
        "virtual assistant",
        "va",
        "assistant",
        "admin",
        "back office",
        "operations",
    ],
    "research": [
        "research assistant",
        "web research",
        "internet research",
        "data collection",
        "lead generation",
    ],
    "transcription_language": [
        "transcription",
        "transcriber",
        "ukrainian",
        "russian",
        "language evaluator",
        "translation",
        "localization",
        "content moderator",
    ],
}
LANGUAGE_TERMS = ["ukrainian", "russian"]
SCAM_TERMS = [
    "crypto",
    "casino",
    "gambling",
    "adult",
    "nsfw",
    "investment",
    "trading bot",
    "forex",
    "mlm",
    "deposit required",
    "pay first",
    "registration fee",
    "telegram only",
    "whatsapp only",
    "dm me for details",
    "easy money",
    "earn $500/day",
    "no experience high pay",
]
NON_JOB_TERMS = [
    "looking for advice",
    "how do i find",
    "is this legit",
    "discussion",
    "rant",
    "meta",
    "question",
    "survey unpaid",
]
UNPAID_TERMS = [
    "unpaid",
    "volunteer",
    "experience only",
    "for exposure",
    "free work",
]
COMMISSION_TERMS = ["commission only", "referral only"]
PAYMENT_TERMS = [
    "paid",
    "salary",
    "hourly",
    "contract",
    "freelance",
    "compensation",
    "usd",
    "eur",
    "\u20ac/h",
    "$/hour",
    "per hour",
    "weekly payment",
    "paypal",
    "wise",
    "deel",
    "bank transfer",
]
CONTACT_TERMS = [
    "email",
    "apply",
    "application",
    "form",
    "careers",
    "google form",
    "typeform",
    "website",
    "dm with portfolio",
    "send cv",
    "resume",
]
WEAK_DM_TERMS = ["dm me", "dm", "message me"]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def text_contains(text, terms):
    lowered = text.lower()
    matches = []
    for term in terms:
        normalized = term.lower()
        if re.match(r"^[a-z0-9]", normalized) and re.search(r"[a-z0-9]$", normalized):
            pattern = r"(?<![a-z0-9])" + re.escape(normalized).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
            if re.search(pattern, lowered):
                matches.append(normalized)
        elif normalized in lowered:
            matches.append(normalized)
    return matches


def strip_html(value):
    text = re.sub(r"(?i)<br\s*/?>", "\n", str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def post_text(post):
    return " ".join([
        str(post.get("title") or ""),
        str(post.get("body") or ""),
        str(post.get("summary") or ""),
    ])


def post_snippet(post, limit=500):
    text = strip_html(post.get("body") or post.get("summary") or "")
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0]


def detect_category(text):
    for category, terms in CATEGORY_TERMS.items():
        if text_contains(text, terms):
            return category
    return "other"


def is_remote_post(text):
    return bool(text_contains(text, REMOTE_TERMS)) and not bool(text_contains(text, ONSITE_TERMS))


def parse_timestamp(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)


def post_age_days(post, now=None):
    published = parse_timestamp(post.get("created_at") or post.get("published_at"))
    if not published:
        return 0
    now = now or datetime.now(timezone.utc)
    return max(0, (now - published).days)


def has_clear_task_description(text):
    return len(strip_html(text)) >= 80 and bool(text_contains(text, sum(CATEGORY_TERMS.values(), [])))


def is_vague_dm_only(text, payment_signals, contact_signals):
    weak_dm = bool(text_contains(text, WEAK_DM_TERMS))
    return weak_dm and not payment_signals and not contact_signals


def score_post(post, query="", now=None):
    del query
    text = post_text(post)
    remote = is_remote_post(text)
    category = detect_category(text)
    scam_signals = text_contains(text, SCAM_TERMS)
    non_job_signals = text_contains(text, NON_JOB_TERMS)
    unpaid_signals = text_contains(text, UNPAID_TERMS)
    commission_signals = text_contains(text, COMMISSION_TERMS)
    payment_signals = text_contains(text, PAYMENT_TERMS)
    contact_signals = text_contains(text, CONTACT_TERMS)
    language_signals = text_contains(text, LANGUAGE_TERMS)
    clear_task = has_clear_task_description(text)
    vague_dm = is_vague_dm_only(text, payment_signals, contact_signals)
    age_days = post_age_days(post, now=now)
    score = 0
    reasons = []

    if remote:
        score += 30
        reasons.append("+30 remote")
    if category == "ai_data" and text_contains(text, [
        "ai annotator",
        "ai trainer",
        "ai evaluator",
        "llm evaluator",
        "data annotation",
        "data labeling",
    ]):
        score += 25
        reasons.append("+25 AI annotation/evaluator")
    if language_signals:
        score += 20
        reasons.append("+20 Ukrainian/Russian")
    if category in {"back_office_va", "research"} or text_contains(text, ["data entry", "web research"]):
        score += 20
        reasons.append("+20 VA/data entry/web research")
    if payment_signals:
        score += 15
        reasons.append("+15 payment signal")
    if contact_signals:
        score += 10
        reasons.append("+10 contact/application signal")
    if clear_task:
        score += 10
        reasons.append("+10 clear task description")

    if scam_signals:
        score -= 60
        reasons.append("-60 scam signal")
    if unpaid_signals:
        score -= 50
        reasons.append("-50 unpaid/volunteer")
    if commission_signals:
        score -= 40
        reasons.append("-40 commission/referral only")
    if not payment_signals and not contact_signals:
        score -= 30
        reasons.append("-30 no payment/contact signal")
    if vague_dm:
        score -= 30
        reasons.append("-30 vague DM-only post")
    if age_days > OLD_POST_DAYS:
        score -= 20
        reasons.append("-20 old post")

    return {
        "score": score,
        "score_reason": "; ".join(reasons),
        "remote": remote,
        "category": category,
        "language_signals": language_signals,
        "payment_signals": payment_signals,
        "contact_signals": contact_signals,
        "application_signals": contact_signals,
        "negative_signals": scam_signals + non_job_signals + unpaid_signals + commission_signals,
        "scam_signals": scam_signals,
        "non_job_signals": non_job_signals,
        "unpaid_signals": unpaid_signals,
        "commission_signals": commission_signals,
        "vague_dm": vague_dm,
        "age_days": age_days,
    }


def is_high_quality(scored):
    return (
        scored["remote"]
        and scored["category"] != "other"
        and bool(scored["payment_signals"])
        and bool(scored["contact_signals"])
        and scored["score"] >= 70
    )


def rejection_reason(post, query="", now=None):
    scored = score_post(post, query, now=now)
    if scored["scam_signals"]:
        return "scam_signal"
    if scored["non_job_signals"]:
        return "non_job_post"
    if scored["unpaid_signals"]:
        return "unpaid"
    if scored["commission_signals"]:
        return "commission_or_referral_only"
    if scored["vague_dm"]:
        return "vague_dm_only"
    if scored["age_days"] > MAX_POST_DAYS and not is_high_quality(scored):
        return "too_old"
    if not scored["remote"]:
        return "not_remote"
    if scored["category"] == "other":
        return "no_positive_category"
    if scored["score"] <= 0:
        return "low_reddit_score"
    return ""


def normalize_post(post, query, collected_at=None, now=None):
    scored = score_post(post, query, now=now)
    subreddit = post.get("subreddit") or ""
    author = post.get("author") or ""
    company = subreddit or author
    created_at = post.get("created_at") or post.get("published_at") or ""
    snippet = post_snippet(post)
    return {
        "title": post.get("title") or "",
        "company": company,
        "location": "Remote" if scored["remote"] else "",
        "url": post.get("url") or "",
        "source": SOURCE_NAME,
        "snippet": snippet,
        "description": strip_html(post.get("body") or post.get("summary") or snippet),
        "published_at": created_at,
        "created_at": created_at,
        "collected_at": collected_at or now_iso(),
        "found_at": collected_at or now_iso(),
        "query": query,
        "subreddit": subreddit,
        "author": author,
        "remote": scored["remote"],
        "category": scored["category"],
        "normalized_category": scored["category"],
        "job_type": "remote_reddit_post",
        "language_signals": ", ".join(scored["language_signals"]),
        "payment_signals": ", ".join(scored["payment_signals"]),
        "contact_signals": ", ".join(scored["contact_signals"]),
        "application_signals": ", ".join(scored["application_signals"]),
        "negative_signals": ", ".join(scored["negative_signals"]),
        "score": scored["score"],
        "reddit_score": scored["score"],
        "remote_score_delta": scored["score"],
        "score_reason": scored["score_reason"],
        "result_type": "job",
        "url_result_type": "real_job",
    }


def reddit_search_url(subreddit, query, kind="rss"):
    suffix = "search.rss" if kind == "rss" else "search.json"
    return f"https://www.reddit.com/r/{subreddit}/{suffix}?" + urlencode({
        "q": query,
        "restrict_sr": "1",
        "sort": "new",
    })


def parse_rss_posts(content, subreddit):
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise ValueError(str(exc)) from exc
    posts = []
    for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
        author_node = entry.find("{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name")
        link = entry.find("{http://www.w3.org/2005/Atom}link[@rel='alternate']")
        posts.append({
            "title": entry.findtext("{http://www.w3.org/2005/Atom}title", default=""),
            "body": entry.findtext("{http://www.w3.org/2005/Atom}content", default=""),
            "summary": entry.findtext("{http://www.w3.org/2005/Atom}summary", default=""),
            "url": link.get("href", "") if link is not None else entry.findtext("{http://www.w3.org/2005/Atom}id", default=""),
            "published_at": entry.findtext("{http://www.w3.org/2005/Atom}updated", default=""),
            "created_at": entry.findtext("{http://www.w3.org/2005/Atom}updated", default=""),
            "subreddit": subreddit,
            "author": author_node.text if author_node is not None else "",
        })
    return posts


def parse_json_posts(payload, subreddit):
    children = (((payload or {}).get("data") or {}).get("children") or [])
    posts = []
    for child in children:
        data = child.get("data") or {}
        posts.append({
            "title": data.get("title") or "",
            "body": data.get("selftext") or "",
            "summary": data.get("selftext") or "",
            "url": data.get("url") or data.get("permalink") or "",
            "published_at": data.get("created_utc") or "",
            "created_at": data.get("created_utc") or "",
            "subreddit": data.get("subreddit") or subreddit,
            "author": data.get("author") or "",
        })
    return posts


def fetch_url(url, session=None):
    client = session or requests
    return client.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def record_warning(stats):
    if stats is not None:
        stats["request_warnings"] = int(stats.get("request_warnings") or 0) + 1


def fetch_reddit_posts(subreddit, query, limit, session=None, stats=None):
    rss_url = reddit_search_url(subreddit, query, kind="rss")
    try:
        response = fetch_url(rss_url, session=session)
    except requests.exceptions.RequestException as exc:
        record_warning(stats)
        print(f"Warning: Reddit RSS request failed for {rss_url}: {exc}")
        return fetch_reddit_json_posts(subreddit, query, limit, session=session, stats=stats)
    if response.status_code in {403, 429} or response.status_code >= 500:
        record_warning(stats)
        print(f"Warning: Reddit RSS unavailable for {rss_url}: HTTP {response.status_code}")
        return fetch_reddit_json_posts(subreddit, query, limit, session=session, stats=stats)
    if response.status_code >= 400:
        record_warning(stats)
        print(f"Warning: Reddit RSS unavailable for {rss_url}: HTTP {response.status_code}")
        return []
    try:
        return parse_rss_posts(response.content, subreddit)[:limit]
    except ValueError as exc:
        record_warning(stats)
        print(f"Warning: Reddit RSS parse failed for {rss_url}: {exc}")
        return fetch_reddit_json_posts(subreddit, query, limit, session=session, stats=stats)


def fetch_reddit_json_posts(subreddit, query, limit, session=None, stats=None):
    json_url = reddit_search_url(subreddit, query, kind="json")
    try:
        response = fetch_url(json_url, session=session)
    except requests.exceptions.RequestException as exc:
        record_warning(stats)
        print(f"Warning: Reddit JSON request failed for {json_url}: {exc}")
        return []
    if response.status_code in {403, 429} or response.status_code >= 500:
        record_warning(stats)
        print(f"Warning: Reddit JSON unavailable for {json_url}: HTTP {response.status_code}")
        return []
    if response.status_code >= 400:
        record_warning(stats)
        print(f"Warning: Reddit JSON unavailable for {json_url}: HTTP {response.status_code}")
        return []
    try:
        payload = response.json()
    except ValueError as exc:
        record_warning(stats)
        print(f"Warning: Reddit JSON parse failed for {json_url}: {exc}")
        return []
    return parse_json_posts(payload, subreddit)[:limit]


def deduplicate_jobs(jobs):
    deduped = []
    seen = set()
    for job in jobs:
        keys = [
            job.get("url") or "",
            "|".join([job.get("title", ""), job.get("author", "")]).lower(),
            "|".join([job.get("title", ""), job.get("subreddit", "")]).lower(),
        ]
        if any(key and key in seen for key in keys):
            continue
        seen.update(key for key in keys if key)
        deduped.append(job)
    return deduped


def collect_jobs(
    config_path=None,
    limit=DEFAULT_REDDIT_LIMIT,
    reddit_limit=None,
    top=MAX_RESULTS,
    pause_seconds=0,
    campania_part_time_first=False,
    search_profile="remote",
    session=None,
    subreddits=None,
    queries=None,
    max_request_warnings=MAX_REQUEST_WARNINGS,
):
    del config_path, campania_part_time_first, search_profile
    per_query_limit = min(int(reddit_limit or limit or DEFAULT_REDDIT_LIMIT), MAX_RESULTS)
    max_results = min(int(top or MAX_RESULTS), MAX_RESULTS)
    collected_at = now_iso()
    jobs = []
    stats = {"request_warnings": 0}

    for subreddit in subreddits or DEFAULT_SUBREDDITS:
        for query in queries or DEFAULT_QUERIES:
            if len(jobs) >= max_results:
                break
            if int(stats.get("request_warnings") or 0) >= max_request_warnings:
                print(
                    "Warning: Reddit source repeatedly unavailable; "
                    f"stopping early after {stats['request_warnings']} request warnings"
                )
                break
            posts = fetch_reddit_posts(
                subreddit,
                query,
                per_query_limit,
                session=session,
                stats=stats,
            )
            for post in posts:
                if rejection_reason(post, query):
                    continue
                jobs.append(normalize_post(post, query, collected_at=collected_at))
                if len(jobs) >= max_results:
                    break
            if pause_seconds:
                time.sleep(pause_seconds)
        if len(jobs) >= max_results or int(stats.get("request_warnings") or 0) >= max_request_warnings:
            break

    jobs = deduplicate_jobs(jobs)
    return sorted(jobs, key=lambda job: int(job.get("reddit_score") or 0), reverse=True)[:max_results]


def write_jobs(jobs, output_path=DEFAULT_OUTPUT_PATH):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(jobs, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Saved {path}: {len(jobs)} rows")


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--reddit-limit", type=int, default=DEFAULT_REDDIT_LIMIT)
    parser.add_argument("--top", type=int, default=MAX_RESULTS)
    parser.add_argument("--pause-seconds", type=float, default=0)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    jobs = collect_jobs(
        reddit_limit=args.reddit_limit,
        top=args.top,
        pause_seconds=args.pause_seconds,
    )
    write_jobs(jobs, args.output)
    print(f"Reddit collector stats: collected={len(jobs)} warnings=see warnings above")


if __name__ == "__main__":
    main()
