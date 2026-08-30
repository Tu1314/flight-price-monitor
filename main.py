"""鏈虹エ浠锋牸鐩戞帶 涓诲叆鍙?

鐢ㄦ硶:
    python main.py                # 鎸?config.yaml 閰嶇疆鍚姩瀹氭椂鐩戞帶
    python main.py --once         # 绔嬪嵆璺戜竴娆″悗閫€鍑?
    python main.py -c other.yaml  # 鎸囧畾閰嶇疆鏂囦欢
"""
import argparse
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
    routes = build_routes(cfg)

    crawlers = []
    for name in platforms:
        cls = REGISTRY.get(name)
        if cls is None:
            logger.warning("鏈煡骞冲彴: %s锛屽凡璺宠繃", name)
            continue
        crawlers.append(cls(crawler_cfg, logger))

    def job():
        logger.info("===== 寮€濮嬩竴杞姄鍙?=====")
        for route in routes:
            all_prices = []
            for c in crawlers:
                prices = c.safe_fetch(route.from_code, route.to_code, route.dates)
                storage.save_many(prices)
                all_prices.extend(prices)
            alerter.check_and_alert(route, all_prices)
        logger.info("===== 鏈疆鎶撳彇缁撴潫 =====")

    return job


def main():
    ap = argparse.ArgumentParser(description="鏈虹エ浠锋牸鐩戞帶宸ュ叿")
    ap.add_argument("-c", "--config", default="config.yaml", help="閰嶇疆鏂囦欢璺緞")
    ap.add_argument("--once", action="store_true", help="鍙繍琛屼竴娆″悗閫€鍑?)
    ap.add_argument("--login", metavar="PLATFORM",
                    help="鐧诲綍鎸囧畾骞冲彴(ctrip/fliggy/tongcheng)锛屽脊鍑哄彲瑙佹祻瑙堝櫒锛岀櫥褰曞畬鎴愬悗鍥炶溅淇濆瓨浼氳瘽")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"閰嶇疆鏂囦欢涓嶅瓨鍦? {cfg_path}", file=sys.stderr)
        sys.exit(1)
    cfg = load_config(str(cfg_path))

    out = cfg.get("output", {})
    logger = setup_logger(out.get("log_path", "logs/monitor.log"))
    storage = PriceStorage(out.get("db_path", "data/prices.db"))
    notifier = build_notifier(cfg.get("notifier"), logger)
    if notifier:
        logger.info("宸插惎鐢ㄦ帹閫? %s", type(notifier).__name__)
    else:
        logger.warning("ServerChan notification disabled: configure notifier.serverchan.enabled and a SendKey")
    notify_cfg = cfg.get("notifier") or {}
    alerter = Alerter(
        logger,
        notifier=notifier,
        storage=storage,
        push_drop_min=float(notify_cfg.get("push_drop_min", 30)),
        push_rise_min=float(notify_cfg.get("push_rise_min", 50)),
    )

    # ---- 鐧诲綍妯″紡 ----
    if args.login:
        name = args.login.strip().lower()
        cls = REGISTRY.get(name)
        if cls is None:
            print(f"鏈煡骞冲彴: {name}锛屽彲閫? {list(REGISTRY)}", file=sys.stderr)
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
    logger.info("鍚姩瀹氭椂璋冨害锛屾瘡 %d 鍒嗛挓涓€娆?(卤%d 鍒嗛挓闅忔満鎵板姩, 棣栨绔嬪嵆杩愯=%s)",
                interval, jitter, run_on_start)
    try:
        run_scheduler(job, interval, run_on_start, jitter_minutes=jitter)
    except (KeyboardInterrupt, SystemExit):
        logger.info("鏀跺埌閫€鍑轰俊鍙凤紝鍋滄鐩戞帶")


if __name__ == "__main__":
    main()

