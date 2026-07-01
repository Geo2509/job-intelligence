from src.job_collector_registry import COLLECTOR_REGISTRY, enabled_collectors, get_collector


EXPECTED_STUDENT_V2_COLLECTORS = [
    "duckduckgo",
    "indeed",
    "subito",
    "randstad",
    "adecco",
    "gigroup",
    "talent",
    "jooble",
    "github",
]


def test_registry_contains_student_v2_collectors():
    for name in EXPECTED_STUDENT_V2_COLLECTORS:
        assert name in COLLECTOR_REGISTRY


def test_registry_plugins_have_required_metadata():
    for name in EXPECTED_STUDENT_V2_COLLECTORS:
        plugin = get_collector(name)

        assert plugin.name == name
        assert plugin.enabled is True
        assert plugin.module.startswith("src.collectors.")
        assert plugin.function == "collect_jobs"
        assert callable(plugin.callable)
        assert plugin.supports_limit is True
        assert plugin.supports_top is True
        assert plugin.supports_campania_part_time_first is True


def test_enabled_collectors_returns_enabled_registry_names():
    names = enabled_collectors()

    for name in EXPECTED_STUDENT_V2_COLLECTORS:
        assert name in names
