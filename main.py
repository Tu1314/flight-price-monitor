"""机票价格监控 主入口

用法:
    python main.py                # 按 config.yaml 配置启动定时监控
    python main.py --once         # 立即跑一次后退出
    python main.py -c other.yaml  # 指定配置文件
"""
import argparse
import os
import sys
from pathlib import Path

import yaml

from core.logger import setup_logger
from core.models import Route
from core.storage import PriceStorage
from core.alerter import Alerter
from core.scheduler import run_scheduler
from core.notifier import build_notifier
from crawlers import REGISTRY


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_routes(cfg: dict):
    routes = []
    for r in cfg.get("routes", []):
        routes.append(Route(
            from_code=r["from"],
            from_name=r.get("from_name", r["from"]),
            to_code=r["to"],
            to_name=r.get("to_name", r["to"]),
            dates=list(r.get("dates", [])),
            alert_threshold=float(r.get("alert_threshold", 0) or 0),
        ))
    return routes


def make_job(cfg: dict, logger, storage: PriceStorage, alerter: Alerter):
    crawler_cfg = cfg.get("crawler", {})
    platforms = cfg.get("platforms", ["ctrip", "fliggy", "tongcheng"])
    fallback_cfg = cfg.get("fallback", {}) or {}
    fallback_enabled = bool(fallback_cfg.get("enabled", True))
    fallback_platforms = fallback_cfg.get("platforms", ["qunar", "ctrip", "tongcheng"])
    routes = build_routes(cfg)

    crawler_map = {}
    for name in list(platforms) + (list(fallback_platforms) if fallback_enabled else []):
        if name in crawler_map:
            continue
        cls = REGISTRY.get(name)
        if cls is None:
            logger.warning("未知平台: %s，已跳过", name)
            continue
        crawler_map[name] = cls(crawler_cfg, logger)

    airport_cfg = cfg.get("airport_combinations", {}) or {}

    def crawl_codes(route, from_code, to_code):
        all_prices = []
        covered_dates = set()
        ordered_names = list(platforms)
        for name in ordered_names:
            c = crawler_map.get(name)
            if c is None:
                continue
            prices = c.safe_fetch(from_code, to_code, route.dates)
            storage.save_many(prices)
            all_prices.extend(prices)
            covered_dates.update(p.depart_date for p in prices)
            blocked = bool(getattr(c, "_in_risk_cooldown", lambda: False)())
            storage.save_health(
                name, from_code, to_code, len(route.dates),
                len({p.depart_date for p in prices}),
                "risk_blocked" if blocked else ("ok" if prices else "no_results"),
            )

        if fallback_enabled:
            missing = [d for d in route.dates if d not in covered_dates]
            for name in fallback_platforms:
                if not missing:
                    break
                c = crawler_map.get(name)
                if c is None or name in ordered_names:
                    continue
                logger.warning("[降级] 首选平台未覆盖 %s→%s，尝试 %s 日期=%s",
                               from_code, to_code, name, missing)
                prices = c.safe_fetch(from_code, to_code, missing)
                storage.save_many(prices)
                all_prices.extend(prices)
                covered_dates.update(p.depart_date for p in prices)
                blocked = bool(getattr(c, "_in_risk_cooldown", lambda: False)())
                storage.save_health(
                    name, from_code, to_code, len(missing),
                    len({p.depart_date for p in prices}),
                    "risk_blocked" if blocked else ("ok" if prices else "no_results"),
                )
                missing = [d for d in route.dates if d not in covered_dates]
            if missing:
                logger.warning("[降级] %s→%s 仍有日期无可用价格: %s",
                               from_code, to_code, missing)
        return all_prices

    def job():
        logger.info("===== 开始一轮抓取 =====")
        for route in routes:
            from_codes = airport_cfg.get(route.from_code, [route.from_code])
            to_codes = airport_cfg.get(route.to_code, [route.to_code])
            all_prices = []
            for from_code in from_codes:
                for to_code in to_codes:
                    logger.info("[机场组合] 查询 %s→%s", from_code, to_code)
                    all_prices.extend(crawl_codes(route, from_code, to_code))
            alerter.check_and_alert(route, all_prices)
        logger.info("===== 本轮抓取结束 =====")

    return job


def main():
    ap = argparse.ArgumentParser(description="机票价格监控工具")
    ap.add_argument("-c", "--config", default="config.yaml", help="配置文件路径")
    ap.add_argument("--once", action="store_true", help="只运行一次后退出")
    ap.add_argument("--login", metavar="PLATFORM",
                    help="登录指定平台(ctrip/fliggy/tongcheng)，弹出可见浏览器，登录完成后回车保存会话")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"配置文件不存在: {cfg_path}", file=sys.stderr)
        sys.exit(1)
    cfg = load_config(str(cfg_path))
    # Secret 只在运行时注入，不写回仓库配置；覆盖定时任务和手动任务两种场景。
    serverchan_key = os.environ.get("SERVERCHAN_SEND_KEY") or os.environ.get("SERVERCHAN_KEY")
    if serverchan_key:
        cfg.setdefault("notifier", {}).setdefault("serverchan", {})
        cfg["notifier"]["serverchan"].update(enabled=True, send_key=serverchan_key)

    out = cfg.get("output", {})
    logger = setup_logger(out.get("log_path", "logs/monitor.log"))
    storage = PriceStorage(out.get("db_path", "data/prices.db"))
    notifier = build_notifier(cfg.get("notifier"), logger)
    if notifier:
        logger.info("已启用推送: %s", type(notifier).__name__)
    else:
        logger.warning("ServerChan notification disabled: configure notifier.serverchan.enabled and a SendKey")
    notify_cfg = cfg.get("notifier") or {}
    alerter = Alerter(
        logger,
        notifier=notifier,
        storage=storage,
        push_drop_min=float(notify_cfg.get("push_drop_min", 30)),
        push_rise_min=float(notify_cfg.get("push_rise_min", 50)),
        notify_each_run=bool(notify_cfg.get("notify_each_run", True)),
        quiet_hours=notify_cfg.get("quiet_hours") or {},
    )

    # ---- 登录模式 ----
    if args.login:
        name = args.login.strip().lower()
        cls = REGISTRY.get(name)
        if cls is None:
            print(f"未知平台: {name}，可选: {list(REGISTRY)}", file=sys.stderr)
            sys.exit(2)
        crawler = cls(cfg.get("crawler", {}), logger)
        crawler.interactive_login()
        return

    job = make_job(cfg, logger, storage, alerter)

    if args.once:
        job()
        return

    sched_cfg = cfg.get("schedule", {})
    interval = int(sched_cfg.get("interval_minutes", 30))
    jitter = int(sched_cfg.get("jitter_minutes", 0))
    run_on_start = bool(sched_cfg.get("run_on_start", True))
    logger.info("启动定时调度，每 %d 分钟一次 (±%d 分钟随机扰动, 首次立即运行=%s)",
                interval, jitter, run_on_start)
    try:
        run_scheduler(job, interval, run_on_start, jitter_minutes=jitter)
    except (KeyboardInterrupt, SystemExit):
        logger.info("收到退出信号，停止监控")


if __name__ == "__main__":
    main()
