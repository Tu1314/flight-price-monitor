"""从 SQLite 导出最近一次抓取结果为标准 JSON（供 GitHub Pages 使用）。"""
import argparse
import json
import sqlite3
import statistics
from datetime import datetime, timedelta
from pathlib import Path

import yaml


AIRPORT_GROUPS = {
    "CTU": ["CTU", "TFU"],
    "SHA": ["SHA", "PVG"],
    "BJS": ["BJS", "PEK", "PKX"],
    "CAN": ["CAN"],
}


def load_config(path: Path) -> dict:
    try:
        if path.exists():
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {}


def parse_extra(value: str) -> dict:
    try:
        obj = json.loads(value or "{}")
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def normalize_result(row) -> dict:
    extra = parse_extra(row[10] if len(row) > 10 else "")
    return {
        "platform": row[0], "from": row[1], "to": row[2], "date": row[3],
        "price": row[4], "airline": row[5], "flight_no": row[6],
        "depart_time": row[7], "arrive_time": row[8], "fetched_at": row[9],
        "tax": extra.get("tax"),
        "baggage": extra.get("baggage", "未知"),
        "seats": extra.get("seats", extra.get("quantity")),
        "cabin": extra.get("cabin", "未知"),
        "fare_type": extra.get("fare_type", "未知"),
    }


def build_health(results: list, platforms: list, expected_dates: list, persisted=None) -> list:
    total = max(1, len(expected_dates))
    health = []
    for platform in platforms:
        rows = [r for r in results if r["platform"] == platform]
        saved = (persisted or {}).get(platform)
        if not rows and saved:
            health.append(saved)
            continue
        dates = {r["date"] for r in rows}
        rate = min(1.0, len(dates) / total)
        health.append({
            "platform": platform,
            "records": len(rows),
            "dates_ok": len(dates),
            "dates_expected": len(expected_dates),
            "success_rate": round(rate * 100, 1),
            "status": "正常" if rate >= 0.8 else ("降级" if rate > 0 else "不可用"),
        })
    return health


def build_baseline(hist_rows: list) -> dict:
    grouped = {}
    for fc, tc, date, platform, price, _ts in hist_rows:
        key = (fc, tc, date, platform)
        grouped.setdefault(key, []).append(float(price))
    out = {}
    for (fc, tc, date, platform), values in grouped.items():
        out.setdefault(date, {})[platform] = {
            "avg": round(statistics.mean(values), 1),
            "median": round(statistics.median(values), 1),
            "min": round(min(values), 1),
            "samples": len(values),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/prices.db")
    ap.add_argument("--out", default="docs/data/latest.json")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--window-minutes", type=int, default=30,
                    help="把最近 N 分钟的抓取视为\"同一轮\"")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print("DB not found, skipping export")
        return

    con = sqlite3.connect(str(db))
    # 找最新的 fetched_at
    latest_ts = con.execute("SELECT MAX(fetched_at) FROM flight_prices").fetchone()[0]
    latest_ts = latest_ts or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cutoff = (datetime.fromisoformat(latest_ts) - timedelta(minutes=args.window_minutes)).isoformat(sep=" ")
    rows = con.execute(
        "SELECT platform, from_city, to_city, depart_date, price, airline, "
        "flight_no, depart_time, arrive_time, fetched_at, extra "
        "FROM flight_prices WHERE fetched_at >= ? ORDER BY fetched_at",
        (cutoff,),
    ).fetchall()

    # 历史走势和基线（近30天）
    hist_rows = con.execute(
        "SELECT from_city, to_city, depart_date, platform, price, fetched_at "
        "FROM flight_prices WHERE fetched_at >= datetime('now','-30 days') ORDER BY fetched_at"
    ).fetchall()
    health_rows = con.execute(
        "SELECT platform, from_city, to_city, requested, succeeded, status, fetched_at "
        "FROM crawl_health ORDER BY fetched_at DESC"
    ).fetchall()
    con.close()

    results = [normalize_result(r) for r in rows]

    # 汇总 summary
    routes: dict = {}
    for r in results:
        key = (r["from"], r["to"], r["date"])
        routes.setdefault(key, []).append(r)
    summary = []
    for (fc, tc, d), items in sorted(routes.items()):
        best = min(items, key=lambda x: x["price"])
        summary.append({
            "from": fc, "to": tc, "date": d,
            "per_platform": {i["platform"]: i["price"] for i in items},
            "min_price": best["price"],
            "best_platform": best["platform"],
            "best_flight": f"{best['airline']}{best['flight_no']}",
            "best_depart_time": best["depart_time"],
            "best_arrive_time": best["arrive_time"],
            "tax": best.get("tax"),
            "baggage": best.get("baggage", "未知"),
            "seats": best.get("seats"),
            "cabin": best.get("cabin", "未知"),
            "fare_type": best.get("fare_type", "未知"),
        })

    cfg = load_config(Path(args.config))
    cfg_routes = cfg.get("routes") or []
    cfg_platforms = cfg.get("platforms") or []
    from_codes = list({s["from"] for s in summary})
    to_codes = list({s["to"] for s in summary})
    if not from_codes and cfg_routes:
        from_codes = [str(cfg_routes[0].get("from", ""))]
    if not to_codes and cfg_routes:
        to_codes = [str(cfg_routes[0].get("to", ""))]
    from_codes = from_codes or [""]
    to_codes = to_codes or [""]
    platforms = cfg_platforms or sorted({r["platform"] for r in results})
    expected_dates = sorted({str(d) for route in cfg_routes for d in (route.get("dates") or [])})
    depart_dates = sorted({s["date"] for s in summary if s["from"] == from_codes[0]}) or expected_dates
    return_dates = sorted({s["date"] for s in summary if s["from"] == to_codes[0]}) if len(to_codes) > 1 else []
    threshold = max([float(route.get("alert_threshold", 0) or 0) for route in cfg_routes] or [0])
    baseline = build_baseline(hist_rows)
    persisted_health = {}
    if health_rows:
        platforms = list(dict.fromkeys(platforms + [r[0] for r in health_rows]))
    for platform, fc, tc, requested, succeeded, health_status, fetched_at in health_rows:
        if platform not in persisted_health:
            expected = max(1, int(requested))
            rate = round(min(1.0, int(succeeded) / expected) * 100, 1)
            persisted_health[platform] = {
                "platform": platform, "records": int(succeeded),
                "dates_ok": int(succeeded), "dates_expected": expected,
                "success_rate": rate,
                "status": "风控" if health_status == "risk_blocked" else health_status,
                "last_checked": fetched_at,
            }
    health = build_health(results, platforms, expected_dates or depart_dates, persisted_health)

    calendar = []
    for date in expected_dates or depart_dates:
        items = [r for r in results if r["date"] == date]
        best = min(items, key=lambda x: x["price"]) if items else None
        base_values = [v["median"] for v in baseline.get(date, {}).values()]
        current = best["price"] if best else None
        signal = "暂无价格"
        if current is not None and base_values:
            median = statistics.median(base_values)
            signal = "偏低" if current <= median * 0.9 else ("偏高" if current >= median * 1.1 else "正常")
        forecast = "暂无预测"
        if current is not None and base_values:
            median = statistics.median(base_values)
            if current <= median * 0.9:
                forecast = "短期可能维持低位"
            elif current >= median * 1.1:
                forecast = "可关注后续回落"
            else:
                forecast = "预计震荡"
        calendar.append({
            "date": date, "min_price": current,
            "best_platform": best["platform"] if best else None,
            "signal": signal,
            "baseline": round(statistics.median(base_values), 1) if base_values else None,
            "forecast": forecast,
        })

    # 历史 trend_data
    trend: dict = {}
    for fc, tc, d, p, price, ts in hist_rows:
        trend.setdefault(d, {}).setdefault(p, []).append({"t": ts, "v": float(price)})

    low_prices = [s["min_price"] for s in summary if s["min_price"] <= threshold] if threshold > 0 else []
    status = "low_price" if low_prices else "not_low"

    payload = {
        "ok": True,
        "data": {
            "query": {
                "from": {"code": from_codes[0], "name": from_codes[0]},
                "to":   {"code": to_codes[0],   "name": to_codes[0]},
                "depart_dates": depart_dates,
                "return_dates": return_dates,
                "platforms": platforms,
                "threshold": threshold,
                "query_time": latest_ts,
                "nearby_airports": {
                    "from": AIRPORT_GROUPS.get(from_codes[0], [from_codes[0]]),
                    "to": AIRPORT_GROUPS.get(to_codes[0], [to_codes[0]]),
                },
            },
            "results": results,
            "summary": summary,
            "trend": trend,
            "health": health,
            "calendar": calendar,
            "baseline": baseline,
            "status": status,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(results)} records → {out}")


if __name__ == "__main__":
    main()
