
import json
import os
import requests
from pathlib import Path

VERSION_API = (
    "https://product-details.mozilla.org/1.0/firefox_versions.json"
)

HISTORY_FILE = Path("last_firefox_updates.json")
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]


def get_update():
    response = requests.get(VERSION_API, timeout=30)
    response.raise_for_status()

    data = response.json()
    version = data.get("LATEST_FIREFOX_VERSION")

    if not version:
        raise RuntimeError("Firefoxのバージョンを取得できませんでした")

    return {
        "id": version,
        "version": version,
        "url": (
            f"https://www.firefox.com/en-US/firefox/"
            f"{version}/releasenotes/"
        )
    }


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
        "🟠 **Mozilla Firefox のアップデート情報**\n"
        f"バージョン：{update['version']}\n"
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
    update = get_update()
    notified = load_history()

    if update["id"] in notified:
        print("新しいFirefoxの更新はありません")
        return

    send_discord(update)
    notified.append(update["id"])
    save_history(notified)


if __name__ == "__main__":
    main()
