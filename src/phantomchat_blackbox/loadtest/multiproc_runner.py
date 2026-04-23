from multiprocessing import Process, Queue, cpu_count
import argparse
import sys
import os
import asyncio
from pathlib import Path
from phantomchat_blackbox.config import TestConfig
from phantomchat_blackbox.loadtest.config import LoadTestConfig
from phantomchat_blackbox.loadtest.reporting import format_report, write_json_report
from phantomchat_blackbox.loadtest.runner import LoadTestRunner


def run_worker(config_dict, user_offset, users, queue):
    config = LoadTestConfig(**config_dict)
    config.users = users
    # Optionally, offset user names/IDs by user_offset for uniqueness
    runner = LoadTestRunner(config)
    result = asyncio.run(runner.run())
    queue.put(result.metrics.to_dict())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--users', type=int, required=True)
    parser.add_argument('--processes', type=int, default=cpu_count())
    parser.add_argument('--json-output', default=None, help="Optional path for a JSON summary report.")
    # Add other arguments as needed to match the normal runner
    parser.add_argument('--rooms', type=int, default=1)
    parser.add_argument('--messages-per-user', type=int, default=2)
    parser.add_argument('--message-rate', type=float, default=1.0)
    parser.add_argument('--duration-seconds', type=float, default=None)
    parser.add_argument('--ramp-up-seconds', type=float, default=5)
    parser.add_argument('--connect-timeout-seconds', type=float, default=None)
    parser.add_argument('--join-timeout-seconds', type=float, default=None)
    parser.add_argument('--send-timeout-seconds', type=float, default=None)
    parser.add_argument('--receive-settle-seconds', type=float, default=2.0)
    parser.add_argument('--room-prefix', default="load-room")
    parser.add_argument('--display-name-prefix', default="LoadUser")
    parser.add_argument('--avatar-id-base', type=int, default=1000)
    parser.add_argument('--ws-url', default=None)
    parser.add_argument('--verify-tls', dest='verify_tls', action='store_true', default=None)
    parser.add_argument('--no-verify-tls', dest='verify_tls', action='store_false')
    args = parser.parse_args()

    users_per_proc = args.users // args.processes
    extras = args.users % args.processes

    test_config = TestConfig.from_env()
    if args.ws_url:
        test_config.websocket_url = args.ws_url
    if args.verify_tls is not None:
        test_config.verify_tls = args.verify_tls

    config = LoadTestConfig.from_test_config(
        test_config,
        users=users_per_proc,  # Will be overridden per process
        rooms=args.rooms,
        messages_per_user=args.messages_per_user,
        message_rate=args.message_rate,
        duration_seconds=args.duration_seconds,
        ramp_up_seconds=args.ramp_up_seconds,
        connect_timeout_seconds=args.connect_timeout_seconds,
        join_timeout_seconds=args.join_timeout_seconds,
        send_timeout_seconds=args.send_timeout_seconds,
        receive_settle_seconds=args.receive_settle_seconds,
        room_prefix=args.room_prefix,
        display_name_prefix=args.display_name_prefix,
        avatar_id_base=args.avatar_id_base,
    )
    config_dict = config.to_dict()

    procs = []
    queue = Queue()
    user_offset = 0
    for i in range(args.processes):
        n_users = users_per_proc + (1 if i < extras else 0)
        p = Process(target=run_worker, args=(config_dict, user_offset, n_users, queue))
        procs.append(p)
        user_offset += n_users

    for p in procs:
        p.start()
    results = [queue.get() for _ in procs]
    for p in procs:
        p.join()

    # Aggregate results
    # Combine metrics for a summary (simple aggregation for now)
    from collections import Counter, defaultdict
    import statistics
    total_metrics = defaultdict(float)
    all_send_ack_latency = []
    all_delivery_latency = []
    all_failure_reasons = Counter()
    all_joined_per_room = Counter()
    all_disconnects = 0
    all_receiver_errors = 0
    for metrics in results:
        for k, v in metrics.items():
            if k in ("send_ack_latency_ms", "delivery_latency_ms"):
                if v:
                    if k == "send_ack_latency_ms":
                        all_send_ack_latency.extend(v)
                    else:
                        all_delivery_latency.extend(v)
            elif k == "failure_reasons":
                all_failure_reasons.update(v)
            elif k == "joined_per_room":
                all_joined_per_room.update(v)
            elif k == "disconnects":
                all_disconnects += v
            elif k == "receiver_errors":
                all_receiver_errors += v
            elif isinstance(v, (int, float)):
                total_metrics[k] += v

    # Fill in all expected fields with defaults if missing
    expected_fields = [
        "started_at", "finished_at", "connection_attempts", "successful_connections", "failed_connections",
        "join_attempts", "join_successes", "join_failures", "send_attempts", "send_successes", "send_failures",
        "expected_receive_events", "messages_received", "rooms_with_traffic", "elapsed_seconds", "join_success_rate",
        "receive_delivery_ratio"
    ]
    for field in expected_fields:
        if field not in total_metrics:
            total_metrics[field] = 0

    from collections import Counter
    summary = {
        "send_ack_latency_ms": all_send_ack_latency,
        "delivery_latency_ms": all_delivery_latency,
        "failure_reasons": Counter(all_failure_reasons),
        "joined_per_room": dict(all_joined_per_room),
        "disconnects": all_disconnects,
        "receiver_errors": all_receiver_errors,
    }
    summary.update(total_metrics)

    # Print formatted report
    class DummyConfig:
        def to_dict(self):
            return config_dict
    class DummyResult:
        def __init__(self, metrics):
            self.run_id = "multiproc"
            self.target_url = test_config.websocket_url
            self.config = config
            self.metrics = type("M", (), metrics)()
            self.room_names = []
            self.joined_users = []
        def to_dict(self):
            return {
                "run_id": self.run_id,
                "target_url": self.target_url,
                "config": self.config.to_dict(),
                "metrics": self.metrics.__dict__,
                "room_names": self.room_names,
                "joined_users": self.joined_users,
            }

    result_obj = DummyResult(summary)
    print(format_report(result_obj))

    if args.json_output:
        json_path = write_json_report(result_obj, args.json_output)
        from pathlib import Path
        relative_path = json_path
        try:
            relative_path = json_path.relative_to(Path.cwd())
        except ValueError:
            pass
        print(f"\nJSON report: {relative_path}")

if __name__ == "__main__":
    main()
