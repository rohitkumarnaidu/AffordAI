"""Evaluation harness: run pipeline -> validate -> summarize."""
from __future__ import annotations

import time

from affordai.observability.tracing import Trace
from affordai.pipeline import run


def run_dataset(dataset_dir: str, run_id: str = "E0", request_traces: dict | None = None) -> dict:
    trace = Trace()
    started = time.time()
    decisions, info = run(dataset_dir, trace=trace, run_id=run_id, request_traces=request_traces)
    runtime_s = time.time() - started
    return {
        "decisions": decisions,
        "trace": trace,
        "runtime_s": runtime_s,
        "usage": info["usage"],
        "n_requests": info["n_requests"],
    }
