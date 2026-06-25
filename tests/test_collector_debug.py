import json
import zipfile
from dataclasses import replace

import pytest

from src import collector_debug
from src.job_collector_registry import get_collector


def job(title, url, **extra):
    data = {
        "title": title,
        "company": extra.pop("company", "Acme"),
        "location": extra.pop("location", "Napoli"),
        "url": url,
        "source": extra.pop("source", "gigroup"),
        "query": extra.pop("query", "back office Napoli"),
        "score": extra.pop("score", 70),
        "remote": extra.pop("remote", False),
        "part_time": extra.pop("part_time", True),
    }
    data.update(extra)
    return data


def install_collector(monkeypatch, jobs):
    plugin = replace(
        get_collector("gigroup"),
        callable=lambda **kwargs: jobs,
    )
    monkeypatch.setattr(
        collector_debug.job_collector_registry,
        "get_collector",
        lambda name: plugin if name == "gigroup" else None,
    )
    monkeypatch.setattr(
        collector_debug.job_collector_registry,
        "enabled_collectors",
        lambda: ["gigroup"],
    )


def test_debug_creates_raw_jobs_json(monkeypatch, tmp_path):
    install_collector(monkeypatch, [job("Real", "https://www.gigroup.it/offerte-lavoro/dettaglio-offerta/1")])

    collector_debug.run_debug("gigroup", limit=5, output_dir=tmp_path)

    raw_path = tmp_path / "raw_jobs.json"
    assert raw_path.exists()
    assert json.loads(raw_path.read_text(encoding="utf-8"))[0]["title"] == "Real"


def test_debug_creates_url_classification_csv(monkeypatch, tmp_path):
    install_collector(monkeypatch, [job("Search", "https://www.gigroup.it/offerte-lavoro?text=data")])

    collector_debug.run_debug("gigroup", limit=5, output_dir=tmp_path)

    csv_text = (tmp_path / "url_classification.csv").read_text(encoding="utf-8")
    assert "url_result_type" in csv_text
    assert "rejection_reason" in csv_text
    assert "Search" in csv_text


def test_debug_creates_url_classification_xlsx(monkeypatch, tmp_path):
    install_collector(monkeypatch, [job("Search", "https://www.gigroup.it/offerte-lavoro?text=data")])

    collector_debug.run_debug("gigroup", limit=5, output_dir=tmp_path)

    xlsx_path = tmp_path / "url_classification.xlsx"
    assert xlsx_path.exists()
    with zipfile.ZipFile(xlsx_path) as xlsx:
        sheet = xlsx.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "url_result_type" in sheet


def test_debug_creates_summary_json(monkeypatch, tmp_path):
    install_collector(monkeypatch, [job("Real", "https://www.gigroup.it/offerte-lavoro/dettaglio-offerta/1")])

    collector_debug.run_debug("gigroup", limit=5, output_dir=tmp_path)

    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["collector"] == "gigroup"
    assert summary["collected"] == 1


def test_summary_counts_real_job_search_page_and_unknown(monkeypatch, tmp_path):
    install_collector(
        monkeypatch,
        [
            job("Real", "https://www.gigroup.it/offerte-lavoro/dettaglio-offerta/1"),
            job("Search", "https://www.gigroup.it/offerte-lavoro?text=data"),
            job("Unknown", "https://example.com/plain-page"),
        ],
    )

    collector_debug.run_debug("gigroup", limit=5, output_dir=tmp_path)

    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["real_job"] == 1
    assert summary["search_page"] == 1
    assert summary["unknown"] == 1


def test_unsupported_collector_has_clear_error(monkeypatch, tmp_path):
    monkeypatch.setattr(collector_debug.job_collector_registry, "get_collector", lambda name: None)
    monkeypatch.setattr(collector_debug.job_collector_registry, "enabled_collectors", lambda: ["gigroup"])

    with pytest.raises(SystemExit) as exc:
        collector_debug.main([
            "--collector",
            "missing",
            "--output-dir",
            str(tmp_path),
        ])

    assert "Unsupported collector: missing" in str(exc.value)
    assert "Available collectors: gigroup" in str(exc.value)
