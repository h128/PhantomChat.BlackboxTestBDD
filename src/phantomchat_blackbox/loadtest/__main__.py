from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from phantomchat_blackbox.config import TestConfig
from phantomchat_blackbox.loadtest.config import LoadTestConfig
from phantomchat_blackbox.loadtest.reporting import format_report, write_json_report
from phantomchat_blackbox.loadtest.runner import LoadTestRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a practical WebSocket-focused load test against a PhantomChat deployment.",
    )
    parser.add_argument("--processes", type=int, default=1, help="Number of processes to split users across (for high concurrency)")
    parser.add_argument("--users", type=int, required=True, help="Number of concurrent users to simulate.")
    parser.add_argument("--rooms", type=int, default=1, help="Number of rooms to spread users across.")
    parser.add_argument(
        "--messages-per-user",
        type=int,
        default=5,
        help="Number of messages each joined user should attempt. Use 0 together with --duration-seconds for duration-only runs.",
    )
    parser.add_argument(
        "--message-rate",
        type=float,
        default=1.0,
        help="Per-user send rate in messages per second. Use 0 only for fixed-count burst runs.",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=None,
        help="Optional send duration. If set with messages-per-user, the sender stops when either limit is reached.",
    )
    parser.add_argument("--ramp-up-seconds", type=float, default=0.0, help="Spread connect/join attempts across this many seconds.")
    parser.add_argument("--connect-timeout-seconds", type=float, default=None, help="WebSocket connect timeout.")
    parser.add_argument("--join-timeout-seconds", type=float, default=None, help="Join response timeout.")
    parser.add_argument("--send-timeout-seconds", type=float, default=None, help="Send response timeout.")
    parser.add_argument(
        "--receive-settle-seconds",
        type=float,
        default=2.0,
        help="Extra wait after sending completes so trailing receive events can arrive.",
    )
    parser.add_argument("--room-prefix", default="load-room", help="Prefix for generated room names.")
    parser.add_argument("--display-name-prefix", default="LoadUser", help="Prefix for generated display names.")
    parser.add_argument("--avatar-id-base", type=int, default=1000, help="Base avatar id for generated users.")
    parser.add_argument("--ws-url", default=None, help="Override WebSocket URL. Defaults to PHANTOMCHAT_WS_URL or repo default.")
    parser.add_argument(
        "--verify-tls",
        dest="verify_tls",
        action="store_true",
        default=None,
        help="Verify TLS certificates for wss:// targets.",
    )
    parser.add_argument(
        "--no-verify-tls",
        dest="verify_tls",
        action="store_false",
        help="Disable TLS verification for wss:// targets.",
    )
    parser.add_argument("--json-output", default=None, help="Optional path for a JSON summary report.")
    return parser


async def _run_async(args: argparse.Namespace) -> int:
    test_config = TestConfig.from_env()
    if args.ws_url:
        test_config.websocket_url = args.ws_url
    if args.verify_tls is not None:
        test_config.verify_tls = args.verify_tls

    config = LoadTestConfig.from_test_config(
        test_config,
        users=args.users,
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

    runner = LoadTestRunner(config)
    result = await runner.run()
    print(format_report(result))

    if args.json_output:
        json_path = write_json_report(result, args.json_output)
        relative_path = json_path
        try:
            relative_path = json_path.relative_to(Path.cwd())
        except ValueError:
            pass
        print(f"\nJSON report: {relative_path}")

    return 0


from multiprocessing import Process, Queue, cpu_count
import copy

def run_worker(config_dict, users, user_offset, queue):
    config = LoadTestConfig(**config_dict)
    config.users = users
    # Optionally, offset user names/IDs by user_offset for uniqueness (not implemented here)
    runner = LoadTestRunner(config)
    result = asyncio.run(runner.run())
    queue.put(result.metrics.to_dict())

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.processes <= 1:
        return asyncio.run(_run_async(args))

    total_users = args.users
    num_procs = args.processes
    users_per_proc = total_users // num_procs
    extras = total_users % num_procs

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
    for i in range(num_procs):
        n_users = users_per_proc + (1 if i < extras else 0)
        p = Process(target=run_worker, args=(copy.deepcopy(config_dict), n_users, user_offset, queue))
        procs.append(p)
        user_offset += n_users

    for p in procs:
        p.start()
    results = [queue.get() for _ in procs]
    for p in procs:
        p.join()

    # Aggregate results (simple example: print all metrics)
    for i, metrics in enumerate(results):
        print(f"Process {i}: {metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())