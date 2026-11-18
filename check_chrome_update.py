
import os
import json
import sys
import re
from pathlib import Path
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests
from html import unescape
from html.parser import HTMLParser


# Google Chrome公式のStable updates RSS
SOURCE_URL = (
    "https://chromereleases.googleblog.com/"
    "feeds/posts/default/-/Stable%20updates?alt=rss"
)

# 通知履歴
STATE_FILE = Path("last_chrome_updates.json")

# Discord Webhook
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")


class TextExtractor(HTMLParser):
    """HTMLからテキストを取り出す"""

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def get_text(self):
        return " ".join(self.parts).strip()


def clean_html(value):
    """HTMLタグを除去して文字列にする"""

    parser = TextExtractor()
    parser.feed(unescape(value))
    return re.sub(r"\s+", " ", parser.get_text())


def get_updates():
    """Google公式RSSからChromeの正式版更新情報を取得"""

    response = requests.get(
        SOURCE_URL,
        timeout=30,
        headers={
            "User-Agent": "ChromeUpdateNotifier/1.0"
        }
    )
    response.raise_for_status()

    root = ElementTree.fromstring(response.content)

    updates = []

    for item in root.findall(".//item"):
        title = item.findtext("title", default="").strip()

        # Windows / Mac / Linux向け正式版のみ対象
        if title != "Stable Channel Update for Desktop":
            continue

        link = item.findtext("link", default="").strip()
        guid = item.findtext("guid", default=link).strip()
        pub_date = item.findtext("pubDate", default="").strip()
        description = item.findtext(
            "description",
            default=""
        )

        if not link or not guid or not pub_date:
            continue

        try:
            published = parsedate_to_datetime(pub_date)
        except (TypeError, ValueError):
            continue

        updates.append({
            "id": guid,
            "title": title,
            "published": published.isoformat(),
            "published_text": published.strftime(
                "%Y年%m月%d日 %H:%M"
            ),
            "details": clean_html(description),
            "url": link
        })

    if not updates:
        raise RuntimeError(
            "Chrome公式RSSから正式版の更新情報を取得できませんでした。"
            "RSSの構造や配信状況を確認してください。"
        )

    # 新しい順に並べる
    updates.sort(
        key=lambda x: x["published"],
        reverse=True
    )

    print(f"取得したChrome更新情報：{len(updates)}件")

    return updates


def load_previous():
    """通知済みの更新情報を読み込む"""

    if not STATE_FILE.exists():
        return []

    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            notified = data.get("notified", [])

            if isinstance(notified, list):
                return notified

        return []

    except (json.JSONDecodeError, OSError) as error:
        raise RuntimeError(
            f"通知履歴を読み込めませんでした：{error}"
        )


def save_updates(notified):
    """通知履歴を保存する"""

    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            {"notified": notified},
            f,
            ensure_ascii=False,
            indent=2
        )


def send_discord(updates):
    """DiscordにChromeの更新情報を通知する"""

    if not WEBHOOK_URL:
        raise RuntimeError(
            "DISCORD_WEBHOOK_URLが設定されていません。"
        )

    for update in updates:
        details = update["details"]

        # Discordの文字数制限対策
        if len(details) > 1000:
            details = details[:1000] + "..."

        message = (
            "**【Google Chrome 正式版アップデート】**\n"
            f"公開日時：{update['published_text']}\n"
            f"更新情報：{update['title']}\n"
            f"詳細：{details}\n"
            f"公式情報：{update['url']}"
        )

        response = requests.post(
            WEBHOOK_URL,
            json={
                "content": message,
                "allowed_mentions": {
                    "parse": []
                }
            },
            timeout=30
        )

        response.raise_for_status()

    print("Discordへの通知が完了しました。")


def main():
    print("Google Chromeの更新情報を確認します。")

    current = get_updates()
    previous = load_previous()

    previous_set = set(previous)

    # 初回実行時は最新の1件だけ通知する
    if not previous:
        new_updates = current[:1]

        # 初回に取得した過去の情報をすべて既知として扱う
        updated_history = [
            update["id"] for update in current
        ]

        print("初回実行のため、最新の1件を通知対象にします。")

    else:
        new_updates = [
            update
            for update in current
            if update["id"] not in previous_set
        ]

        updated_history = list(previous)

        updated_history.extend(
            update["id"] for update in new_updates
        )

    if not new_updates:
        print("新しいChrome更新情報はありません。")
        return

    print(f"新しい更新情報：{len(new_updates)}件")

    # 通知が成功してから履歴を保存する
    send_discord(new_updates)

    # 重複を除去し、直近500件を保存
    updated_history = list(dict.fromkeys(updated_history))
    updated_history = updated_history[-500:]

    save_updates(updated_history)

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
