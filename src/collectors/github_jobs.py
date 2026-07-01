import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import requests


SOURCE_NAME = "github"
SEARCH_URL = "https://api.github.com/search/issues"
DEFAULT_OUTPUT_PATH = "output/github_jobs.json"
DEFAULT_GITHUB_LIMIT = 50
MAX_RESULTS = 100
OLD_ISSUE_DAYS = 180

DEFAULT_QUERIES = [
    'is:issue "AI annotator" remote',
    'is:issue "AI trainer" remote',
    'is:issue "LLM evaluator" remote',
    'is:issue "data annotation" remote',
    'is:issue "data labeling" remote',
    'is:issue "data entry" remote',
    'is:issue "virtual assistant" remote',
    'is:issue "research assistant" remote',
    'is:issue "web research" remote',
    "is:issue transcription remote",
    "is:issue Ukrainian remote",
    "is:issue Russian remote",
    'is:issue "language evaluator" remote',
    'is:issue "content moderator" remote',
]

REMOTE_TERMS = [
    "remote",
    "work from home",
    "anywhere",
    "worldwide",
    "fully remote",
    "distributed",
    "async",
]
ONSITE_TERMS = [
    "onsite",
    "on-site",
    "in office",
    "hybrid only",
    "relocation required",
]
DEVELOPER_HEAVY_TERMS = [
    "senior software engineer",
    "staff engineer",
    "backend developer",
    "frontend developer",
    "full stack",
    "fullstack",
    "devops",
    "kubernetes",
    "blockchain",
    "solidity",
]
NON_JOB_TERMS = [
    "bug",
    "feature request",
    "acceptance criteria",
    "arxiv",
    "code review",
    "compliance",
    "implementation",
    "pull request",
    "risk detected",
    "scope boundaries",
    "spec_id",
    "success criteria",
    "uat_id",
    "good first issue",
    "hacktoberfest",
    "open source contribution",
    "contributor needed",
]
HELP_WANTED_TERM = "help wanted"
UNPAID_TERMS = ["unpaid", "volunteer", "no pay", "uncompensated"]
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
    "weekly payment",
]
CONTACT_TERMS = [
    "email",
    "apply",
    "application",
    "form",
    "careers",
    "greenhouse",
    "lever",
    "ashby",
    "workable",
]
CATEGORY_TERMS = {
    "ai_data": [
        "ai annotator",
        "ai trainer",
        "ai evaluator",
        "llm evaluator",
        "data annotation",
        "data labeling",
    ],
    "back_office_va": [
        "virtual assistant",
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
    ],
    "transcription_language": [
        "transcription",
        "transcriber",
        "ukrainian",
        "russian",
        "language evaluator",
        "translation",
        "localization",
    ],
}
LANGUAGE_TERMS = ["ukrainian", "russian"]


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


def issue_text(issue):
    return " ".join([
        str(issue.get("title") or ""),
        str(issue.get("body") or ""),
        " ".join(label.get("name", "") for label in issue.get("labels", []) if isinstance(label, dict)),
    ])


def issue_snippet(issue, limit=500):
    body = " ".join(str(issue.get("body") or "").split())
    if len(body) <= limit:
        return body
    return body[:limit].rsplit(" ", 1)[0]


def repository_owner(issue):
    repository_url = str(issue.get("repository_url") or "")
    match = re.search(r"/repos/([^/]+)/", repository_url)
    if match:
        return match.group(1)
    user = issue.get("user") or {}
    return user.get("login", "") if isinstance(user, dict) else ""


def detect_category(text):
    for category, terms in CATEGORY_TERMS.items():
        if text_contains(text, terms):
            return category
    return "other"


def is_remote_issue(text):
    remote_matches = text_contains(text, REMOTE_TERMS)
    onsite_matches = text_contains(text, ONSITE_TERMS)
    return bool(remote_matches) and not bool(onsite_matches)


def parse_created_at(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def issue_age_days(issue, now=None):
    created_at = parse_created_at(issue.get("created_at"))
    if not created_at:
        return 0
    now = now or datetime.now(timezone.utc)
    return max(0, (now - created_at).days)


def score_issue(issue, query, now=None):
    del query
    text = issue_text(issue)
    remote = is_remote_issue(text)
    category = detect_category(text)
    developer_signals = text_contains(text, DEVELOPER_HEAVY_TERMS)
    payment_signals = text_contains(text, PAYMENT_TERMS)
    contact_signals = text_contains(text, CONTACT_TERMS)
    language_signals = text_contains(text, LANGUAGE_TERMS)
    unpaid_signals = text_contains(text, UNPAID_TERMS)
    state = str(issue.get("state") or "").lower()
    score = 0
    reasons = []

    if remote:
        score += 30
        reasons.append("+30 remote")
    if category == "ai_data":
        score += 25
        reasons.append("+25 AI annotation/evaluator")
    if language_signals:
        score += 20
        reasons.append("+20 Ukrainian/Russian")
    if payment_signals:
        score += 15
        reasons.append("+15 payment signal")
    if contact_signals:
        score += 10
        reasons.append("+10 contact/application signal")
    if category != "other" and not developer_signals:
        score += 10
        reasons.append("+10 non-developer match")
    if developer_signals:
        score -= 50
        reasons.append("-50 developer-heavy")
    if unpaid_signals:
        score -= 40
        reasons.append("-40 unpaid/volunteer")
    if not payment_signals and not contact_signals:
        score -= 30
        reasons.append("-30 no payment/contact signal")
    if state == "closed":
        score -= 20
        reasons.append("-20 closed issue")
    if issue_age_days(issue, now=now) > OLD_ISSUE_DAYS:
        score -= 20
        reasons.append("-20 old issue")

    return {
        "score": score,
        "score_reason": "; ".join(reasons),
        "remote": remote,
        "category": category,
        "language_signals": language_signals,
        "payment_signals": payment_signals,
        "contact_signals": contact_signals,
        "negative_signals": developer_signals + unpaid_signals,
    }


def rejection_reason(issue, query, now=None):
    del query
    text = issue_text(issue)
    strong_non_job = text_contains(text, NON_JOB_TERMS)
    help_wanted = HELP_WANTED_TERM in text.lower()
    scored = score_issue(issue, "", now=now)

    if strong_non_job:
        return "non_job_issue"
    if help_wanted and not (scored["payment_signals"] or scored["contact_signals"]):
        return "help_wanted_without_job_signal"
    if scored["negative_signals"] and any(term in DEVELOPER_HEAVY_TERMS for term in scored["negative_signals"]):
        return "developer_heavy"
    if not scored["remote"]:
        return "not_remote"
    if scored["category"] == "other":
        return "no_positive_category"
    if scored["score"] <= 0:
        return "low_github_score"
    return ""


def normalize_issue(issue, query, collected_at=None, now=None):
    title = issue.get("title") or ""
    snippet = issue_snippet(issue)
    created_at = issue.get("created_at") or ""
    scored = score_issue(issue, query, now=now)
    company = repository_owner(issue)
    return {
        "title": title,
        "company": company,
        "location": "Remote" if scored["remote"] else "",
        "url": issue.get("html_url") or "",
        "source": SOURCE_NAME,
        "snippet": snippet,
        "description": issue.get("body") or snippet,
        "published_at": created_at,
        "created_at": created_at,
        "collected_at": collected_at or now_iso(),
        "found_at": collected_at or now_iso(),
        "query": query,
        "remote": scored["remote"],
        "category": scored["category"],
        "normalized_category": scored["category"],
        "job_type": "remote_github_issue",
        "language_signals": ", ".join(scored["language_signals"]),
        "payment_signals": ", ".join(scored["payment_signals"]),
        "contact_signals": ", ".join(scored["contact_signals"]),
        "negative_signals": ", ".join(scored["negative_signals"]),
        "score": scored["score"],
        "github_score": scored["score"],
        "remote_score_delta": scored["score"],
        "score_reason": scored["score_reason"],
        "issue_state": issue.get("state") or "",
        "result_type": "job",
        "url_result_type": "real_job",
    }


def github_search_url(query):
    return f"{SEARCH_URL}?q={quote_plus(query)}"


def search_github_issues(query, per_page, session=None):
    client = session or requests
    params = {
        "q": query,
        "per_page": per_page,
        "sort": "created",
        "order": "desc",
    }
    response = client.get(
        SEARCH_URL,
        params=params,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "job-intelligence-github-collector",
        },
        timeout=30,
    )
    if response.status_code in {403, 429}:
        print(f"Warning: GitHub search rate-limited or blocked for {github_search_url(query)}: HTTP {response.status_code}")
        return []
    response.raise_for_status()
    return response.json().get("items", [])


def deduplicate_jobs(jobs):
    deduped = []
    seen = set()
    for job in jobs:
        key = job.get("url") or "|".join([job.get("title", ""), job.get("company", "")])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(job)
    return deduped


def collect_jobs(
    config_path=None,
    limit=DEFAULT_GITHUB_LIMIT,
    github_limit=None,
    top=MAX_RESULTS,
    pause_seconds=0,
    campania_part_time_first=False,
    search_profile="remote",
    session=None,
):
    del config_path, campania_part_time_first, search_profile
    per_query_limit = min(int(github_limit or limit or DEFAULT_GITHUB_LIMIT), DEFAULT_GITHUB_LIMIT)
    max_results = min(int(top or MAX_RESULTS), MAX_RESULTS)
    collected_at = now_iso()
    jobs = []

    for query in DEFAULT_QUERIES:
        if len(jobs) >= max_results:
            break
        try:
            issues = search_github_issues(query, per_query_limit, session=session)
        except requests.exceptions.RequestException as exc:
            print(f"Warning: GitHub search failed for {github_search_url(query)}: {exc}")
            break
        for issue in issues:
            reason = rejection_reason(issue, query)
            if reason:
                continue
            jobs.append(normalize_issue(issue, query, collected_at=collected_at))
            if len(jobs) >= max_results:
                break
        if pause_seconds:
            time.sleep(pause_seconds)

    jobs = deduplicate_jobs(jobs)
    return sorted(jobs, key=lambda job: int(job.get("github_score") or 0), reverse=True)[:max_results]


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
    parser.add_argument("--github-limit", type=int, default=DEFAULT_GITHUB_LIMIT)
    parser.add_argument("--top", type=int, default=MAX_RESULTS)
    parser.add_argument("--pause-seconds", type=float, default=0)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    jobs = collect_jobs(
        github_limit=args.github_limit,
        top=args.top,
        pause_seconds=args.pause_seconds,
    )
    write_jobs(jobs, args.output)
    print(f"GitHub collector stats: collected={len(jobs)} rate_limit_warning=see warnings above")


if __name__ == "__main__":
    main()
