import csv

from src.csv_utils import set_csv_field_limit
from src.main import count_csv_rows


def write_large_csv(path):
    large_text = "x" * (220 * 1024)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["title", "description"])
        writer.writeheader()
        writer.writerow({
            "title": "Large field job",
            "description": large_text,
        })


def test_count_csv_rows_supports_large_fields(tmp_path):
    path = tmp_path / "large_field.csv"
    write_large_csv(path)
    csv.field_size_limit(131072)

    assert count_csv_rows(path) == 1


def test_csv_dict_reader_supports_large_fields_after_helper(tmp_path):
    path = tmp_path / "large_field.csv"
    write_large_csv(path)
    csv.field_size_limit(131072)

    set_csv_field_limit()
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert len(rows[0]["description"]) > 200 * 1024
