from src.job_collector_registry import COLLECTOR_REGISTRY, enabled_collectors, get_collector


def test_registry_contains_duckduckgo_indeed_subito_randstad_adecco_and_gigroup():
    assert "duckduckgo" in COLLECTOR_REGISTRY
    assert "indeed" in COLLECTOR_REGISTRY
    assert "subito" in COLLECTOR_REGISTRY
    assert "randstad" in COLLECTOR_REGISTRY
    assert "adecco" in COLLECTOR_REGISTRY
    assert "gigroup" in COLLECTOR_REGISTRY


def test_registry_plugins_have_required_metadata():
    for name in ["duckduckgo", "indeed", "subito", "randstad", "adecco", "gigroup"]:
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

    assert "duckduckgo" in names
    assert "indeed" in names
    assert "subito" in names
    assert "randstad" in names
    assert "adecco" in names
    assert "gigroup" in names
