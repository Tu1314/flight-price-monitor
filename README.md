# ✈️ FlightRadar — 中国多平台机票价格监控

<div align="center">

**自动监控携程 / 飞猪 / 去哪儿 / 同程 / 途牛，每天多轮比价，降价微信提醒。**

[![GitHub Actions](https://github.com/zhanglong-ustc/flight-price-monitor/actions/workflows/monitor.yml/badge.svg)](https://github.com/zhanglong-ustc/flight-price-monitor/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://python.org)

[🌐 项目主页](https://zhanglong-ustc.github.io/flight-price-monitor) · [📋 示例报告](https://zhanglong-ustc.github.io/flight-price-monitor/data/report.html) · [🔀 Fork 使用](https://github.com/zhanglong-ustc/flight-price-monitor/fork)

</div>

---

## ✨ 功能一览

| 功能 | 说明 |
|------|------|
| 🔍 **五平台比价** | 飞猪/途牛（接口逆向）+ 携程/去哪儿/同程（Playwright 自动化） |
| 📅 **多日期对比** | 同时监控多个出发日期，自动挑出最便宜那天 |
| 📈 **价格走势图** | SQLite 历史入库，多平台叠加折线图，7天趋势一目了然 |
| 💬 **微信降价提醒** | Server酱推送，含价格/平台/航班/链接，推送去抖不轰炸 |
| ⚙️ **GitHub Actions** | 免费定时运行（每天4次），无需服务器，Fork即用 |
| 🌐 **自动生成报告** | 每轮抓取后自动生成 HTML 可视化报告，Push 到 GitHub Pages |

## 🚀 快速开始（5分钟）

### 方式一：GitHub Actions（推荐，无需服务器）

1. **Fork 本仓库**：点击右上角 [Fork](https://github.com/zhanglong-ustc/flight-price-monitor/fork)

2. **配置行程**：在 Actions 标签页手动触发时填入参数，或修改 `config.example.yaml` 后改名为 `config.yaml` 提交

3. **开启 GitHub Pages**：  
   Settings → Pages → Source 选 `Deploy from branch` → Branch 选 `main` / `docs` 文件夹

4. **配置微信提醒**（可选）：  
   - 访问 [sct.ftqq.com](https://sct.ftqq.com/) 扫码登录，获取 `SendKey`  
   - Settings → Secrets and variables → Actions → New repository secret  
   - Name: `SERVERCHAN_SEND_KEY`，Value: 你的 SendKey

5. **手动触发测试**：  
   Actions → `Flight Price Monitor` → `Run workflow` → 填入行程参数 → Run

### 方式二：本地运行

```bash
git clone https://github.com/zhanglong-ustc/flight-price-monitor.git
cd flight-price-monitor

# Python 3.12+（需要 uv 或直接 pip）
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium               # 携程/去哪儿/同程需要

# 配置
cp config.example.yaml config.yaml
# 编辑 config.yaml，修改航线和日期...

# 运行一次（测试用）
python main.py --once

# 定时运行（持续监控）
nohup python main.py &
```

## ⚙️ 配置说明

```yaml
routes:
  - from: LZO          # 出发地三字码
    from_name: 泸州
    to: BJS             # 目的地三字码
    to_name: 北京
    dates:
      - "2026-09-30"
      - "2026-10-01"
      - "2026-10-02"
    alert_threshold: 800  # 低于此价触发微信提醒（0 = 关闭）

  - from: BJS           # 回程
    from_name: 北京
    to: LZO
    to_name: 泸州
    dates:
      - "2026-10-06"
    alert_threshold: 800

platforms: [fliggy, tuniu, qunar, tongcheng]  # 可选: ctrip, fliggy, tuniu, qunar, tongcheng

notifier:
  push_drop_min: 30     # 降幅 ≥ 30元 才再次推送
  serverchan:
    enabled: true
    send_key: "SCTxxxxxxxxxx"
```

### 常用城市三字码

| 城市 | 代码 | 城市 | 代码 | 城市 | 代码 |
|------|------|------|------|------|------|
| 北京 | BJS | 上海 | SHA | 广州 | CAN |
| 深圳 | SZX | 成都 | CTU | 重庆 | CKG |
| 杭州 | HGH | 西安 | SIA | 昆明 | KMG |
| 泸州 | LZO | 厦门 | XMN | 武汉 | WUH |
| 南京 | NKG | 贵阳 | KWE | 三亚 | SYX |

## 📂 项目结构

```
flight-price-monitor/
├── main.py                    # 主入口（定时调度）
├── config.example.yaml        # 配置模板
├── requirements.txt
├── crawlers/                  # 各平台爬虫
│   ├── fliggy.py              # 飞猪（httpx 逆向）
│   ├── tuniu.py               # 途牛（httpx 逆向）
│   ├── ctrip.py               # 携程（Playwright）
│   ├── qunar.py               # 去哪儿（Playwright）
│   └── tongcheng.py           # 同程（Playwright）
├── core/                      # 核心模块
│   ├── models.py              # 数据模型
│   ├── storage.py             # SQLite 存储
│   ├── alerter.py             # 低价告警逻辑
│   ├── notifier.py            # Server酱推送
│   └── scheduler.py           # APScheduler 调度
├── scripts/
│   ├── build_config.py        # Actions 参数 → config.yaml
│   ├── export_results.py      # SQLite → JSON（供 Pages 用）
│   └── render_report.py       # JSON → HTML 可视化报告
├── .github/workflows/
│   └── monitor.yml            # GitHub Actions 工作流
└── docs/                      # GitHub Pages
    ├── index.html             # 项目介绍主页
    └── data/
        ├── latest.json        # 最新抓取结果（自动更新）
        └── report.html        # 可视化比价报告（自动更新）
```

## ⚠️ 注意事项

- 本项目仅用于**个人学习和出行参考**，请勿高频请求
- 爬虫可能因平台改版失效，如遇 `NO_RESULTS` 请查看 `debug/` 目录排查
- 途牛同 IP 每10分钟约3次成功后触发风控（属预期，飞猪兜底）
- 价格为含税最低价，与实付价可能有小幅差异，以购票页面为准

## 📄 License

MIT © 2026 [Long Zhang](https://zhanglong-ustc.github.io)
