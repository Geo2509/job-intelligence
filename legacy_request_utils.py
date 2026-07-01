import requests


def prepared_url(url, params=None):
    return requests.Request("GET", url, params=params).prepare().url


def safe_get(source, url, **kwargs):
    params = kwargs.get("params")
    fallback_url = prepared_url(url, params=params)
    try:
        response = requests.get(url, **kwargs)
    except requests.exceptions.Timeout as exc:
        print(f"{source}: request failed: timeout for {fallback_url}: {exc}")
        return None
    except requests.exceptions.ConnectionError as exc:
        print(f"{source}: request failed: connection error for {fallback_url}: {exc}")
        return None
    except requests.exceptions.RequestException as exc:
        print(f"{source}: request failed for {fallback_url}: {exc}")
        return None

    response_url = getattr(response, "url", None) or fallback_url
    if response.status_code >= 400:
        print(f"{source}: source unavailable: HTTP {response.status_code} for {response_url}")
        return None
    return response


def safe_json(source, response):
    response_url = getattr(response, "url", "")
    try:
        data = response.json()
    except ValueError as exc:
        print(f"{source}: invalid JSON for {response_url}: {exc}")
        return None
    if not isinstance(data, dict):
        print(f"{source}: invalid JSON for {response_url}: expected object")
        return None
    return data
