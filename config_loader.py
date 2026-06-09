import os
from pathlib import Path

import yaml


DEFAULT_QUERIES_FILE = "configs/queries.yaml"
DEFAULT_SCORING_FILE = "configs/scoring.yaml"
QUERIES_ENV = "JOB_INTELLIGENCE_QUERIES_FILE"
SCORING_ENV = "JOB_INTELLIGENCE_SCORING_FILE"


def load_yaml_config(path, label):
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"{label} config file not found: {config_path}. "
            f"Pass a valid path or create {config_path}."
        )

    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if not isinstance(data, dict):
        raise ValueError(f"{label} config file is empty or invalid: {config_path}")

    return data


def queries_config_path(default=DEFAULT_QUERIES_FILE):
    return os.environ.get(QUERIES_ENV, default)


def load_queries_config(path=None):
    return load_yaml_config(path or queries_config_path(), "Queries")


def scoring_config_path(default=DEFAULT_SCORING_FILE):
    return os.environ.get(SCORING_ENV, default)


def load_scoring_config(path=None):
    return load_yaml_config(path or scoring_config_path(), "Scoring")
