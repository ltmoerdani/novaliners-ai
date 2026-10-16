"""Layer 2 — StageTrace & TraceReport (internal-docs §7).

Every deterministic stage is recorded as an artifact: stage name, duration,
status, output summary. TraceReport.to_dict() is attached to
DiagnosisArtifact.pipeline_trace and can be saved to traces/*.jsonl —
so debugging points at the WRONG STAGE, not "the final output is wrong
for some reason".
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _digest(obj: Any) -> str:
    try:
        blob = json.dumps(obj, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        blob = repr(obj)
    return hashlib.sha1(blob.encode()).hexdigest()[:10]


class TraceReport:
    """Collection of stage traces for one diagnosis run."""

    def __init__(
        self,
        run_id: str = "diagnosis",
        on_stage=None,  # Callable[[str, int], None] — progres per-stage (E5)
    ) -> None:
        self.run_id = run_id
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.stages: list[dict] = []
        # E5 (23 Sep 2026): progress callback. Previously stage names were only visible
        # AFTER the run finished (pipeline_trace), even though finalize can take 70–110s — the UI
        # had no way to know which stage it was in. Used by main.py for /progress.
        self.on_stage = on_stage

    def stage(self, name: str, fn: Callable[[], Any], note: str = "") -> Any:
        """Run fn as a named stage — output is still returned,
        execution is NOT changed (trace-only wrapper)."""
        if self.on_stage:
            try:
                self.on_stage(name, len(self.stages) + 1)
            except Exception:  # noqa: BLE001 — progress must NOT fail the pipeline
                pass
        t0 = time.perf_counter()
        status, result, err = "ok", None, None
        try:
            result = fn()
        except Exception as e:  # noqa: BLE001 — the trace must still be recorded
            status, err = "error", f"{type(e).__name__}: {e}"
            raise
        finally:
            self.stages.append({
                "stage": name,
                "status": status,
                "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
                "output_digest": _digest(result),
                "output_summary": _summary(result),
                "note": note,
                "error": err,
            })
        return result

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "stage_count": len(self.stages),
            "stages": self.stages,
        }

    def save(self, dir_path: str | Path = "traces") -> Path:
        d = Path(dir_path)
        d.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        p = d / f"{ts}_{self.run_id}.jsonl"
        with p.open("w") as f:
            f.write(json.dumps(self.to_dict(), ensure_ascii=False) + "\n")
        return p


def _summary(result: Any, limit: int = 160) -> str:
    """One-line summary of the stage output — for humans to read in the trace."""
    if result is None:
        return "None"
    if isinstance(result, list):
        return f"list[{len(result)}]"
    if isinstance(result, dict):
        return f"dict[{len(result)} keys: {', '.join(list(result)[:5])}]"
    attrs = (
        "current_monthly, gap_monthly, capacity_utilization, primary, "
        "causal_status"
    )
    if hasattr(result, "model_dump"):  # pydantic
        return f"{type(result).__name__}"
    s = str(result)
    return (
        s[:limit]
        + ("…" if len(s) > limit else "")
        + (f" | [{attrs}]" if hasattr(result, "gap_monthly") else "")
    )
