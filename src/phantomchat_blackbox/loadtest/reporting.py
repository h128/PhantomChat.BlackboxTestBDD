from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phantomchat_blackbox.loadtest.runner import LoadTestResult, latency_summary


def _format_ms(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f} ms"


def format_report(result: LoadTestResult) -> str:
    metrics = result.metrics
    send_summary = latency_summary(metrics.send_ack_latency_ms)
    delivery_summary = latency_summary(metrics.delivery_latency_ms)
    lines = [
        f"Run ID: {result.run_id}",
        f"Target: {result.target_url}",
        f"Requested users/rooms: {result.config.users}/{result.config.rooms}",
        f"Elapsed: {metrics.elapsed_seconds:.2f} s",
        "",
        "Connectivity",
        f"  Connections: {metrics.successful_connections} success, {metrics.failed_connections} failed, {metrics.disconnects} unexpected disconnects",
        f"  Joins: {metrics.join_successes} success, {metrics.join_failures} failed ({metrics.join_success_rate * 100:.1f}% success)",
        "",
        "Messaging",
        f"  Sends: {metrics.send_attempts} attempted, {metrics.send_successes} acked, {metrics.send_failures} failed",
        f"  Receives: {metrics.messages_received} observed / {metrics.expected_receive_events} expected ({metrics.receive_delivery_ratio * 100:.1f}% delivery)",
        f"  Rooms with multi-user traffic: {metrics.rooms_with_traffic}",
        "",
        "Latency",
        (
            "  Send ack: "
            f"count={send_summary['count']}, min={_format_ms(send_summary['min_ms'])}, avg={_format_ms(send_summary['avg_ms'])}, "
            f"p50={_format_ms(send_summary['p50_ms'])}, p95={_format_ms(send_summary['p95_ms'])}, max={_format_ms(send_summary['max_ms'])}"
        ),
        (
            "  Delivery: "
            f"count={delivery_summary['count']}, min={_format_ms(delivery_summary['min_ms'])}, avg={_format_ms(delivery_summary['avg_ms'])}, "
            f"p50={_format_ms(delivery_summary['p50_ms'])}, p95={_format_ms(delivery_summary['p95_ms'])}, max={_format_ms(delivery_summary['max_ms'])}"
        ),
        "",
        "Rooms",
    ]

    if metrics.joined_per_room:
        for room_name, count in metrics.joined_per_room.items():
            lines.append(f"  {room_name}: {count} joined")
    else:
        lines.append("  No rooms had successful joins")

    lines.append("")
    lines.append("Failures")
    if metrics.failure_reasons:
        for failure, count in metrics.failure_reasons.most_common(10):
            lines.append(f"  {failure}: {count}")
    else:
        lines.append("  None")

    return "\n".join(lines)


def write_json_report(result: LoadTestResult, output_path: str) -> Path:
    target = Path(output_path)
    if not target.is_absolute():
        target = Path.cwd() / target
    target.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = result.to_dict()
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target