from pathlib import Path

import yaml

from src import job_site_profiler


def test_load_enabled_sources_from_yaml(tmp_path):
    config_path = tmp_path / "sources.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "aggregators": [
                    {
                        "name": "Enabled Source",
                        "enabled": True,
                        "type": "aggregator",
                        "priority": "high",
                        "base_url": "https://example.com",
                    },
                    {
                        "name": "Disabled Source",
                        "enabled": False,
                        "type": "aggregator",
                        "priority": "low",
                        "base_url": "https://disabled.example.com",
                    },
                ],
                "classifieds": [],
                "agencies": [],
                "remote_data_ai": [],
                "public_employment": [],
            }
        ),
        encoding="utf-8",
    )

    sources = job_site_profiler.load_enabled_sources(config_path)

    assert len(sources) == 1
    assert sources[0]["name"] == "Enabled Source"
    assert sources[0]["group"] == "aggregators"


def test_recommended_strategy_priority_order():
    assert job_site_profiler.recommended_strategy(False, True, True, True) == "manual"
    assert job_site_profiler.recommended_strategy(True, True, True, True) == "rss"
    assert job_site_profiler.recommended_strategy(True, False, True, True) == "sitemap"
    assert job_site_profiler.recommended_strategy(True, False, False, True) == "direct"
    assert job_site_profiler.recommended_strategy(True, False, False, False) == "duckduckgo"


def test_dry_run_does_not_write_output(tmp_path, monkeypatch):
    config_path = tmp_path / "sources.yaml"
    output_path = tmp_path / "profiles.yaml"
    config_path.write_text("aggregators: []\n", encoding="utf-8")

    monkeypatch.setattr(
        job_site_profiler,
        "profile_sources",
        lambda sources, limit=None, workers=job_site_profiler.DEFAULT_WORKERS: [
            {
                "name": "Example",
                "enabled": True,
                "type": "aggregator",
                "priority": "high",
                "base_url": "https://example.com",
                "status_code": 200,
                "reachable": True,
                "robots_txt_found": True,
                "sitemap_found": False,
                "rss_found": False,
                "job_keywords_found": ["jobs"],
                "recommended_strategy": "direct",
                "notes": "",
            }
        ],
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "job_site_profiler",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
            "--dry-run",
        ],
    )

    job_site_profiler.main()

    assert not output_path.exists()


def test_profile_structure(monkeypatch):
    source = {
        "name": "Example Jobs",
        "enabled": True,
        "type": "aggregator",
        "priority": "high",
        "base_url": "https://example.com/jobs",
        "notes": "Example notes.",
    }

    monkeypatch.setattr(
        job_site_profiler,
        "fetch_url",
        lambda url, timeout=job_site_profiler.REQUEST_TIMEOUT: {
            "url": url,
            "status_code": 200,
            "text": "Find lavoro and jobs here",
            "content_type": "text/html",
            "error": "",
        },
    )
    monkeypatch.setattr(job_site_profiler, "resource_found", lambda url: url.endswith("robots.txt"))
    monkeypatch.setattr(job_site_profiler, "rss_found", lambda base_url: False)

    profile = job_site_profiler.build_profile(source)

    assert set(profile) == {
        "name",
        "enabled",
        "type",
        "priority",
        "base_url",
        "status_code",
        "reachable",
        "robots_txt_found",
        "sitemap_found",
        "rss_found",
        "job_keywords_found",
        "recommended_strategy",
        "notes",
    }
    assert profile["name"] == "Example Jobs"
    assert profile["status_code"] == 200
    assert profile["reachable"] is True
    assert profile["robots_txt_found"] is True
    assert profile["sitemap_found"] is False
    assert profile["recommended_strategy"] == "direct"
