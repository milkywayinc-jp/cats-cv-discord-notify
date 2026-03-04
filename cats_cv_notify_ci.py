#!/usr/bin/env python3
"""
CATs CV通知 → Chatwork（GitHub Actions用）
5分ごとに起動し、4分半の間30秒おきにチェックする
"""

import os
import json
import time
import datetime
import requests
from typing import Optional, List, Dict, Any

# ===== 設定（環境変数から取得） =====
CATS_LOGIN_URL = "https://admin.deneb.tokyo/front/login/confirm"
CATS_SEARCH_URL = "https://admin.deneb.tokyo/admin/actionlog/list/search"
CATS_LOGIN_ID = os.environ["CATS_LOGIN_ID"]
CATS_PASSWORD = os.environ["CATS_PASSWORD"]

CHATWORK_API_TOKEN = os.environ["CHATWORK_API_TOKEN"]
CHATWORK_ROOM_ID = os.environ["CHATWORK_ROOM_ID"]
CHATWORK_API_URL = f"https://api.chatwork.com/v2/rooms/{CHATWORK_ROOM_ID}/messages"

CHECK_INTERVAL = 30   # 30秒
RUN_DURATION = 270    # 4分30秒（5分のcronに収まるように）

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cats_last_check.json")


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


def send_chatwork_message(message: str) -> bool:
    resp = requests.post(
        CHATWORK_API_URL,
        headers={"X-ChatWorkToken": CHATWORK_API_TOKEN},
        data={"body": message, "self_unread": "1"},
        timeout=10,
    )
    if resp.status_code in (200, 201):
        print(f"[OK] Chatwork送信成功")
        return True
    else:
        print(f"[ERROR] Chatwork送信失敗: {resp.status_code} {resp.text}")
        return False


def format_cv_message(records: List[Dict[str, Any]]) -> str:
    messages = []
    for r in records:
        messages.append(
            f"[info][title]新規CV通知【CATs】[/title]"
            f"\\ CVがつきました‼️🎉 /　{r.get('actionDate', '-')}\n"
            f"・ 媒体: {r.get('partnerName', '-')}\n"
            f"・ 広告主: {r.get('companyName', '-')}[/info]"
        )
    return "\n".join(messages)


def load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"seen_ids": []}


def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False)


def make_record_id(r: Dict[str, Any]) -> str:
    return f"{r.get('actionDate', '')}_{r.get('sessionId', '')}_{r.get('partnerName', '')}"


def check_and_notify(session: requests.Session, seen_ids: set) -> set:
    now = datetime.datetime.now().strftime("%H:%M:%S")
    records = fetch_cv_logs(session)

    if not records:
        # セッション切れ → 再ログイン
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
        message = format_cv_message(new_records)
        send_chatwork_message(message)
    else:
        print(f"[{now}] 取得: {len(records)}件 → 新規なし")

    return seen_ids


def main():
    print("=" * 50)
    print("CATs CV即時通知（GitHub Actions）")
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

    # 初回起動時（stateが空）は既存データを既読にする
    if not seen_ids:
        records = fetch_cv_logs(session)
        if records:
            for r in records:
                seen_ids.add(make_record_id(r))
            print(f"[INIT] 既存CV {len(records)}件を既読化")

    # 4分30秒間ループ
    start = time.time()
    while time.time() - start < RUN_DURATION:
        try:
            seen_ids = check_and_notify(session, seen_ids)
        except Exception as e:
            print(f"[ERROR] {e}")

        # 状態を毎回保存（中断に備えて）
        save_state({"seen_ids": list(seen_ids)[-500:]})

        remaining = RUN_DURATION - (time.time() - start)
        if remaining > CHECK_INTERVAL:
            time.sleep(CHECK_INTERVAL)
        else:
            break

    print("[DONE] 今回の実行完了")


if __name__ == "__main__":
    main()
