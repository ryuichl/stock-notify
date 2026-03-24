"""
監控標的與 200 日均線的關係，在關鍵時刻建立 GitHub Issue 通知。

監控標的：QQQ、0050.TW
通知時機：
1. 跌破 200MA（第 1 天）
2. 連續 1~3 天低於 200MA
3. 漲回 200MA（第 1 天）
4. 連續 1~3 天高於 200MA
"""

import sys
import subprocess
import yfinance as yf
import pandas as pd


# ── 監控清單 ──────────────────────────────────────────────
ALL_TARGETS = {
    "us": [
        {"ticker": "QQQ", "name": "QQQ", "currency": "$"},
    ],
    "tw": [
        {"ticker": "0050.TW", "name": "0050", "currency": "NT$"},
    ],
}


def get_status(ticker, name):
    """下載資料並計算 200MA 狀態"""
    data = yf.download(ticker, period="2y", progress=False)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    data["MA200"] = data["Close"].rolling(200).mean()
    data.dropna(inplace=True)
    data["above"] = data["Close"] > data["MA200"]

    recent = data.tail(10).copy().reset_index()

    today = recent.iloc[-1]
    today_above = bool(today["above"])
    today_close = float(today["Close"])
    today_ma200 = float(today["MA200"])
    today_date = today["Date"].strftime("%Y-%m-%d")
    diff_pct = (today_close / today_ma200 - 1) * 100

    # 連續幾天在同一側
    streak = 1
    current_side = recent.iloc[-1]["above"]
    for i in range(len(recent) - 2, -1, -1):
        if recent.iloc[i]["above"] == current_side:
            streak += 1
        else:
            break

    yesterday_above = bool(recent.iloc[-2]["above"]) if len(recent) >= 2 else today_above

    return {
        "name": name,
        "date": today_date,
        "close": today_close,
        "ma200": today_ma200,
        "diff_pct": diff_pct,
        "above": today_above,
        "yesterday_above": yesterday_above,
        "streak": streak,
    }


def create_issue(title, body):
    """用 gh CLI 建立 GitHub Issue，並指派給 repo owner 以觸發 email 通知"""
    cmd = [
        "gh", "issue", "create",
        "--title", title,
        "--body", body,
        "--assignee", "ryuichl",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  Issue 已建立: {result.stdout.strip()}")
    else:
        print(f"  建立 Issue 失敗: {result.stderr}")


def check_alerts(status, currency):
    """根據狀態產生通知列表"""
    name = status["name"]
    alerts = []

    # 1. 今天跌破 200MA
    if status["yesterday_above"] and not status["above"]:
        alerts.append({
            "title": f"⚠️ {name} 跌破 200MA ({status['date']})",
            "emoji": "⚠️",
            "event": "跌破 200 日均線（第 1 天）",
            "action": "開始觀察，連續 3 天則確認趨勢轉換",
        })

    # 2. 連續 1~3 天低於 200MA
    if not status["above"] and 1 <= status["streak"] <= 3:
        labels = {1: "第 1 天", 2: "第 2 天", 3: "第 3 天 ✅ 確認"}
        urgency = {1: "🟡", 2: "🟠", 3: "🔴"}
        action_map = {
            1: "持續觀察中",
            2: "明天若仍低於 200MA 將觸發 3 天確認訊號",
            3: "3 天確認訊號觸發！考慮操作",
        }
        if status["streak"] >= 2 or not (status["yesterday_above"] and not status["above"]):
            alerts.append({
                "title": f"{urgency[status['streak']]} {name} 低於 200MA {labels[status['streak']]} ({status['date']})",
                "emoji": urgency[status["streak"]],
                "event": f"低於 200 日均線（{labels[status['streak']]}）",
                "action": action_map[status["streak"]],
            })

    # 3. 今天漲回 200MA
    if not status["yesterday_above"] and status["above"]:
        alerts.append({
            "title": f"📈 {name} 漲回 200MA ({status['date']})",
            "emoji": "📈",
            "event": "漲回 200 日均線（第 1 天）",
            "action": "開始觀察，連續 3 天則確認趨勢轉換",
        })

    # 4. 連續 1~3 天高於 200MA
    if status["above"] and 1 <= status["streak"] <= 3:
        labels = {1: "第 1 天", 2: "第 2 天", 3: "第 3 天 ✅ 確認"}
        urgency = {1: "📈", 2: "📊", 3: "🟢"}
        action_map = {
            1: "持續觀察中",
            2: "明天若仍高於 200MA 將觸發 3 天確認訊號",
            3: "3 天確認訊號觸發！考慮操作",
        }
        if status["streak"] >= 2 or not (not status["yesterday_above"] and status["above"]):
            alerts.append({
                "title": f"{urgency[status['streak']]} {name} 站上 200MA {labels[status['streak']]} ({status['date']})",
                "emoji": urgency[status["streak"]],
                "event": f"高於 200 日均線（{labels[status['streak']]}）",
                "action": action_map[status["streak"]],
            })

    return alerts


def main():
    # 支援命令列參數: us, tw, all (預設 all)
    market = sys.argv[1] if len(sys.argv) > 1 else "all"

    if market == "all":
        watchlist = [item for group in ALL_TARGETS.values() for item in group]
    elif market in ALL_TARGETS:
        watchlist = ALL_TARGETS[market]
    else:
        print(f"未知市場: {market}，可用: {', '.join(ALL_TARGETS.keys())}, all")
        sys.exit(1)

    for item in watchlist:
        ticker = item["ticker"]
        name = item["name"]
        currency = item["currency"]

        print(f"\n{'='*50}")
        print(f"  檢查 {name} ({ticker})")
        print(f"{'='*50}")

        status = get_status(ticker, name)

        print(f"  日期: {status['date']}")
        print(f"  收盤: {currency}{status['close']:.2f}")
        print(f"  200MA: {currency}{status['ma200']:.2f}")
        print(f"  差距: {status['diff_pct']:+.2f}%")
        print(f"  位於 200MA {'上方' if status['above'] else '下方'}")
        print(f"  連續 {status['streak']} 天在{'上方' if status['above'] else '下方'}")

        alerts = check_alerts(status, currency)

        if not alerts:
            print("  無需通知，目前無觸發條件。")
            continue

        for alert in alerts:
            body = f"""## {alert['emoji']} {name} — {alert['event']}

| 項目 | 數值 |
|------|------|
| 日期 | {status['date']} |
| {name} 收盤價 | {currency}{status['close']:.2f} |
| 200 日均線 | {currency}{status['ma200']:.2f} |
| 差距 | {status['diff_pct']:+.2f}% |
| 連續天數 | {status['streak']} 天在{'上方' if status['above'] else '下方'} |

### 建議動作
{alert['action']}

---
*此通知由 GitHub Actions 自動產生*
"""
            print(f"  觸發通知: {alert['title']}")
            create_issue(alert["title"], body)


if __name__ == "__main__":
    main()
