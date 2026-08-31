"""GitHub Actions 专用版报告渲染器：读取 docs/data/latest.json（含 trend），输出 docs/data/report.html。"""
import argparse
import html as html_mod
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from string import Template
from urllib.parse import quote

PLATFORM_NAMES  = {"fliggy":"飞猪","tuniu":"途牛","ctrip":"携程","qunar":"去哪儿","tongcheng":"同程"}
PLATFORM_COLORS = {"fliggy":"#FF6B00","tuniu":"#00A651","ctrip":"#0086F6","qunar":"#FF4500","tongcheng":"#7C3AED"}

CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#f0f2f7;--card:#fff;--border:#e8eaef;--text:#1a1d29;--sub:#6b7280;
  --accent:#2563eb;--red:#dc2626;--orange:#d97706;--radius:16px;--shadow:0 2px 12px rgba(0,0,0,.07)}
body{font-family:-apple-system,"PingFang SC","Helvetica Neue",sans-serif;background:var(--bg);color:var(--text)}
.page{max-width:980px;margin:0 auto;padding:28px 16px 60px}
.hero{background:linear-gradient(135deg,#1e3a8a 0%,#2563eb 60%,#60a5fa 100%);
  border-radius:var(--radius);padding:32px 36px;margin-bottom:20px;position:relative;overflow:hidden}
.hero::after{content:'✈';position:absolute;right:28px;top:50%;transform:translateY(-50%);
  font-size:72px;opacity:.12;pointer-events:none}
.hero h1{color:#fff;font-size:22px;font-weight:700;margin-bottom:6px}
.hero .sub{color:rgba(255,255,255,.75);font-size:13px}
.card{background:var(--card);border-radius:var(--radius);padding:22px 24px;
  margin-bottom:18px;box-shadow:var(--shadow)}
.card-title{font-size:14px;font-weight:600;color:var(--sub);text-transform:uppercase;
  letter-spacing:.05em;margin-bottom:16px;display:flex;align-items:center;gap:8px}
.card-title::before{content:'';display:inline-block;width:3px;height:15px;
  background:var(--accent);border-radius:2px}
.table-wrap{overflow-x:auto;border-radius:8px}
table{width:100%;border-collapse:collapse;font-size:14px;min-width:520px}
th{padding:10px 8px;text-align:center;background:#f8f9fc;color:var(--sub);
  font-weight:500;font-size:12px;border-bottom:2px solid var(--border)}
th:first-child{text-align:left}
td{padding:12px 8px;text-align:center;border-bottom:1px solid #f3f4f8;vertical-align:middle}
td:first-child{text-align:left}
tr:last-child td{border-bottom:none}
.na{color:#ccc}.best{color:var(--red);font-weight:800;font-size:16px}
.tag-d{display:inline-block;padding:2px 7px;border-radius:5px;font-size:11px;
  font-weight:600;background:#dbeafe;color:#1d4ed8}
.tag-r{display:inline-block;padding:2px 7px;border-radius:5px;font-size:11px;
  font-weight:600;background:#d1fae5;color:#065f46}
.badge{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:600;color:#fff;margin-top:3px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;vertical-align:middle}
.time{font-size:12px;color:var(--sub);line-height:1.6}
.total{background:linear-gradient(90deg,#fff7ed,#fef3c7);border:1.5px solid #fde68a;
  border-radius:10px;padding:14px 18px;margin-top:14px;display:flex;align-items:center;flex-wrap:wrap;gap:12px}
.total-lbl{font-size:13px;color:var(--orange)}
.total-p{font-size:26px;font-weight:800;color:var(--red)}
.total-sub{font-size:12px;color:var(--sub)}
.trend-tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.ttab{padding:6px 13px;border-radius:7px;font-size:13px;font-weight:500;cursor:pointer;
  border:1.5px solid var(--border);background:#f8f9fc;color:var(--sub);transition:all .15s}
.ttab.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--sub);margin-bottom:10px}
.legend-item{display:flex;align-items:center;gap:5px}
.lline{width:20px;height:3px;border-radius:2px;display:inline-block}
canvas{width:100%;border-radius:8px;background:#fafbff;display:block}
.nodata{text-align:center;padding:40px;color:var(--sub);font-size:13px}
.status{padding:12px 16px;border-radius:10px;margin-bottom:18px;font-weight:700}
.status.low{background:#fee2e2;color:#991b1b;border:1px solid #fecaca}
.status.normal{background:#eef2ff;color:#3730a3;border:1px solid #c7d2fe}
.muted{color:var(--sub);font-size:12px}
.action-link{color:var(--accent);font-weight:600;text-decoration:none}
.action-link:hover{text-decoration:underline}
.footer{text-align:center;color:#b0b7c3;font-size:12px;padding:20px 0 0}
"""

JS_TPL = r"""
const TD=$TREND_DATA;const CM=$COLOR_MAP;const NM=$NAME_MAP;
var allDates=Object.keys(TD).sort(),idx=0;
var cv=document.getElementById('cv'),nd=document.getElementById('nd'),ctx=cv?cv.getContext('2d'):null;
function tabs(){var el=document.getElementById('tabs');if(!el)return;el.innerHTML='';
  allDates.forEach(function(d,i){var b=document.createElement('button');
    b.className='ttab'+(i===idx?' active':'');b.textContent=d;
    b.onclick=function(){idx=i;tabs();draw(d)};el.appendChild(b)})}
function draw(date){if(!ctx)return;var dd=TD[date]||{};
  var ps=Object.keys(dd).filter(function(p){return dd[p]&&dd[p].length>0});
  if(!ps.length){cv.style.display='none';nd.style.display='block';legend([]);return}
  cv.style.display='block';nd.style.display='none';
  var DPR=window.devicePixelRatio||1,W=cv.parentElement.offsetWidth||760,H=250;
  cv.width=W*DPR;cv.height=H*DPR;cv.style.width=W+'px';cv.style.height=H+'px';
  ctx.setTransform(DPR,0,0,DPR,0,0);ctx.clearRect(0,0,W,H);
  var PL=66,PR=20,PT=22,PB=50,pw=W-PL-PR,ph=H-PT-PB;
  var allTs=[],allV=[];ps.forEach(function(p){(dd[p]||[]).forEach(function(pt){allTs.push(pt.t);allV.push(pt.v)})});
  var tsU=allTs.filter(function(v,i,a){return a.indexOf(v)===i}).sort();
  var mn=Math.min.apply(null,allV),mx=Math.max.apply(null,allV),sp=mx-mn||1;
  var t0=new Date(tsU[0]).getTime(),tN=new Date(tsU[tsU.length-1]).getTime(),tSp=tN-t0||1;
  function tx(ts){return PL+pw*(new Date(ts).getTime()-t0)/tSp}
  function ty(v){return PT+ph*(1-(v-mn)/sp)}
  ctx.strokeStyle='#eef0f5';ctx.lineWidth=1;
  for(var g=0;g<=4;g++){var gy=PT+ph*(g/4);ctx.beginPath();ctx.moveTo(PL,gy);ctx.lineTo(W-PR,gy);ctx.stroke();
    ctx.fillStyle='#9ca3af';ctx.font='11px system-ui';ctx.textAlign='right';
    ctx.fillText('¥'+(mx-sp*(g/4)).toFixed(0),PL-8,gy+4)}
  ctx.fillStyle='#9ca3af';ctx.textAlign='center';ctx.font='10px system-ui';
  var sl=Math.max(1,Math.floor(tsU.length/7));
  tsU.forEach(function(ts,i){if(i%sl!==0&&i!==tsU.length-1)return;ctx.fillText(ts.slice(5,16),tx(ts),H-8)});
  ps.forEach(function(p){var pts=dd[p];if(!pts||!pts.length)return;var c=CM[p]||'#888';
    ctx.strokeStyle=c;ctx.lineWidth=2.5;ctx.lineJoin='round';ctx.lineCap='round';ctx.beginPath();
    pts.forEach(function(pt,i){var x=tx(pt.t),y=ty(pt.v);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();
    pts.forEach(function(pt){ctx.beginPath();ctx.arc(tx(pt.t),ty(pt.v),4,0,Math.PI*2);
      ctx.fillStyle=c;ctx.fill();ctx.beginPath();ctx.arc(tx(pt.t),ty(pt.v),2,0,Math.PI*2);
      ctx.fillStyle='#fff';ctx.fill()});
    var last=pts[pts.length-1];ctx.fillStyle=c;ctx.font='bold 12px system-ui';
    ctx.textAlign='left';ctx.fillText('¥'+last.v.toFixed(0),tx(last.t)+8,ty(last.v)-6)});
  legend(ps)}
function legend(ps){var el=document.getElementById('lg');if(!el)return;
  el.innerHTML=ps.map(function(p){return'<div class="legend-item"><span class="lline" style="background:'+(CM[p]||'#888')+'"></span><span>'+(NM[p]||p)+'</span></div>'}).join('')}
if(allDates.length){tabs();draw(allDates[0])}else{if(nd)nd.style.display='block';if(cv)cv.style.display='none'}
window.addEventListener('resize',function(){if(allDates.length)draw(allDates[idx])});
"""


def e(s):
    return html_mod.escape(str(s))


def build_view_url(q, date, platform):
    fc, tc = q["from"]["code"], q["to"]["code"]
    fn, tn = q["from"].get("name", fc), q["to"].get("name", tc)
    if platform == "ctrip":
        return ("https://m.ctrip.com/html5/flight/taro/first?from=inner"
                f"&tripType=ONE_WAY&dcity={quote(fc)}&acity={quote(tc)}&ddate={quote(date)}")
    if platform == "tongcheng":
        return ("https://m.ly.com/ft/touch/book1?date=" + quote(date) +
                f"&an=1&cn=0&baby=0&fromcitycode={quote(fc)}&fromCode={quote(fc)}"
                f"&tocitycode={quote(tc)}&toCode={quote(tc)}&cabin=0&platcode=518&frompage=HOME")
    if platform == "qunar":
        return ("https://touch.qunar.com/ncs/page/flightlist?depCity=" + quote(fn) +
                f"&arrCity={quote(tn)}&goDate={quote(date)}&from=touch_index_search"
                "&child=0&baby=0&cabinType=0")
    if platform == "tuniu":
        return (f"https://m.tuniu.com/flight/domestic/new/{quote(fc)}_{quote(tc)}_OW_1_0_0"
                f"?deptDate={quote(date)}&isGo=0")
    return ("https://outfliggys.m.taobao.com/app/trip/rx-flight-eco/pages/listing"
            f"?depCityCode={quote(fc)}&arrCityCode={quote(tc)}&leaveDate={quote(date)}"
            "&adultPassengerNum=1&searchType=1")


def render(q, summary, trend, health=None, calendar=None, status="not_low"):
    fn, fc = q["from"]["name"], q["from"]["code"]
    tn, tc = q["to"]["name"],   q["to"]["code"]
    platforms = q["platforms"]
    platform_desc = "、".join(PLATFORM_NAMES.get(p, p) for p in platforms)

    # 列头
    def th(p):
        c = PLATFORM_COLORS.get(p, "#888")
        n = PLATFORM_NAMES.get(p, p)
        return f"<th><span class='dot' style='background:{c}'></span>{e(n)}</th>"
    ths = "".join(th(p) for p in platforms)
    health = health or []
    calendar = calendar or []

    # 表体
    rows_html = []
    for s in summary:
        is_r = s["from"] == tc
        cells = ""
        for p in platforms:
            pr = s["per_platform"].get(p)
            if pr is None:
                cells += "<td class='na'>—</td>"
            elif pr == s["min_price"]:
                cells += f"<td class='best'>¥{pr:.0f}</td>"
            else:
                cells += f"<td>¥{pr:.0f}</td>"
        bc = PLATFORM_COLORS.get(s["best_platform"], "#888")
        bn = PLATFORM_NAMES.get(s["best_platform"], s["best_platform"])
        view_url = build_view_url(q, s["date"], s["best_platform"])
        flight_html = (f"<a class='action-link' target='_blank' rel='noopener' href='{e(view_url)}'>"
                       f"{e(s['best_flight'] or '查看平台低价')}</a>")
        rows_html.append(
            f"<tr>"
            f"<td><span class='{'tag-r' if is_r else 'tag-d'}'>{'回程' if is_r else '去程'}</span> {e(s['date'])}</td>"
            f"{cells}"
            f"<td class='best'>¥{s['min_price']:.0f}</td>"
            f"<td>{flight_html}<br><span class='badge' style='background:{bc}'>{e(bn)}</span></td>"
            f"<td class='time'>{e(s['best_depart_time'])}<br>→ {e(s['best_arrive_time'])}<br>"
            f"含税 ¥{e(s.get('tax') or '未知')} · 行李 {e(s.get('baggage') or '未知')} · 余票 {e(s.get('seats') or '未知')}</td>"
            f"</tr>"
        )

    # 往返合计
    ob = [s for s in summary if s["from"] == fc]
    ib = [s for s in summary if s["from"] == tc]
    total_html = ""
    if ob and ib:
        bo = min(ob, key=lambda s: s["min_price"])
        bi = min(ib, key=lambda s: s["min_price"])
        tot = bo["min_price"] + bi["min_price"]
        total_html = (
            f"<div class='total'>"
            f"<span class='total-lbl'>往返合计最低</span>"
            f"<span class='total-p'>¥{tot:.0f}</span>"
            f"<span class='total-sub'>去程 {e(bo['date'])} ¥{bo['min_price']:.0f} ＋ 回程 {e(bi['date'])} ¥{bi['min_price']:.0f}</span>"
            f"</div>"
        )

    # trend 过滤到本次日期
    all_dates = sorted({s["date"] for s in summary})
    trend_filtered = {d: trend.get(d, {}) for d in all_dates}
    all_plat = sorted({p for d in trend_filtered.values() for p in d})
    cm = {p: PLATFORM_COLORS.get(p, "#888") for p in all_plat}
    nm = {p: PLATFORM_NAMES.get(p, p) for p in all_plat}

    status_class = "low" if status == "low_price" else "normal"
    status_text = "低价提醒" if status == "low_price" else "未低价提醒"
    threshold = float(q.get("threshold") or 0)
    low_summary = [s for s in summary if threshold > 0 and s.get("min_price", 10**9) <= threshold]
    low_link_html = ""
    if low_summary:
        low = min(low_summary, key=lambda s: s["min_price"])
        low_link_html = (f"<a class='action-link' target='_blank' rel='noopener' "
                         f"href='{e(build_view_url(q, low['date'], low['best_platform']))}'>"
                         f"立即查看 {e(PLATFORM_NAMES.get(low['best_platform'], low['best_platform']))} 最低价 ¥{low['min_price']:.0f}</a>")
    nearby = q.get("nearby_airports", {})
    nearby_text = f"出发机场：{' / '.join(nearby.get('from', [fc]))}　到达机场：{' / '.join(nearby.get('to', [tc]))}"
    cal_rows = []
    for item in calendar:
        price = f"¥{item['min_price']:.0f}" if item.get("min_price") is not None else "暂无价格"
        base = f"¥{item['baseline']:.0f}" if item.get("baseline") is not None else "—"
        sig = item.get("signal", "—")
        cal_rows.append(f"<tr><td>{e(item.get('date'))}</td><td class='{'best' if sig == '偏低' else ''}'>{price}</td><td>{base}</td><td>{e(sig)}</td><td>{e(item.get('forecast', '暂无预测'))}</td><td>{e(PLATFORM_NAMES.get(item.get('best_platform'), item.get('best_platform') or '—'))}</td></tr>")
    health_rows = []
    for item in health:
        health_rows.append(f"<tr><td>{e(PLATFORM_NAMES.get(item.get('platform'), item.get('platform')))}</td><td>{e(item.get('dates_ok', 0))}/{e(item.get('dates_expected', 0))}</td><td>{e(item.get('success_rate', 0))}%</td><td>{e(item.get('status', '—'))}</td><td>{e(item.get('last_checked', '—'))}</td></tr>")

    js = Template(JS_TPL).substitute(
        TREND_DATA=json.dumps(trend_filtered, ensure_ascii=False),
        COLOR_MAP=json.dumps(cm, ensure_ascii=False),
        NAME_MAP=json.dumps(nm, ensure_ascii=False),
    )

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>机票比价 · {e(fn)}⇄{e(tn)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="page">
  <div class="hero">
    <h1>✈️ {e(fn)}（{e(fc)}）⇄ {e(tn)}（{e(tc)}）</h1>
    <div class="sub">机票多平台价格监控 · {e(q['query_time'])} · 数据仅供参考</div>
  </div>
  <div class="status {status_class}">{status_text} <span class="muted">· 本轮报告每次运行都会更新</span>{('<br>'+low_link_html) if low_link_html else ''}</div>
  <div class="card"><div class="card-title">附近机场组合</div><div>{e(nearby_text)}</div></div>
  <div class="card">
    <div class="card-title">📊 比价结果</div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>航线/日期</th>{ths}<th>最低价</th><th>最低价航班</th><th>起降时间</th></tr></thead>
        <tbody>{''.join(rows_html)}</tbody>
      </table>
    </div>
    {total_html}
  </div>
  <div class="card">
    <div class="card-title">低价日历 · 历史基线 · 价格预测</div>
    <div class="table-wrap"><table><thead><tr><th>日期</th><th>当前最低</th><th>历史中位数</th><th>信号</th><th>预测</th><th>最佳平台</th></tr></thead>
    <tbody>{''.join(cal_rows) or '<tr><td colspan="6" class="nodata">暂无日期数据</td></tr>'}</tbody></table></div>
  </div>
  <div class="card">
    <div class="card-title">平台健康度与降级状态</div>
    <div class="table-wrap"><table><thead><tr><th>平台</th><th>覆盖日期</th><th>成功率</th><th>状态</th><th>最近检查</th></tr></thead>
    <tbody>{''.join(health_rows) or '<tr><td colspan="5" class="nodata">暂无健康度数据</td></tr>'}</tbody></table></div>
  </div>
  <div class="card">
    <div class="card-title">📈 价格走势（近7天，多平台）</div>
    <div class="trend-tabs" id="tabs"></div>
    <div class="legend" id="lg"></div>
    <canvas id="cv" height="250"></canvas>
    <div class="nodata" id="nd" style="display:none">暂无足够历史数据，随监控积累后将显示</div>
  </div>
  <div class="footer">由 flight-price-monitor 自动生成 · {e(platform_desc)} · 以实际购票页面为准</div>
</div>
<script>{js}</script>
</body>
</html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-file", required=True)
    ap.add_argument("--out-dir", default="docs/data")
    args = ap.parse_args()

    rf = Path(args.results_file).expanduser()
    if not rf.exists():
        print(f"results file {rf} not found, skipping")
        return
    payload = json.loads(rf.read_text(encoding="utf-8"))
    if not payload.get("ok"):
        print("payload not ok, skipping")
        return
    data = payload["data"]
    trend = data.get("trend", {})

    out = Path(args.out_dir) / "report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data["query"], data.get("summary", []), trend,
                          data.get("health"), data.get("calendar"), data.get("status", "not_low")), encoding="utf-8")
    print(f"Report → {out}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)
