"""从命令行参数生成 config.yaml（供 GitHub Actions 使用）。"""
import argparse
import os
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-code", required=True)
    ap.add_argument("--from-name", required=True)
    ap.add_argument("--to-code", required=True)
    ap.add_argument("--to-name", required=True)
    ap.add_argument("--dates", required=True)
    ap.add_argument("--return-dates", default="")
    ap.add_argument("--trip-type", choices=("one_way", "round_trip", "auto"), default="auto")
    ap.add_argument("--platforms", default="fliggy,tuniu,qunar,tongcheng")
    ap.add_argument("--threshold", type=int, default=0)
    ap.add_argument("--serverchan-key", default=None)
    ap.add_argument("--output", default="config.yaml")
    args = ap.parse_args()

    # Support both the documented secret name and the legacy name.
    serverchan_key = args.serverchan_key
    if serverchan_key is None:
        serverchan_key = (
            os.environ.get("SERVERCHAN_SEND_KEY")
            or os.environ.get("SERVERCHAN_KEY")
            or ""
        )

    depart = [d.strip() for d in args.dates.split(",") if d.strip()]
    returns = [d.strip() for d in args.return_dates.split(",") if d.strip()]
    # Treat common form values for "no return" as an empty return itinerary.
    if any(d.lower() in {"0", "none", "null", "no", "无", "无返程"} for d in returns):
        returns = []
    if args.trip_type == "one_way":
        returns = []
    elif args.trip_type == "round_trip" and not returns:
        raise SystemExit("round_trip requires at least one return date")
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]

    lines = ["routes:"]
    lines += [
        f"  - from: {args.from_code}",
        f"    from_name: {args.from_name}",
        f"    to: {args.to_code}",
        f"    to_name: {args.to_name}",
        "    dates:",
    ]
    lines += [f'      - "{d}"' for d in depart]
    lines.append(f"    alert_threshold: {args.threshold}")

    if returns:
        lines += [
            "",
            f"  - from: {args.to_code}",
            f"    from_name: {args.to_name}",
            f"    to: {args.from_code}",
            f"    to_name: {args.from_name}",
            "    dates:",
        ]
        lines += [f'      - "{d}"' for d in returns]
        lines.append(f"    alert_threshold: {args.threshold}")

    lines += ["", "platforms:"]
    lines += [f"  - {p}" for p in platforms]
    lines += [
        "",
        "fallback:",
        "  enabled: true",
        "  platforms:",
        "    - qunar",
        "    - ctrip",
        "    - tongcheng",
        "",
        "schedule:",
        "  interval_minutes: 999",
        "  jitter_minutes: 0",
        "  run_on_start: true",
        "",
        "crawler:",
        "  headless: true",
        "  timeout_seconds: 45",
        "  delay_min: 5",
        "  delay_max: 15",
        '  user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"',
        '  mobile_user_agent: ""',
        "  debug: false",
        "  debug_dir: debug",
        "  user_data_dir: user_data",
        "",
        "output:",
        "  db_path: data/prices.db",
        "  log_path: logs/monitor.log",
        "",
        "notifier:",
        "  notify_each_run: true",
        "  push_drop_min: 30",
        "  push_rise_min: 50",
        "  serverchan:",
        f"    enabled: {'true' if serverchan_key else 'false'}",
        f'    send_key: "{serverchan_key}"',
        '    channel: ""',
        "  quiet_hours:",
        "    enabled: false",
        '    start: "23:00"',
        '    end: "07:00"',
        "  webhook:",
        "    enabled: false",
        '    url: ""',
        "  telegram:",
        "    enabled: false",
        '    bot_token: ""',
        '    chat_id: ""',
        "",
    ]

    Path(args.output).write_text("\n".join(lines), encoding="utf-8")
    print(f"config written to {args.output}")
    print(f"ServerChan notifications: {'enabled' if serverchan_key else 'disabled (missing SendKey)'}")
    print(f"Price alert threshold: {args.threshold} ({'enabled' if args.threshold > 0 else 'disabled'})")


if __name__ == "__main__":
    main()
