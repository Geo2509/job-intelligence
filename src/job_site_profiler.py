import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import yaml


SOURCE_GROUPS = [
    "aggregators",
    "classifieds",
    "agencies",
    "remote_data_ai",
    "public_employment",
]
JOB_KEYWORDS = [
    "lavoro",
    "jobs",
    "careers",
    "offerte",
    "posizione",
    "vacancy",
    "remote",
    "remoto",
]
FEED_PATHS = [
    "feed",
    "rss.xml",
]
REQUEST_TIMEOUT = 4
MAX_RESPONSE_BYTES = 200_000
DEFAULT_WORKERS = 8
USER_AGENT = "job-intelligence-site-profiler/1.0"


def load_enabled_sources(config_path):
    data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    sources = []
    for group_name in SOURCE_GROUPS:
        for source in data.get(group_name, []) or []:
            if source.get("enabled"):
                source = dict(source)
                source["group"] = group_name
                sources.append(source)
    return sources


def root_url(url):
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url.rstrip("/") + "/"
    return f"{parsed.scheme}://{parsed.netloc}/"


def fetch_url(url, timeout=REQUEST_TIMEOUT):
    curl_result = fetch_url_with_curl(url, timeout)
    if curl_result is not None:
        return curl_result

    session = requests.Session()
    session.max_redirects = 3
    try:
        response = session.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            allow_redirects=True,
            stream=True,
        )
        content = response.raw.read(MAX_RESPONSE_BYTES, decode_content=True)
        encoding = response.encoding or "utf-8"
        text = content.decode(encoding, errors="replace")
        response.close()
        return {
            "url": url,
            "status_code": response.status_code,
            "text": text,
            "content_type": response.headers.get("content-type", ""),
            "error": "",
        }
    except requests.RequestException as exc:
        return {
            "url": url,
            "status_code": None,
            "text": "",
            "content_type": "",
            "error": str(exc),
        }
    finally:
        session.close()


def fetch_url_with_curl(url, timeout=REQUEST_TIMEOUT):
    command = [
        "curl",
        "--location",
        "--max-redirs",
        "3",
        "--max-time",
        str(timeout),
        "--silent",
        "--show-error",
        "--range",
        f"0-{MAX_RESPONSE_BYTES - 1}",
        "--user-agent",
        USER_AGENT,
        "--write-out",
        "\n__JI_STATUS__:%{http_code}\n__JI_CONTENT_TYPE__:%{content_type}\n",
        url,
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=timeout + 1,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    output = (result.stdout or b"").decode("utf-8", errors="replace")
    status_marker = "\n__JI_STATUS__:"
    content_type_marker = "\n__JI_CONTENT_TYPE__:"
    status_code = None
    content_type = ""
    text = output

    if status_marker in output and content_type_marker in output:
        text, marker_text = output.rsplit(status_marker, 1)
        status_text, content_type_text = marker_text.split(content_type_marker, 1)
        try:
            status_code = int(status_text.strip())
        except ValueError:
            status_code = None
        content_type = content_type_text.strip()

    return {
        "url": url,
        "status_code": status_code,
        "text": text,
        "content_type": content_type,
        "error": (result.stderr or b"").decode("utf-8", errors="replace").strip(),
    }


def is_successful_status(status_code):
    return status_code is not None and 200 <= status_code < 400


def resource_found(url):
    result = fetch_url(url)
    return is_successful_status(result["status_code"])


def rss_found(base_url):
    candidates = []
    base = base_url.rstrip("/") + "/"
    root = root_url(base_url)
    for path in FEED_PATHS:
        candidates.append(urljoin(base, path))
        candidates.append(urljoin(root, path))

    for url in dict.fromkeys(candidates):
        result = fetch_url(url)
        if not is_successful_status(result["status_code"]):
            continue
        content_type = result["content_type"].lower()
        text_start = result["text"][:500].lower()
        if (
            "xml" in content_type
            or "rss" in content_type
            or "<rss" in text_start
            or "<feed" in text_start
        ):
            return True
    return False


def find_job_keywords(page_text):
    text = page_text.lower()
    return [keyword for keyword in JOB_KEYWORDS if keyword in text]


def recommended_strategy(reachable, rss, sitemap, job_keywords):
    if not reachable:
        return "manual"
    if rss:
        return "rss"
    if sitemap:
        return "sitemap"
    if job_keywords:
        return "direct"
    return "duckduckgo"


def build_profile(source):
    base_url = source.get("base_url", "")
    page = fetch_url(base_url)
    status_code = page["status_code"]
    reachable = is_successful_status(status_code)
    keywords_found = find_job_keywords(page["text"]) if reachable else []
    robots = resource_found(urljoin(root_url(base_url), "robots.txt")) if base_url else False
    sitemap = resource_found(urljoin(root_url(base_url), "sitemap.xml")) if base_url else False
    feed = rss_found(base_url) if base_url and reachable else False
    strategy = recommended_strategy(reachable, feed, sitemap, bool(keywords_found))

    notes = source.get("notes", "")
    if page["error"]:
        notes = f"{notes} Profiler error: {page['error']}".strip()

    return {
        "name": source.get("name", ""),
        "enabled": bool(source.get("enabled")),
        "type": source.get("type", ""),
        "priority": source.get("priority", ""),
        "base_url": base_url,
        "status_code": status_code,
        "reachable": reachable,
        "robots_txt_found": robots,
        "sitemap_found": sitemap,
        "rss_found": feed,
        "job_keywords_found": keywords_found,
        "recommended_strategy": strategy,
        "notes": notes,
    }


def profile_sources(sources, limit=None, workers=DEFAULT_WORKERS):
    selected_sources = sources[:limit] if limit else sources
    if not selected_sources:
        return []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(build_profile, selected_sources))


def write_profiles(profiles, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {"profiles": profiles},
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def print_summary(profiles, output_path=None, dry_run=False):
    reachable = sum(1 for profile in profiles if profile["reachable"])
    strategies = {}
    for profile in profiles:
        strategy = profile["recommended_strategy"]
        strategies[strategy] = strategies.get(strategy, 0) + 1

    print(f"Profiles built: {len(profiles)}")
    print(f"Reachable sources: {reachable}")
    for strategy, count in sorted(strategies.items()):
        print(f"Strategy {strategy}: {count}")
    if dry_run:
        print("Dry run: output file not written.")
    elif output_path:
        print(f"Profiles written: {output_path}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/job_sources.yaml")
    parser.add_argument("--output", default="configs/job_site_profiles.yaml")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    sources = load_enabled_sources(args.config)
    profiles = profile_sources(sources, args.limit, args.workers)
    if not args.dry_run:
        write_profiles(profiles, args.output)
    print_summary(profiles, args.output, args.dry_run)


if __name__ == "__main__":
    main()
