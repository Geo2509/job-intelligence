from dataclasses import dataclass, field
from typing import Callable

from src.collectors import (
    adecco_jobs,
    duckduckgo_jobs,
    github_jobs,
    gigroup_jobs,
    indeed_jobs,
    jooble_jobs,
    randstad_jobs,
    reddit_jobs,
    subito_jobs,
    talent_jobs,
)


@dataclass(frozen=True)
class CollectorPlugin:
    name: str
    enabled: bool
    module: str
    function: str
    callable: Callable
    supports_campania_part_time_first: bool
    supports_top: bool
    supports_limit: bool
    default_kwargs: dict = field(default_factory=dict)
    supports_search_profile: bool = False


COLLECTOR_REGISTRY = {
    "duckduckgo": CollectorPlugin(
        name="duckduckgo",
        enabled=True,
        module="src.collectors.duckduckgo_jobs",
        function="collect_jobs",
        callable=duckduckgo_jobs.collect_jobs,
        supports_campania_part_time_first=True,
        supports_top=True,
        supports_limit=True,
        default_kwargs={"pause_seconds": 0},
        supports_search_profile=True,
    ),
    "indeed": CollectorPlugin(
        name="indeed",
        enabled=True,
        module="src.collectors.indeed_jobs",
        function="collect_jobs",
        callable=indeed_jobs.collect_jobs,
        supports_campania_part_time_first=True,
        supports_top=True,
        supports_limit=True,
        default_kwargs={"direct_pause_seconds": 0},
    ),
    "subito": CollectorPlugin(
        name="subito",
        enabled=True,
        module="src.collectors.subito_jobs",
        function="collect_jobs",
        callable=subito_jobs.collect_jobs,
        supports_campania_part_time_first=True,
        supports_top=True,
        supports_limit=True,
        default_kwargs={"direct_pause_seconds": 0},
    ),
    "randstad": CollectorPlugin(
        name="randstad",
        enabled=True,
        module="src.collectors.randstad_jobs",
        function="collect_jobs",
        callable=randstad_jobs.collect_jobs,
        supports_campania_part_time_first=True,
        supports_top=True,
        supports_limit=True,
        default_kwargs={"direct_pause_seconds": 0},
    ),
    "adecco": CollectorPlugin(
        name="adecco",
        enabled=True,
        module="src.collectors.adecco_jobs",
        function="collect_jobs",
        callable=adecco_jobs.collect_jobs,
        supports_campania_part_time_first=True,
        supports_top=True,
        supports_limit=True,
        default_kwargs={"direct_pause_seconds": 0},
    ),
    "gigroup": CollectorPlugin(
        name="gigroup",
        enabled=True,
        module="src.collectors.gigroup_jobs",
        function="collect_jobs",
        callable=gigroup_jobs.collect_jobs,
        supports_campania_part_time_first=True,
        supports_top=True,
        supports_limit=True,
        default_kwargs={"direct_pause_seconds": 0},
    ),
    "talent": CollectorPlugin(
        name="talent",
        enabled=True,
        module="src.collectors.talent_jobs",
        function="collect_jobs",
        callable=talent_jobs.collect_jobs,
        supports_campania_part_time_first=True,
        supports_top=True,
        supports_limit=True,
        default_kwargs={"direct_pause_seconds": 0},
    ),
    "jooble": CollectorPlugin(
        name="jooble",
        enabled=True,
        module="src.collectors.jooble_jobs",
        function="collect_jobs",
        callable=jooble_jobs.collect_jobs,
        supports_campania_part_time_first=True,
        supports_top=True,
        supports_limit=True,
        default_kwargs={"direct_pause_seconds": 0},
    ),
    "github": CollectorPlugin(
        name="github",
        enabled=True,
        module="src.collectors.github_jobs",
        function="collect_jobs",
        callable=github_jobs.collect_jobs,
        supports_campania_part_time_first=True,
        supports_top=True,
        supports_limit=True,
        default_kwargs={"pause_seconds": 0},
        supports_search_profile=True,
    ),
    "reddit": CollectorPlugin(
        name="reddit",
        enabled=True,
        module="src.collectors.reddit_jobs",
        function="collect_jobs",
        callable=reddit_jobs.collect_jobs,
        supports_campania_part_time_first=True,
        supports_top=True,
        supports_limit=True,
        default_kwargs={"pause_seconds": 0},
        supports_search_profile=True,
    ),
}


def get_collector(name):
    return COLLECTOR_REGISTRY.get(name)


def enabled_collectors():
    return [
        plugin.name
        for plugin in COLLECTOR_REGISTRY.values()
        if plugin.enabled
    ]
