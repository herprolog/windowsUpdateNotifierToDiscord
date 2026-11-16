
import os
import re
import json
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# Microsoft公式サイト
SOURCE_URL = (
    "https://learn.microsoft.com/ja-jp/"
    "windows/release-health/windows11-release-information"
)

# 前回確認した更新情報
STATE_FILE = Path("last_updates.json")

# Discord Webhook（GitHub Secretsから取得）
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")


def get_updates():
    """Microsoft公式ページからWindows 11の更新情報を取得"""

    response = requests.get(
        SOURCE_URL,
        timeout=30,
        headers={"User-Agent": "WindowsUpdateNotifier/1.0"}
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    updates = {}

    # KB番号が記載された更新履歴テーブルを取得
    for table in soup.find_all("table"):

        rows = table.find_all("tr")
        if not rows:
            continue

        header_text = " ".join(
            cell.get_text(" ", strip=True)
            for cell in rows[0].find_all(["th", "td"])
        )

        # Windows 11の更新履歴テーブルだけを対象にする
        if (
            "サポート技術情報の記事" not in header_text
            and "KB article" not in header_text
        ):
            continue

        heading = table.find_previous(["h2", "h3", "h4"])
        version = (
            heading.get_text(" ", strip=True)
            if heading else "Windows 11"
        )

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            row_text = " | ".join(
                cell.get_text(" ", strip=True)
                for cell in cells
            )

            kb_matches = re.findall(
                r"\bKB\d{7,8}\b",
                row_text,
                re.IGNORECASE
            )

            if not kb_matches:
                continue

            kb = kb_matches[0].upper()

            # 更新情報へのリンクを取得
            link = None
            for a in row.find_all("a", href=True):
                if kb.lower() in a.get_text(" ", strip=True).lower():
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
                "details": row_text,
                "url": link
            }

    if not updates:
        raise RuntimeError(
            "更新情報を取得できませんでした。"
            "Microsoft公式ページの構造が変わった可能性があります。"
        )

    return updates


def load_previous():
    """前回の更新情報を読み込む"""

    if not STATE_FILE.exists():
        return None

    with STATE_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_updates(updates):
    """今回の更新情報を保存する"""

    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            updates,
            f,
            ensure_ascii=False,
            indent=2
        )


def send_discord(new_updates):
    """新しい更新をDiscordに通知"""

    if not WEBHOOK_URL:
        raise RuntimeError(
            "DISCORD_WEBHOOK_URLが設定されていません。"
        )

    messages = []

    for update in new_updates:
        message = (
            "**【Windows 11 新規アップデート公開】**\n"
            f"KB番号：{update['kb']}\n"
            f"対象：{update['version']}\n"
            f"詳細：{update['details']}\n"
            f"公式情報：{update['url']}"
        )
        messages.append(message)

    # Discordの文字数制限に合わせて分割
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
                "allowed_mentions": {"parse": []}
            },
            timeout=30
        )
        response.raise_for_status()


def main():
    print("Windows 11の更新情報を確認します。")

    current = get_updates()
    previous = load_previous()

    # 初回実行は現在の情報を記録するだけ
    if previous is None:
        save_updates(current)
        print("初回実行：既存の更新情報を記録しました。")
        return

    # 前回存在しなかったKB番号を検出
    new_updates = [
        update
        for kb, update in current.items()
        if kb not in previous
    ]

    if new_updates:
        print(f"{len(new_updates)}件の新しい更新を検出しました。")

        # 通知に成功してから状態を更新
        send_discord(new_updates)
        print("Discordへの通知が完了しました。")

    else:
        print("新しい更新はありません。")

    save_updates(current)
    print("確認完了。")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"エラー：{error}", file=sys.stderr)
        sys.exit(1)
