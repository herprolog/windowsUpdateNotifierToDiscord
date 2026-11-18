
import json
import os
import re
import requests
from pathlib import Path
from bs4 import BeautifulSoup

RELEASE_URL = (
    "https://learn.microsoft.com/en-us/deployedge/"
    "microsoft-edge-relnote-stable-channel"
)
HISTORY_FILE = Path("last_edge_updates.json")
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]


def get_updates():
    response = requests.get(
        RELEASE_URL,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    page_text = soup.get_text("\n")

    updates = []
    pattern = re.compile(
        r"Version\s+([\d.]+):\s*([^\n]+)"
    )

    for match in pattern.finditer(page_text):
        version = match.group(1)
        description = match.group(2).strip()

        # Stableのみ対象。Extended Stableは除外
        if "(Stable)" not in description:
            continue

        if "Extended Stable" in description:
            continue

        updates.append({
            "id": version,
            "version": version,
            "description": description,
            "url": RELEASE_URL
        })

    # 同じバージョンの重複を除去
    unique = {}
    for update in updates:
        unique[update["id"]] = update

    return list(unique.values())


def load_history():
    if not HISTORY_FILE.exists():
        return []

    with HISTORY_FILE.open("r", encoding="utf-8") as f:
        return json.load(f).get("notified", [])


def save_history(notified):
    with HISTORY_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            {"notified": notified[-500:]},
            f,
            ensure_ascii=False,
            indent=2
        )


def send_discord(update):
    message = (
        "🔵 **Microsoft Edge のアップデート情報**\n"
        f"バージョン：{update['version']}\n"
        f"内容：{update['description']}\n"
        f"詳細：{update['url']}"
    )

    response = requests.post(
        WEBHOOK_URL,
        json={
            "content": message,
            "allowed_mentions": {"parse": []}
        },
        timeout=30
    )
    response.raise_for_status()


def main():
    updates = get_updates()

    if not updates:
        raise RuntimeError("Edgeの更新情報を取得できませんでした")

    notified = load_history()

    # 初回は最新情報だけ通知し、既存の履歴を登録
    if not notified:
        latest = updates[0]
        send_discord(latest)
        notified = [u["id"] for u in updates]
        save_history(notified)
        return

    new_updates = [
        u for u in updates
        if u["id"] not in notified
    ]

    for update in reversed(new_updates):
        send_discord(update)
        notified.append(update["id"])

    save_history(notified)


if __name__ == "__main__":
    main()
