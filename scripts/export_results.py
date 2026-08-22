"""从 SQLite 导出最近一次抓取结果为标准 JSON（供 GitHub Pages 使用）。"""
import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/prices.db")
    ap.add_argument("--out", default="docs/data/latest.json")
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
    if not latest_ts:
        print("No data in DB")
        return

    cutoff = (datetime.fromisoformat(latest_ts) - timedelta(minutes=args.window_minutes)).isoformat(sep=" ")
    rows = con.execute(
        "SELECT platform, from_city, to_city, depart_date, price, airline, "
        "flight_no, depart_time, arrive_time, fetched_at "
        "FROM flight_prices WHERE fetched_at >= ? ORDER BY fetched_at",
        (cutoff,),
    ).fetchall()

    # 历史走势（近7天）
    hist_rows = con.execute(
        "SELECT from_city, to_city, depart_date, platform, price, fetched_at "
        "FROM flight_prices WHERE fetched_at >= datetime('now','-7 days') ORDER BY fetched_at"
    ).fetchall()
    con.close()

    results = [
        {
            "platform": r[0], "from": r[1], "to": r[2], "date": r[3],
            "price": r[4], "airline": r[5], "flight_no": r[6],
            "depart_time": r[7], "arrive_time": r[8], "fetched_at": r[9],
        }
        for r in rows
    ]

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
        })

    if not summary:
        print("No results in latest window")
        return

    # 从 summary 推断 query 信息
    from_codes = list({s["from"] for s in summary})
    to_codes   = list({s["to"]   for s in summary})
    platforms  = sorted({r["platform"] for r in results})
    depart_dates = sorted({s["date"] for s in summary if s["from"] == from_codes[0]})
    return_dates = sorted({s["date"] for s in summary if s["from"] == to_codes[0]}) if len(to_codes) > 1 else []

    # 历史 trend_data
    trend: dict = {}
    for fc, tc, d, p, price, ts in hist_rows:
        trend.setdefault(d, {}).setdefault(p, []).append({"t": ts, "v": float(price)})

    payload = {
        "ok": True,
        "data": {
            "query": {
                "from": {"code": from_codes[0], "name": from_codes[0]},
                "to":   {"code": to_codes[0],   "name": to_codes[0]},
                "depart_dates": depart_dates,
                "return_dates": return_dates,
                "platforms": platforms,
                "threshold": 0,
                "query_time": latest_ts,
            },
            "results": results,
            "summary": summary,
            "trend": trend,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(results)} records → {out}")


if __name__ == "__main__":
    main()
