
import os
import re
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# Microsoft公式サイト
SOURCE_URL = (
    "https://learn.microsoft.com/ja-jp/"
    "windows/release-health/windows11-release-information"
)

# 通知済みの更新情報
STATE_FILE = Path("last_updates.json")

# Discord Webhook
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 日本時間
JST = ZoneInfo("Asia/Tokyo")


def get_yesterday():
    """日本時間で昨日の日付を取得"""
    return (
        datetime.now(JST).date() - timedelta(days=1)
    ).isoformat()


def get_updates():
    """Microsoft公式ページから更新情報を取得"""

    response = requests.get(
        SOURCE_URL,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0 WindowsUpdateNotifier/1.0",
            "Accept-Charset": "utf-8"
        }
    )
    response.raise_for_status()

    # 文字化け防止：UTF-8として明示的に読み込む
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")

    updates = {}

    for table in soup.find_all("table"):
        rows = table.find_all("tr")

        if not rows:
            continue

        # ヘッダー行を取得
        header_row = next(
            (row for row in rows if row.find("th")),
            None
        )

        if header_row is None:
            continue

        headers = [
            cell.get_text(" ", strip=True)
            for cell in header_row.find_all(["th", "td"])
        ]

        # 公開日列を探す
        date_index = next(
            (
                i for i, header in enumerate(headers)
                if "公開日" in header
            ),
            None
        )

        if date_index is None:
            continue

        heading = table.find_previous(["h2", "h3", "h4"])

        version = (
            heading.get_text(" ", strip=True)
            if heading else "Windows 11"
        )

        for row in rows:
            cells = row.find_all(["td", "th"])

            if len(cells) <= date_index:
                continue

            row_text = " | ".join(
                cell.get_text(" ", strip=True)
                for cell in cells
            )

            # KB番号を取得
            kb_matches = re.findall(
                r"\bKB\d{7,8}\b",
                row_text,
                re.IGNORECASE
            )

            if not kb_matches:
                continue

            kb = kb_matches[0].upper()

            # 公開日を取得
            date_text = cells[date_index].get_text(
                " ", strip=True
            )

            date_match = re.search(
                r"\d{4}-\d{2}-\d{2}",
                date_text
            )

            if not date_match:
                continue

            published_date = date_match.group(0)

            # 更新情報へのリンクを取得
            link = None

            for a in row.find_all("a", href=True):
                if kb.lower() in a.get_text(
                    " ", strip=True
                ).lower():
                    link = urljoin(SOURCE_URL, a["href"])
                    break

            if not link:
                link = (
                    "https://support.microsoft.com/help/"
                    + kb[2:]
                )

            updates[kb] = {
                "kb": kb,
                "version": version,
                "published_date": published_date,
                "details": row_text,
                "url": link
            }

    if not updates:
        raise RuntimeError(
            "更新情報を取得できませんでした。"
            "Microsoft公式ページの構造を確認してください。"
        )

    print(f"取得した更新情報：{len(updates)}件")

    return updates


def load_previous():
    """通知済みの更新情報を読み込む"""

    if not STATE_FILE.exists():
        return {}

    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        # 新形式のみ読み込む
        if isinstance(data, dict) and "notified" in data:
            return data["notified"]

        return {}

    except (json.JSONDecodeError, OSError):
        return {}


def save_updates(notified):
    """通知済みの更新情報を保存"""

    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            {"notified": notified},
            f,
            ensure_ascii=False,
            indent=2
        )


def send_discord(new_updates):
    """Discordに更新情報を通知"""

    if not WEBHOOK_URL:
        raise RuntimeError(
            "DISCORD_WEBHOOK_URLが設定されていません。"
        )

    messages = []

    for update in new_updates:
        message = (
            "**【Windows 11 新規アップデート公開】**\n"
            f"公開日：{update['published_date']}\n"
            f"KB番号：{update['kb']}\n"
            f"対象：{update['version']}\n"
            f"詳細：{update['details']}\n"
            f"公式情報：{update['url']}"
        )

        messages.append(message)

    # Discordの文字数制限を考慮して分割
    chunks = []
    current = ""

    for message in messages:
        if current and len(current) + len(message) + 2 > 1900:
            chunks.append(current)
            current = ""

        current = (
            current + "\n\n" + message
            if current else message
        )

    if current:
        chunks.append(current)

    for chunk in chunks:
        response = requests.post(
            WEBHOOK_URL,
            json={
                "content": chunk,
                "allowed_mentions": {
                    "parse": []
                }
            },
            headers={
                "Content-Type": "application/json; charset=utf-8"
            },
            timeout=30
        )

        response.raise_for_status()


def main():
    yesterday = get_yesterday()

    print(f"Windows 11の更新情報を確認します。")
    print(f"通知対象の公開日：{yesterday}")

    current = get_updates()
    previous = load_previous()

    # 昨日公開された更新情報だけを抽出
    yesterday_updates = [
        update
        for update in current.values()
        if update["published_date"] == yesterday
    ]

    # すでに通知したKB番号を除外
    new_updates = [
        update
        for update in yesterday_updates
        if update["kb"] not in previous
    ]

    if not new_updates:
        print("昨日公開された新しい更新情報はありません。")
        return

    print(
        f"昨日公開された新しい更新情報："
        f"{len(new_updates)}件"
    )

    # Discord通知
    send_discord(new_updates)

    print("Discordへの通知が完了しました。")

    # 通知成功後に履歴を保存
    for update in new_updates:
        previous[update["kb"]] = update["published_date"]

    save_updates(previous)

    print("通知履歴を保存しました。")
    print("確認完了。")


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        print(
            f"エラー：{error}",
            file=sys.stderr
        )
        sys.exit(1)
