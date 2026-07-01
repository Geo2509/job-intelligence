from pathlib import Path

import yaml


CONFIG_PATH = Path("configs/job_sources.yaml")
REQUIRED_GROUPS = {
    "aggregators",
    "classifieds",
    "agencies",
    "remote_data_ai",
    "public_employment",
    "remote_discovery_queries",
    "student_services",
    "duckduckgo_discovery_queries",
}
REQUIRED_SOURCE_FIELDS = {"name", "enabled", "type", "priority"}
QUERY_GROUPS = {"duckduckgo_discovery_queries", "remote_discovery_queries", "student_services"}
SOURCE_GROUPS = REQUIRED_GROUPS - QUERY_GROUPS
REQUIRED_DISCOVERY_CATEGORIES = {
    "# DATA / OFFICE",
    "# HOTEL",
    "# RISTORANTE / BAR",
    "# PULIZIE",
    "# MANUTENZIONE",
    "# MAGAZZINO",
    "# GDO",
    "# TURISMO",
    "# WEEKEND / TURNI",
    "# REMOTE",
}


def load_config():
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def test_job_sources_config_exists():
    assert CONFIG_PATH.exists()


def test_job_sources_config_yaml_is_readable():
    data = load_config()

    assert isinstance(data, dict)


def test_job_sources_config_has_required_groups():
    data = load_config()

    assert REQUIRED_GROUPS.issubset(data)


def test_each_source_has_required_fields():
    data = load_config()

    for group_name in SOURCE_GROUPS:
        for source in data[group_name]:
            assert REQUIRED_SOURCE_FIELDS.issubset(source), group_name


def test_duckduckgo_discovery_has_at_least_10_queries():
    data = load_config()

    assert len(data["duckduckgo_discovery_queries"]) >= 10


def test_remote_discovery_has_required_queries():
    data = load_config()

    assert len(data["remote_discovery_queries"]) >= 30
    assert "AI trainer remote Italian" in data["remote_discovery_queries"]
    assert "data entry smart working Italia" in data["remote_discovery_queries"]


def test_student_services_queries_are_configured():
    data = load_config()

    assert "babysitter" in data["student_services"]
    assert "aiuto compiti" in data["student_services"]


def test_duckduckgo_discovery_has_expanded_search_coverage():
    data = load_config()

    assert len(data["duckduckgo_discovery_queries"]) >= 100


def test_duckduckgo_discovery_queries_have_no_duplicates():
    data = load_config()
    queries = data["duckduckgo_discovery_queries"]

    assert len(queries) == len(set(queries))


def test_duckduckgo_discovery_categories_are_documented():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")

    for category in REQUIRED_DISCOVERY_CATEGORIES:
        assert category in config_text
