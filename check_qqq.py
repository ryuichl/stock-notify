"""
檢查 QQQ 與 200 日均線的關係，在關鍵時刻建立 GitHub Issue 通知。

通知時機：
1. 今天跌破 200MA（第 1 天跌破）
2. 連續 3 天低於 200MA
3. 今天漲回 200MA（第 1 天漲回）
4. 連續 3 天高於 200MA
"""

import os
import json
import subprocess
import yfinance as yf
import pandas as pd
from datetime import datetime


def get_qqq_status():
    """下載 QQQ 資料並計算 200MA 狀態"""
    qqq = yf.download("QQQ", period="2y", progress=False)
    if isinstance(qqq.columns, pd.MultiIndex):
        qqq.columns = qqq.columns.get_level_values(0)

    qqq["MA200"] = qqq["Close"].rolling(200).mean()
    qqq.dropna(inplace=True)
    qqq["above"] = qqq["Close"] > qqq["MA200"]

    # 計算連續天數
    recent = qqq.tail(10).copy()
    recent = recent.reset_index()

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

    # 昨天的狀態
    yesterday_above = bool(recent.iloc[-2]["above"]) if len(recent) >= 2 else today_above

    return {
        "date": today_date,
        "close": today_close,
        "ma200": today_ma200,
        "diff_pct": diff_pct,
        "above": today_above,
        "yesterday_above": yesterday_above,
        "streak": streak,
    }


def create_issue(title, body):
    """用 gh CLI 建立 GitHub Issue"""
    result = subprocess.run(
        ["gh", "issue", "create", "--title", title, "--body", body],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"Issue 已建立: {result.stdout.strip()}")
    else:
        print(f"建立 Issue 失敗: {result.stderr}")


def main():
    status = get_qqq_status()

    print(f"日期: {status['date']}")
    print(f"QQQ 收盤: ${status['close']:.2f}")
    print(f"200MA: ${status['ma200']:.2f}")
    print(f"差距: {status['diff_pct']:+.2f}%")
    print(f"位於 200MA {'上方' if status['above'] else '下方'}")
    print(f"連續 {status['streak']} 天在{'上方' if status['above'] else '下方'}")

    # 判斷通知時機
    alerts = []

    # 1. 今天跌破 200MA（昨天在上方，今天在下方）
    if status["yesterday_above"] and not status["above"]:
        alerts.append({
            "title": f"⚠️ QQQ 跌破 200MA ({status['date']})",
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
            3: "3 天確認訊號觸發！考慮賣出 TQQQ 換入替代標的",
        }
        # 第 1 天跌破已有獨立通知，連續天數從第 2 天開始通知避免重複
        if status["streak"] >= 2 or not (status["yesterday_above"] and not status["above"]):
            alerts.append({
                "title": f"{urgency[status['streak']]} QQQ 低於 200MA {labels[status['streak']]} ({status['date']})",
                "emoji": urgency[status["streak"]],
                "event": f"低於 200 日均線（{labels[status['streak']]}）",
                "action": action_map[status["streak"]],
            })

    # 3. 今天漲回 200MA（昨天在下方，今天在上方）
    if not status["yesterday_above"] and status["above"]:
        alerts.append({
            "title": f"📈 QQQ 漲回 200MA ({status['date']})",
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
            3: "3 天確認訊號觸發！考慮買回 TQQQ",
        }
        if status["streak"] >= 2 or not (not status["yesterday_above"] and status["above"]):
            alerts.append({
                "title": f"{urgency[status['streak']]} QQQ 站上 200MA {labels[status['streak']]} ({status['date']})",
                "emoji": urgency[status["streak"]],
                "event": f"高於 200 日均線（{labels[status['streak']]}）",
                "action": action_map[status["streak"]],
            })

    if not alerts:
        print("\n無需通知，目前無觸發條件。")
        return

    for alert in alerts:
        body = f"""## {alert['emoji']} {alert['event']}

| 項目 | 數值 |
|------|------|
| 日期 | {status['date']} |
| QQQ 收盤價 | ${status['close']:.2f} |
| 200 日均線 | ${status['ma200']:.2f} |
| 差距 | {status['diff_pct']:+.2f}% |
| 連續天數 | {status['streak']} 天在{'上方' if status['above'] else '下方'} |

### 建議動作
{alert['action']}

---
*此通知由 GitHub Actions 自動產生*
"""
        print(f"\n觸發通知: {alert['title']}")
        create_issue(alert["title"], body)


if __name__ == "__main__":
    main()
