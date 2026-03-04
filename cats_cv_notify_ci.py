#!/usr/bin/env python3
"""
CATs CV通知 + CV検索応答 → Discord（GitHub Actions用）
1分ごとに起動し、50秒の間20秒おきにチェックする
"""

import os
import re
import json
import time
import datetime
import requests
from typing import Optional, List, Dict, Any, Set

# ===== 設定（環境変数から取得） =====
CATS_LOGIN_URL = "https://admin.deneb.tokyo/front/login/confirm"
CATS_SEARCH_URL = "https://admin.deneb.tokyo/admin/actionlog/list/search"
CATS_LOGIN_ID = os.environ["CATS_LOGIN_ID"]
CATS_PASSWORD = os.environ["CATS_PASSWORD"]

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
DISCORD_CHANNEL_ID = os.environ["DISCORD_CHANNEL_ID"]
DISCORD_API_BASE = "https://discord.com/api/v10"

CHECK_INTERVAL = 20   # 20秒
RUN_DURATION = 50     # 50秒（1分のcronに収まるように）

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cats_last_check.json")

CIRCLED_NUMS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def normalize_text(text: str) -> str:
    """&/＆/&amp; やHTMLエンティティを正規化して比較用テキストを返す"""
    import html
    text = html.unescape(text)
    text = text.replace("＆", "&")
    return text


def cats_login(session: requests.Session) -> bool:
    resp = session.post(CATS_LOGIN_URL, data={
        "loginId": CATS_LOGIN_ID,
        "password": CATS_PASSWORD,
    }, allow_redirects=True, timeout=15)
    return resp.status_code == 200 and "ログイン" not in resp.text[:500]


def fetch_cv_logs(session: requests.Session, date_str: Optional[str] = None) -> List[Dict[str, Any]]:
    if date_str is None:
        today = datetime.date.today().strftime("%Y/%m/%d")
        date_str = f"{today} - {today}"

    resp = session.post(CATS_SEARCH_URL, data={
        "draw": "1",
        "start": "0",
        "length": "100",
        "order[0][column]": "0",
        "order[0][dir]": "desc",
        "searchDate": date_str,
    }, timeout=15)

    if resp.status_code != 200:
        print(f"[ERROR] API応答エラー: {resp.status_code}")
        return []

    try:
        data = resp.json()
        return data.get("data", [])
    except json.JSONDecodeError:
        print("[ERROR] JSONパースエラー")
        return []


def send_discord_message(content: Optional[str] = None, embeds: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Discordにメッセージを送信"""
    url = f"{DISCORD_API_BASE}/channels/{DISCORD_CHANNEL_ID}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {}  # type: Dict[str, Any]
    if content:
        payload["content"] = content
    if embeds:
        payload["embeds"] = embeds

    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    if resp.status_code in (200, 201):
        print("[OK] Discord送信成功")
        return True
    else:
        print(f"[ERROR] Discord送信失敗: {resp.status_code} {resp.text}")
        return False


def format_cv_message(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """CV情報をDiscord Embed形式にフォーマット"""
    embeds = []
    for r in records:
        action = r.get('actionDate', '-')
        click = r.get('clickDate', '')
        flag = ""
        try:
            dt_click = datetime.datetime.strptime(click, "%Y-%m-%d %H:%M:%S")
            dt_action = datetime.datetime.strptime(action, "%Y-%m-%d %H:%M:%S")
            if (dt_action - dt_click).total_seconds() >= 12 * 3600:
                flag = "(❌)"
        except (ValueError, TypeError):
            pass
        embeds.append({
            "title": "新規CV通知【CATs】",
            "description": (
                f"\\ CVがつきました‼️🎉 /　{action}{flag}\n"
                f"・ 媒体: {r.get('partnerName', '-')}\n"
                f"・ 広告主: {r.get('companyName', '-')}"
            ),
            "color": 0x00FF00,
        })
    return embeds


# ===== CV検索応答 =====

def fetch_discord_messages() -> List[Dict[str, Any]]:
    """Discordの最新メッセージを取得"""
    url = f"{DISCORD_API_BASE}/channels/{DISCORD_CHANNEL_ID}/messages"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    resp = requests.get(url, headers=headers, params={"limit": "50"}, timeout=10)
    if resp.status_code == 200:
        return resp.json()
    print(f"[ERROR] Discordメッセージ取得失敗: {resp.status_code}")
    return []


def parse_search_query(body: str) -> Optional[Dict[str, str]]:
    """検索テンプレートをパース"""
    period_match = re.search(
        r'【期間】(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}\s*\S+\s*(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}',
        body
    )
    if not period_match:
        return None

    start_date = period_match.group(1).replace('-', '/')
    end_date = period_match.group(2).replace('-', '/')

    media_match = re.search(r'【媒体】(.+)', body)
    project_match = re.search(r'【案件】(.+)', body)

    if media_match:
        return {
            "type": "media",
            "date_str": f"{start_date} - {end_date}",
            "query": media_match.group(1).strip(),
        }
    if project_match:
        return {
            "type": "project",
            "date_str": f"{start_date} - {end_date}",
            "query": project_match.group(1).strip(),
        }
    return None


def format_search_result(records: List[Dict[str, Any]], query: Dict[str, str]) -> List[Dict[str, Any]]:
    """CV検索結果をDiscord Embed形式にフォーマット"""
    q = normalize_text(query["query"])
    if query["type"] == "media":
        filtered = [r for r in records if q in normalize_text(r.get("partnerName", ""))]
    else:
        filtered = [r for r in records
                    if q in normalize_text(r.get("companyName", ""))
                    or q in normalize_text(r.get("partnerName", ""))]

    if not filtered:
        return [{
            "title": "CV検索結果",
            "description": f"「{query['query']}」のCVは【0】件です。",
            "color": 0x0099FF,
        }]

    lines = [f"この期間のCVは【{len(filtered)}】件です。\n---"]
    for i, r in enumerate(filtered):
        num = CIRCLED_NUMS[i] if i < len(CIRCLED_NUMS) else f"({i+1})"
        click = r.get("clickDate", "-")
        action = r.get("actionDate", "-")
        flag = ""
        try:
            dt_click = datetime.datetime.strptime(click, "%Y-%m-%d %H:%M:%S")
            dt_action = datetime.datetime.strptime(action, "%Y-%m-%d %H:%M:%S")
            if (dt_action - dt_click).total_seconds() >= 12 * 3600:
                flag = "❌"
        except (ValueError, TypeError):
            pass
        if query["type"] == "project":
            media = r.get("partnerName", "-")
            lines.append(f"{num}【媒体】{media}\n　【クリック】{click}【成果】{action}{flag}")
        else:
            lines.append(f"{num}【クリック】{click}【成果】{action}{flag}")

    return [{
        "title": "CV検索結果",
        "description": "\n".join(lines),
        "color": 0x0099FF,
    }]


def check_search_queries(session: requests.Session, responded_ids: Set[str]) -> Set[str]:
    """Discordの検索リクエストに応答"""
    messages = fetch_discord_messages()
    if not messages:
        return responded_ids

    for msg in messages:
        mid = str(msg.get("id", ""))
        if mid in responded_ids:
            continue

        body = msg.get("content", "")
        query = parse_search_query(body)
        if query is None:
            continue

        print(f"[SEARCH] 検索リクエスト検出: {query['type']}={query['query']}")
        records = fetch_cv_logs(session, query["date_str"])
        result_embeds = format_search_result(records, query)
        send_discord_message(embeds=result_embeds)
        responded_ids.add(mid)

    return responded_ids


# ===== 状態管理 =====

def load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"seen_ids": [], "responded_msg_ids": []}


def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False)


def make_record_id(r: Dict[str, Any]) -> str:
    return f"{r.get('actionDate', '')}_{r.get('sessionId', '')}_{r.get('partnerName', '')}"


def check_and_notify(session: requests.Session, seen_ids: Set[str]) -> Set[str]:
    now = datetime.datetime.now().strftime("%H:%M:%S")
    records = fetch_cv_logs(session)

    if not records:
        print(f"[{now}] セッション再取得...")
        if cats_login(session):
            records = fetch_cv_logs(session)

    if not records:
        print(f"[{now}] データ取得失敗")
        return seen_ids

    new_records = []
    for r in records:
        rid = make_record_id(r)
        if rid not in seen_ids:
            new_records.append(r)
        seen_ids.add(rid)

    if new_records:
        print(f"[{now}] 取得: {len(records)}件 → 新規CV {len(new_records)}件!")
        embeds = format_cv_message(new_records)
        for i in range(0, len(embeds), 10):
            send_discord_message(embeds=embeds[i:i+10])
    else:
        print(f"[{now}] 取得: {len(records)}件 → 新規なし")

    return seen_ids


def main():
    print("=" * 50)
    print("CATs CV即時通知 + 検索応答（GitHub Actions → Discord）")
    print("=" * 50)

    session = requests.Session()

    print("[INIT] CATsにログイン中...")
    if not cats_login(session):
        print("[ERROR] ログイン失敗")
        return
    print("[INIT] ログイン成功")

    # 前回の状態を復元
    state = load_state()
    seen_ids = set(state.get("seen_ids", []))
    responded_ids = set(state.get("responded_msg_ids", []))

    # 初回起動時（stateが空）は既存データを既読にする
    if not seen_ids:
        records = fetch_cv_logs(session)
        if records:
            for r in records:
                seen_ids.add(make_record_id(r))
            print(f"[INIT] 既存CV {len(records)}件を既読化")

    # 初回起動時は既存の検索リクエストをスキップ
    if not responded_ids:
        messages = fetch_discord_messages()
        for msg in messages:
            mid = str(msg.get("id", ""))
            body = msg.get("content", "")
            if parse_search_query(body) is not None:
                responded_ids.add(mid)
        if responded_ids:
            print(f"[INIT] 既存検索リクエスト {len(responded_ids)}件をスキップ")

    # 50秒間ループ
    start = time.time()
    while time.time() - start < RUN_DURATION:
        try:
            seen_ids = check_and_notify(session, seen_ids)
            responded_ids = check_search_queries(session, responded_ids)
        except Exception as e:
            print(f"[ERROR] {e}")

        # 状態を毎回保存（中断に備えて）
        save_state({
            "seen_ids": list(seen_ids)[-500:],
            "responded_msg_ids": list(responded_ids)[-200:],
        })

        remaining = RUN_DURATION - (time.time() - start)
        if remaining > CHECK_INTERVAL:
            time.sleep(CHECK_INTERVAL)
        else:
            break

    print("[DONE] 今回の実行完了")


if __name__ == "__main__":
    main()
