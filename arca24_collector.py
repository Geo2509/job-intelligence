import html
import re
from urllib.parse import urljoin

import pandas as pd
import requests


COLUMNS = [
    "source",
    "title",
    "company",
    "location",
    "sector",
    "role",
    "contract",
    "url",
    "description",
]
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
}


def clean_text(value):
    value = re.sub(r"(?i)<br\s*/?>", "\n", value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def fetch(session, url, params=None, referer=None, source="arca24"):
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer

    try:
        response = session.get(url, params=params, headers=headers, timeout=30)
    except requests.exceptions.Timeout as exc:
        print(f"{source}: request failed: timeout for {url}: {exc}")
        return None
    except requests.exceptions.ConnectionError as exc:
        print(f"{source}: request failed: connection error for {url}: {exc}")
        return None
    except requests.exceptions.RequestException as exc:
        print(f"{source}: request failed for {url}: {exc}")
        return None

    if response.status_code >= 400:
        print(f"{source}: source unavailable: HTTP {response.status_code} for {getattr(response, 'url', url)}")
        return None

    # Arca24 sometimes serves a tiny JavaScript page that clears localStorage and
    # reloads once after setting the session cookie. A second request gets HTML.
    if "localStorage.clear()" in response.text or "window.location.reload" in response.text:
        try:
            response = session.get(url, params=params, headers=headers, timeout=30)
        except requests.exceptions.Timeout as exc:
            print(f"{source}: request failed: timeout for {url}: {exc}")
            return None
        except requests.exceptions.ConnectionError as exc:
            print(f"{source}: request failed: connection error for {url}: {exc}")
            return None
        except requests.exceptions.RequestException as exc:
            print(f"{source}: request failed for {url}: {exc}")
            return None
        if response.status_code >= 400:
            print(f"{source}: source unavailable: HTTP {response.status_code} for {getattr(response, 'url', url)}")
            return None

    return response.text


def extract_first(pattern, text, default=""):
    match = re.search(pattern, text, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return default
    return clean_text(match.group(1))


def extract_detail(label, block):
    pattern = (
        r"<th[^>]*>.*?<label>\s*"
        + re.escape(label)
        + r"\s*:?\s*</label>.*?</th>\s*<td[^>]*>(.*?)</td>"
    )
    return extract_first(pattern, block)


def parse_jobs(page_html, base_url, source, company):
    jobs = []
    blocks = re.split(r'<div class="singleResult[^"]*"', page_html)[1:]

    for block in blocks:
        href_match = re.search(r'<a\s+href="([^"]+)"[^>]*>\s*<h3[^>]*>(.*?)</h3>', block, re.DOTALL)
        if not href_match:
            continue

        url = urljoin(base_url + "/jobs.php", href_match.group(1))
        title = clean_text(href_match.group(2))
        description = extract_first(
            r'<div class="descriptionContainer"[^>]*>\s*(.*?)</div>',
            block,
        )

        location = extract_detail("Luogo di lavoro", block)
        if not location:
            location_parts = [
                extract_detail("Nazione", block),
                extract_detail("Regione", block),
                extract_detail("Luogo", block),
            ]
            location = ", ".join(part for part in location_parts if part)

        jobs.append({
            "source": source,
            "title": title,
            "company": company,
            "location": location,
            "sector": extract_detail("Settore", block),
            "role": extract_detail("Ruolo", block),
            "contract": extract_detail("Tipo di contratto", block),
            "url": url,
            "description": description,
        })

    return jobs


def parse_last_page(page_html):
    pages = [
        int(page)
        for page in re.findall(r"[?&]page=(\d+)", page_html)
        if page.isdigit()
    ]
    if not pages:
        return 1
    return max(pages)


def collect_jobs(base_url, source, company, output_file, referer=None, params=None, max_pages=20):
    list_url = f"{base_url}/jobs.php"
    params = dict(params or {})

    session = requests.Session()
    first_params = dict(params)
    first_params["page"] = 1
    first_page_html = fetch(session, list_url, params=first_params, referer=referer, source=source)
    if first_page_html is None:
        df = pd.DataFrame(columns=COLUMNS)
        df.to_csv(output_file, index=False)
        print("Total jobs:", len(df))
        print(f"Saved {output_file}")
        return
    last_page = min(parse_last_page(first_page_html), max_pages)

    all_jobs = parse_jobs(first_page_html, base_url, source, company)
    print("Status code: 200 Page: 1")
    print("Jobs received:", len(all_jobs))
    print("Last page:", last_page)

    for page in range(2, last_page + 1):
        page_params = dict(params)
        page_params["page"] = page
        page_html = fetch(session, list_url, params=page_params, referer=referer, source=source)
        if page_html is None:
            break
        jobs = parse_jobs(page_html, base_url, source, company)
        print("Status code: 200 Page:", page)
        print("Jobs received:", len(jobs))

        if not jobs:
            break

        all_jobs.extend(jobs)

    df = pd.DataFrame(all_jobs, columns=COLUMNS)

    if not df.empty:
        df = df.drop_duplicates(subset=["url"], keep="first")

    print("Total jobs:", len(df))
    if not df.empty:
        print(df[["title", "company", "location", "sector", "url"]].head(20))

    df.to_csv(output_file, index=False)
    print(f"Saved {output_file}")
