"""End-to-end: pipeline on sample rows -> validator must pass unedited."""
import sys

sys.path.insert(0, "src")

from affordai.evaluation.harness import run_dataset
from affordai.ingestion import requests as ingest_requests
from affordai.output.serializer import decisions_to_rows
from affordai.output.validator import validate_files, validate_plans
from affordai.pipeline import build_contexts, decide_context, load_dataset


def test_e2e_sample_rows_validate(tmp_path):
    tables = load_dataset("dataset/official")
    tables["requests"] = ingest_requests.load("dataset/official/sample_requests.csv")
    contexts = build_contexts(tables)
    decisions = [decide_context(c, tables, "dataset/official") for c in contexts]
    assert len(decisions) == 25
    home = {c.request_id: c.profile["home_currency"] for c in contexts}
    rows = decisions_to_rows(decisions, home)
    import csv

    req_path = tmp_path / "requests.csv"
    out_path = tmp_path / "output.csv"
    src = list(csv.DictReader(open("dataset/official/sample_requests.csv", encoding="utf-8-sig")))
    with open(req_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "request_id", "user_id", "request_date", "request_type",
            "requested_amount", "desired_completion_date",
            "allows_partial_payment", "request_text"])
        w.writeheader()
        for r in src:
            w.writerow({k: r[k] for k in w.fieldnames})
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    assert validate_files(str(req_path), str(out_path)) == []
