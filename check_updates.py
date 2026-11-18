
import re
import sys
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup


# ==========================================
# 設定
# ==========================================

WEBHOOK_URL = None

WINDOWS_URL = (
    "https://learn.microsoft.com/en-us/"
    "windows/release-health/windows11-release-information"
)

CHROME_URL = (
    "https://chromereleases.googleblog.com/"
    "feeds/posts/default/-/Stable%20updates?alt=rss"
)

EDGE_URL = (
    "https://learn.microsoft.com/en-us/deployedge/"
    "microsoft-edge-relnote-stable-channel"
)

FIREFOX_URL = (
    "https://product-details.mozilla.org/1.0/firefox.json"
)

JST = ZoneInfo("Asia/Tokyo")

HEADERS = {
    "User-Agent": "DailyUpdateNotifier/1.0"
}

TIMEOUT = 30


# ==========================================
# 共通処理
# ==========================================

def get_yesterday():
    """日本時間で昨日の日付を取得する"""
    today = datetime.now(JST).date()
    return today - timedelta(days=1)


def get_page(url):
    """Webページを取得する"""
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT
    )
    response.raise_for_status()
    return response


def clean_text(value):
    """HTMLを除去して読みやすいテキストにする"""
    soup = BeautifulSoup(value or "", "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


# ==========================================
# Windows 11
# ==========================================

def get_windows_updates(target_date):
    print("Windows 11を確認中...")

    response = get_page(WINDOWS_URL)
    response.encoding = "utf-8"

    soup = BeautifulSoup(response.text, "html.parser")

    updates = []
    seen = set()

    for table in soup.find_all("table"):
        rows = table.find_all("tr")

        header_row = next(
            (row for row in rows if row.find("th")),
            None
        )

        if header_row is None:
            continue

        headers = [
            cell.get_text(" ", strip=True).lower()
            for cell in header_row.find_all(["th", "td"])
        ]

        date_index = next(
            (
                i for i, header in enumerate(headers)
                if "availability date" in header
            ),
            None
        )

        kb_index = next(
            (
                i for i, header in enumerate(headers)
                if "kb article" in header
            ),
            None
        )

        if date_index is None or kb_index is None:
            continue

        heading = table.find_previous(["h2", "h3", "h4"])

        version = (
            heading.get_text(" ", strip=True)
            if heading else "Windows 11"
        )

        for row in rows:
            cells = row.find_all(["td", "th"])

            if len(cells) <= max(date_index, kb_index):
                continue

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

            if published_date != target_date.isoformat():
                continue

            kb_text = cells[kb_index].get_text(
                " ", strip=True
            )

            kb_match = re.search(
                r"KB\d{6,8}",
                kb_text,
                re.IGNORECASE
            )

            if not kb_match:
                continue

            kb = kb_match.group(0).upper()

            key = (version, kb, published_date)

            if key in seen:
                continue

            seen.add(key)

            row_text = " | ".join(
                cell.get_text(" ", strip=True)
                for cell in cells
            )

            link = (
                f"https://support.microsoft.com/help/{kb[2:]}"
            )

            for a in row.find_all("a", href=True):
                if kb.lower() in a.get_text(
                    " ", strip=True
                ).lower():
                    link = a["href"]
                    break

            updates.append({
                "service": "Windows 11",
                "date": published_date,
                "title": f"{version} / {kb}",
                "details": row_text,
                "url": link
            })

    print(f"Windows 11: {len(updates)}件")

    return updates


# ==========================================
# Google Chrome
# ==========================================

def get_chrome_updates(target_date):
    print("Google Chromeを確認中...")

    response = get_page(CHROME_URL)

    root = ElementTree.fromstring(response.content)

    updates = []

    for item in root.findall(".//item"):
        title = item.findtext(
            "title", default=""
        ).strip()

        # デスクトップ版Stableのみ対象
        if title != "Stable Channel Update for Desktop":
            continue

        link = item.findtext(
            "link", default=""
        ).strip()

        pub_date = item.findtext(
            "pubDate", default=""
        ).strip()

        description = item.findtext(
            "description", default=""
        )

        if not link or not pub_date:
            continue

        try:
            published = parsedate_to_datetime(pub_date)
        except (TypeError, ValueError):
            continue

        # RSSに記載された公開日で判定
        published_date = published.date()

        if published_date != target_date:
            continue

        details = clean_text(description)

        version_match = re.search(
            r"\d+\.\d+\.\d+\.\d+",
            details
        )

        version = (
            version_match.group(0)
            if version_match else "バージョン情報なし"
        )

        updates.append({
            "service": "Google Chrome",
            "date": published_date.isoformat(),
            "title": f"Chrome {version}",
            "details": details,
            "url": link
        })

    print(f"Google Chrome: {len(updates)}件")

    return updates


# ==========================================
# Microsoft Edge
# ==========================================

def get_edge_updates(target_date):
    print("Microsoft Edgeを確認中...")

    response = get_page(EDGE_URL)
    soup = BeautifulSoup(response.text, "html.parser")

    updates = []

    pattern = re.compile(
        r"^Version\s+([\d.]+):\s*"
        r"([A-Za-z]+\s+\d{1,2},\s+\d{4})"
        r"\s+\(Stable\)"
        r"(?:\s*-\s*(.*))?$"
    )

    for heading in soup.find_all(["h2", "h3", "h4"]):
        heading_text = heading.get_text(
            " ", strip=True
        )

        match = pattern.match(heading_text)

        if not match:
            continue

        version = match.group(1)
        date_text = match.group(2)
        release_type = (match.group(3) or "").strip()

        try:
            published_date = datetime.strptime(
                date_text,
                "%B %d, %Y"
            ).date()
        except ValueError:
            continue

        if published_date != target_date:
            continue

        updates.append({
            "service": "Microsoft Edge",
            "date": published_date.isoformat(),
            "title": f"Edge {version}",
            "details": (
                release_type
                if release_type
                else "Stable Channel Update"
            ),
            "url": EDGE_URL
        })

    # 同じバージョンの重複を除去
    unique = {}

    for update in updates:
        unique[update["title"]] = update

    updates = list(unique.values())

    print(f"Microsoft Edge: {len(updates)}件")

    return updates


# ==========================================
# Mozilla Firefox
# ==========================================

def get_firefox_updates(target_date):
    print("Mozilla Firefoxを確認中...")

    response = get_page(FIREFOX_URL)
    data = response.json()

    releases = data.get("releases", {})

    updates = []

    for release in releases.values():
        if release.get("product") != "firefox":
            continue

        # 正式版のみ対象。Betaや開発版は除外
        if release.get("category") not in (
            "major",
            "stability"
        ):
            continue

        published_date = release.get("date")
        version = release.get("version")

        if not published_date or not version:
            continue

        if published_date != target_date.isoformat():
            continue

        updates.append({
            "service": "Mozilla Firefox",
            "date": published_date,
            "title": f"Firefox {version}",
            "details": "Firefox正式版のリリース",
            "url": (
                f"https://www.mozilla.org/en-US/firefox/"
                f"{version}/releasenotes/"
            )
        })

    print(f"Mozilla Firefox: {len(updates)}件")

    return updates


# ==========================================
# Discord通知
# ==========================================

def send_discord(updates, target_date):
    if not updates:
        print("昨日公開された更新情報はありません。")
        return

    import os

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")

    if not webhook_url:
        raise RuntimeError(
            "DISCORD_WEBHOOK_URLが設定されていません。"
        )

    messages = []

    messages.append(
        f"**【ソフトウェア更新情報】**\n"
        f"公開日：{target_date.isoformat()}\n"
        f"新規更新：{len(updates)}件"
    )

    for update in updates:
        details = update["details"]

        if len(details) > 900:
            details = details[:900] + "..."

        message = (
            f"\n\n**■ {update['service']}**\n"
            f"バージョン・内容：{update['title']}\n"
            f"詳細：{details}\n"
            f"公式情報：{update['url']}"
        )

        messages.append(message)

    # Discordの文字数制限に合わせて分割
    chunks = []
    current = ""

    for message in messages:
        if current and len(current) + len(message) > 1900:
            chunks.append(current)
            current = ""

        current += message

    if current:
        chunks.append(current)

    for chunk in chunks:
        response = requests.post(
            webhook_url,
            json={
                "content": chunk,
                "allowed_mentions": {
                    "parse": []
                }
            },
            timeout=TIMEOUT
        )

        response.raise_for_status()

    print("Discordへの通知が完了しました。")


# ==========================================
# メイン処理
# ==========================================

def main():
    target_date = get_yesterday()

    print("===================================")
    print("ソフトウェア更新情報チェック")
    print(f"確認対象日：{target_date}")
    print("===================================")

    all_updates = []
    errors = []

    checkers = [
        ("Windows 11", get_windows_updates),
        ("Google Chrome", get_chrome_updates),
        ("Microsoft Edge", get_edge_updates),
        ("Mozilla Firefox", get_firefox_updates)
    ]

    for name, checker in checkers:
        try:
            updates = checker(target_date)
            all_updates.extend(updates)

        except Exception as error:
            message = f"{name}の取得に失敗：{error}"
            print(message, file=sys.stderr)
            errors.append(message)

    print("-----------------------------------")
    print(f"合計更新件数：{len(all_updates)}")

    try:
        send_discord(all_updates, target_date)

    except Exception as error:
        print(
            f"Discord通知に失敗：{error}",
            file=sys.stderr
        )
        errors.append(f"Discord通知：{error}")

    if errors:
        raise RuntimeError(
            "一部の処理に失敗しました。\n"
            + "\n".join(errors)
        )

    print("すべての確認が完了しました。")


if __name__ == "__main__":
    main()
