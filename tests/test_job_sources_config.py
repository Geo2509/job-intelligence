from pathlib import Path

import yaml


CONFIG_PATH = Path("configs/job_sources.yaml")
REQUIRED_GROUPS = {
    "aggregators",
    "classifieds",
    "agencies",
    "remote_data_ai",
    "public_employment",
    "duckduckgo_discovery_queries",
}
REQUIRED_SOURCE_FIELDS = {"name", "enabled", "type", "priority"}
SOURCE_GROUPS = REQUIRED_GROUPS - {"duckduckgo_discovery_queries"}


def test_job_sources_config_exists():
    assert CONFIG_PATH.exists()


def test_job_sources_config_yaml_is_readable():
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    assert isinstance(data, dict)


def test_job_sources_config_has_required_groups():
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    assert REQUIRED_GROUPS.issubset(data)


def test_each_source_has_required_fields():
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    for group_name in SOURCE_GROUPS:
        for source in data[group_name]:
            assert REQUIRED_SOURCE_FIELDS.issubset(source), group_name


def test_duckduckgo_discovery_has_at_least_10_queries():
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    assert len(data["duckduckgo_discovery_queries"]) >= 10
