"""
End-to-end API validation script for training monitoring V2.

Workflow:
1) Resolve model/dataset (from args or auto-discovery)
2) Start a training task via /training/start
3) Subscribe to /training/v2/events/stream and collect events
4) Optionally trigger /training/stop after a given duration
5) Fetch overview + metrics and produce a JSON validation report

Usage example:
python scripts/validate_training_v2_flow.py --base-url http://127.0.0.1:8000 --auto-stop-after 45

Exit codes:
0: all acceptance checks passed
1: script executed, but acceptance checks failed
2/3: precondition/start-up payload issues
10/11/99: request/runtime errors
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


def _request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 15.0,
) -> Any:
    body = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        if not raw:
            return {}
        return json.loads(raw)


def _parse_sse_events(stream, max_seconds: int, stop_after: int | None, stop_fn):
    events: list[dict[str, Any]] = []
    last_id = ""
    last_sequence = 0
    gaps: list[dict[str, int]] = []
    regressions: list[dict[str, int]] = []
    phase_path: list[str] = []
    terminal_event: dict[str, Any] | None = None
    started = time.time()
    stop_sent = False

    cur_event_type = "message"
    cur_event_id = ""
    cur_data_lines: list[str] = []

    def finalize_event():
        nonlocal last_id, last_sequence, terminal_event
        if not cur_data_lines:
            return
        data_text = "\n".join(cur_data_lines).strip()
        if not data_text:
            return
        try:
            payload = json.loads(data_text)
        except json.JSONDecodeError:
            return
        if isinstance(payload, dict) and payload.get("kind") == "heartbeat":
            return
        sequence = int(payload.get("sequence", 0) or 0)
        if sequence > 0:
            if last_sequence > 0 and sequence > last_sequence + 1:
                gaps.append({"expected": last_sequence + 1, "got": sequence})
            if sequence <= last_sequence:
                regressions.append({"previous": last_sequence, "got": sequence})
            last_sequence = max(last_sequence, sequence)
        event = {
            "event_id": cur_event_id or payload.get("event_id", ""),
            "event_type": cur_event_type,
            "received_at": datetime.now().isoformat(),
            "payload": payload,
        }
        events.append(event)
        phase = payload.get("phase")
        if phase:
            phase_path.append(str(phase))
            if phase in ("completed", "failed", "stopped"):
                terminal_event = event
        if event["event_id"]:
            last_id = event["event_id"]

    while True:
        now = time.time()
        elapsed = now - started
        if elapsed > max_seconds:
            break
        if stop_after and not stop_sent and elapsed >= stop_after:
            try:
                stop_fn()
                stop_sent = True
            except Exception:
                stop_sent = True

        raw = stream.readline()
        if not raw:
            break
        line = raw.decode("utf-8", errors="ignore").rstrip("\r\n")
        if line == "":
            finalize_event()
            cur_event_type = "message"
            cur_event_id = ""
            cur_data_lines = []
            if terminal_event is not None:
                break
            continue
        if line.startswith("event:"):
            cur_event_type = line.split(":", 1)[1].strip() or "message"
            continue
        if line.startswith("id:"):
            cur_event_id = line.split(":", 1)[1].strip()
            continue
        if line.startswith("data:"):
            cur_data_lines.append(line.split(":", 1)[1].lstrip())
            continue

    return {
        "events": events,
        "last_event_id": last_id,
        "last_sequence": last_sequence,
        "gaps": gaps,
        "sequence_regressions": regressions,
        "phase_path": phase_path,
        "terminal_event": terminal_event,
        "stopped_by_script": stop_sent,
    }


def _pick_first_id(items: Any, keys: tuple[str, ...]) -> str | None:
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    if not isinstance(first, dict):
        return None
    for key in keys:
        value = first.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate training monitoring V2 flow through real API calls.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--model-id", default="", help="Model id to use; auto-discover if omitted")
    parser.add_argument("--dataset-id", default="", help="Dataset id to use; auto-discover if omitted")
    parser.add_argument("--method", default="qlora")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--max-seq-length", type=int, default=128)
    parser.add_argument("--gradient-accumulation", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=int, default=240, help="Max total streaming duration")
    parser.add_argument("--auto-stop-after", type=int, default=60, help="Stop training after N seconds (0 disables)")
    parser.add_argument("--output", default="", help="Optional report file path")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    script_started_at = datetime.now().isoformat()

    try:
        model_id = args.model_id.strip()
        if not model_id:
            models = _request_json("GET", f"{base}/models")
            model_id = _pick_first_id(models, ("id", "name", "model_id")) or ""
        dataset_id = args.dataset_id.strip()
        if not dataset_id:
            datasets = _request_json("GET", f"{base}/datasets")
            dataset_id = _pick_first_id(datasets, ("id", "name", "dataset_id")) or ""

        if not model_id or not dataset_id:
            print("Failed to resolve model_id/dataset_id. Provide --model-id and --dataset-id explicitly.", file=sys.stderr)
            return 2

        start_payload = {
            "model_id": model_id,
            "dataset_id": dataset_id,
            "method": args.method,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "gradient_accumulation": args.gradient_accumulation,
            "max_seq_length": args.max_seq_length,
        }
        start_url = f"{base}/training/start?skip_resource_check=true&use_queue=false&priority=normal&apply_recommended_config=false"
        start_resp = _request_json("POST", start_url, payload=start_payload, timeout=30.0)
        task_id = str(start_resp.get("id", "")).strip()
        if not task_id:
            print(f"Unexpected start response: {start_resp}", file=sys.stderr)
            return 3

        sse_url = f"{base}/training/v2/events/stream?task_id={urllib.parse.quote(task_id)}"
        req = urllib.request.Request(url=sse_url, method="GET")
        req.add_header("Accept", "text/event-stream")

        def _stop_training():
            _request_json("POST", f"{base}/training/stop", payload=None, timeout=10.0)

        with urllib.request.urlopen(req, timeout=args.timeout_seconds + 30) as stream:
            stream_data = _parse_sse_events(
                stream,
                max_seconds=args.timeout_seconds,
                stop_after=args.auto_stop_after if args.auto_stop_after > 0 else None,
                stop_fn=_stop_training,
            )

        overview = _request_json("GET", f"{base}/training/v2/overview")
        metrics = _request_json("GET", f"{base}/training/v2/tasks/{urllib.parse.quote(task_id)}/metrics?cursor=0&limit=500")

        events = stream_data["events"]
        terminal_event = stream_data["terminal_event"]
        terminal_phase = terminal_event["payload"].get("phase") if terminal_event else None
        if not terminal_phase and terminal_event:
            terminal_phase = terminal_event["payload"].get("payload", {}).get("status")

        acceptance = {
            "received_events": len(events) > 0,
            "sequence_monotonic": len(stream_data["sequence_regressions"]) == 0,
            "sequence_no_gaps": len(stream_data["gaps"]) == 0,
            "saw_running": "running" in stream_data["phase_path"],
            "saw_terminal": terminal_event is not None,
            "completed_has_final_metrics": True,
        }
        if terminal_event and terminal_event["payload"].get("phase") == "completed":
            p = terminal_event["payload"].get("payload", {})
            acceptance["completed_has_final_metrics"] = (
                "final_loss" in p and "final_lr" in p and "final_elapsed_time" in p
            )

        report = {
            "script_started_at": script_started_at,
            "script_finished_at": datetime.now().isoformat(),
            "base_url": base,
            "task_id": task_id,
            "config": start_payload,
            "stream": {
                "event_count": len(events),
                "last_event_id": stream_data["last_event_id"],
                "last_sequence": stream_data["last_sequence"],
                "gaps": stream_data["gaps"],
                "sequence_regressions": stream_data["sequence_regressions"],
                "phase_path": stream_data["phase_path"],
                "terminal_event": terminal_event,
                "stopped_by_script": stream_data["stopped_by_script"],
            },
            "overview_snapshot": overview,
            "metrics_snapshot": {
                "count": len(metrics.get("items", [])) if isinstance(metrics, dict) else 0,
                "next_cursor": metrics.get("next_cursor") if isinstance(metrics, dict) else None,
                "has_more": metrics.get("has_more") if isinstance(metrics, dict) else None,
            },
            "acceptance": acceptance,
            "overall_passed": all(acceptance.values()),
        }

        output_path = args.output.strip()
        if not output_path:
            report_dir = Path("outputs") / "validation"
            report_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(report_dir / f"training_v2_report_{task_id[:8]}.json")
        else:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(json.dumps({"task_id": task_id, "report": output_path, "overall_passed": report["overall_passed"]}, ensure_ascii=False))
        return 0 if report["overall_passed"] else 1

    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        print(f"HTTPError: {exc.code} {exc.reason}\n{detail}", file=sys.stderr)
        return 10
    except urllib.error.URLError as exc:
        print(f"URLError: {exc}", file=sys.stderr)
        return 11
    except KeyboardInterrupt:
        print("Interrupted by user", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 99


if __name__ == "__main__":
    raise SystemExit(main())
