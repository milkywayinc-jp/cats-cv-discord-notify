#!/usr/bin/env python3
"""
CATs CV通知 + CV検索応答 → Chatwork
成果ログを定期チェックし、新しいCVをChatworkに通知する
Chatworkの検索リクエストにも応答する
"""

import os
import re
import json
import time
import datetime
import requests
from typing import Optional, List, Dict, Any, Set
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ===== 設定（環境変数から取得） =====
CATS_LOGIN_URL = "https://admin.deneb.tokyo/front/login/confirm"
CATS_SEARCH_URL = "https://admin.deneb.tokyo/admin/actionlog/list/search"
CATS_LOGIN_ID = os.environ["CATS_LOGIN_ID"]
CATS_PASSWORD = os.environ["CATS_PASSWORD"]

CHATWORK_API_TOKEN = os.environ["CHATWORK_API_TOKEN"]
CHATWORK_ROOM_ID = os.environ.get("CATS_CHATWORK_ROOM_ID", os.environ.get("CHATWORK_ROOM_ID", ""))
CHATWORK_API_URL = f"https://api.chatwork.com/v2/rooms/{CHATWORK_ROOM_ID}/messages"

# チェック間隔（秒）
CHECK_INTERVAL = 30  # 30秒（即時通知）

# 最終チェック記録ファイル
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cats_last_check.json")

CIRCLED_NUMS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def normalize_text(text: str) -> str:
    """&/＆/&amp; やHTMLエンティティを正規化して比較用テキストを返す"""
    import html
    text = html.unescape(text)
    text = text.replace("＆", "&")
    return text


def cats_login(session: requests.Session) -> bool:
    """CATsにログインしてセッションを取得"""
    resp = session.post(CATS_LOGIN_URL, data={
        "loginId": CATS_LOGIN_ID,
        "password": CATS_PASSWORD,
    }, allow_redirects=True)
    return resp.status_code == 200 and "ログイン" not in resp.text[:500]


def fetch_cv_logs(session: requests.Session, date_str: Optional[str] = None) -> List[Dict[str, Any]]:
    """成果ログを取得（DataTables server-side API）"""
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
    })

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
    """Chatworkにメッセージを送信"""
    resp = requests.post(
        CHATWORK_API_URL,
        headers={"X-ChatWorkToken": CHATWORK_API_TOKEN},
        data={"body": message, "self_unread": "1"},
    )
    if resp.status_code in (200, 201):
        print(f"[OK] Chatwork送信成功")
        return True
    else:
        print(f"[ERROR] Chatwork送信失敗: {resp.status_code} {resp.text}")
        return False


def format_cv_message(records: List[Dict[str, Any]]) -> str:
    """CV情報をChatworkメッセージにフォーマット"""
    messages = []
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
        messages.append(
            f"[info][title]新規CV通知【CATs】[/title]"
            f"\\ CVがつきました‼️🎉 /　{action}{flag}\n"
            f"・ 媒体: {r.get('partnerName', '-')}\n"
            f"・ 広告主: {r.get('companyName', '-')}[/info]"
        )
    return "\n".join(messages)


# ===== CV検索応答 =====

def fetch_chatwork_messages() -> List[Dict[str, Any]]:
    """Chatworkの最新メッセージを取得"""
    resp = requests.get(
        CHATWORK_API_URL,
        headers={"X-ChatWorkToken": CHATWORK_API_TOKEN},
        params={"force": "1"},
        timeout=10,
    )
    if resp.status_code == 200:
        return resp.json()
    if resp.status_code == 204:
        return []
    print(f"[ERROR] Chatworkメッセージ取得失敗: {resp.status_code}")
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


def format_search_result(records: List[Dict[str, Any]], query: Dict[str, str]) -> str:
    """CV検索結果をフォーマット"""
    # フィルタ（正規化して比較、partnerName と companyName 両方を検索）
    q = normalize_text(query["query"])
    if query["type"] == "media":
        filtered = [r for r in records if q in normalize_text(r.get("partnerName", ""))]
    else:
        filtered = [r for r in records
                    if q in normalize_text(r.get("companyName", ""))
                    or q in normalize_text(r.get("partnerName", ""))]

    if not filtered:
        return f"[info][title]CV検索結果[/title]「{query['query']}」のCVは【0】件です。[/info]"

    lines = [f"[info][title]CV検索結果[/title]この期間のCVは【{len(filtered)}】件です。\n---"]
    for i, r in enumerate(filtered):
        num = CIRCLED_NUMS[i] if i < len(CIRCLED_NUMS) else f"({i+1})"
        click = r.get("clickDate", "-")
        action = r.get("actionDate", "-")
        # クリック→成果が12時間以上なら❌
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
    lines.append("[/info]")
    return "\n".join(lines)


def check_search_queries(session: requests.Session, responded_ids: Set[str]) -> Set[str]:
    """Chatworkの検索リクエストに応答"""
    messages = fetch_chatwork_messages()
    if not messages:
        return responded_ids

    for msg in messages:
        mid = str(msg.get("message_id", ""))
        if mid in responded_ids:
            continue

        body = msg.get("body", "")
        query = parse_search_query(body)
        if query is None:
            continue

        print(f"[SEARCH] 検索リクエスト検出: {query['type']}={query['query']}")
        records = fetch_cv_logs(session, query["date_str"])
        result = format_search_result(records, query)
        send_chatwork_message(result)
        responded_ids.add(mid)

    return responded_ids


# ===== 状態管理 =====

def load_state() -> Dict[str, Any]:
    """前回のチェック状態を読み込み"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"seen_ids": [], "responded_msg_ids": []}


def save_state(state: Dict[str, Any]) -> None:
    """チェック状態を保存"""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False)


def make_record_id(r: Dict[str, Any]) -> str:
    return f"{r.get('actionDate', '')}_{r.get('sessionId', '')}_{r.get('partnerName', '')}"


def check_and_notify(session: requests.Session, seen_ids: Set[str]) -> Set[str]:
    """新規CVをチェックして通知"""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    records = fetch_cv_logs(session)

    if not records:
        print(f"[{now}] セッション再取得中...")
        if not cats_login(session):
            print(f"[{now}] ログイン失敗")
            return seen_ids
        records = fetch_cv_logs(session)

    if not records:
        print(f"[{now}] データなし")
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


def test_single():
    """テスト: 1回だけ実行して結果確認"""
    print("=" * 50)
    print("CATs CV通知テスト")
    print("=" * 50)

    session = requests.Session()

    print("\n[1] ログインテスト...")
    if not cats_login(session):
        print("  ✗ ログイン失敗")
        return
    print("  ✓ ログイン成功")

    print("\n[2] 成果ログ取得テスト...")
    records = fetch_cv_logs(session)
    print(f"  ✓ {len(records)}件取得")

    if records:
        print("\n[3] 取得データサンプル（最新3件）:")
        for i, r in enumerate(records[:3]):
            print(f"  --- レコード {i+1} ---")
            print(f"  成果日時: {r.get('actionDate', '-')}")
            print(f"  クリック日時: {r.get('clickDate', '-')}")
            print(f"  媒体名: {r.get('partnerName', '-')}")
            print(f"  広告主: {r.get('companyName', '-')}")

        print("\n[4] Chatwork送信テスト（最新1件のみ）...")
        test_msg = format_cv_message(records[:1])
        print(f"  メッセージプレビュー:\n{test_msg}")
        send_chatwork_message(test_msg)
    else:
        print("  本日のCVデータなし")


def run_loop():
    """ループ実行（セッション使い回し）"""
    print(f"CATs CV即時通知 + 検索応答を開始（{CHECK_INTERVAL}秒間隔）")
    print("Ctrl+C で停止\n")

    session = requests.Session()
    print("[INIT] CATsにログイン中...")
    if not cats_login(session):
        print("[ERROR] 初回ログイン失敗。認証情報を確認してください。")
        return
    print("[INIT] ログイン成功\n")

    # 前回の状態を復元
    state = load_state()
    seen_ids = set(state.get("seen_ids", []))
    responded_ids = set(state.get("responded_msg_ids", []))

    # 初回は既存データを全て「既読」にする
    if not seen_ids:
        records = fetch_cv_logs(session)
        if records:
            for r in records:
                seen_ids.add(make_record_id(r))
            print(f"[INIT] 既存CV {len(records)}件を既読化")

    # 初回は既存の検索リクエストをスキップ
    if not responded_ids:
        messages = fetch_chatwork_messages()
        for msg in messages:
            mid = str(msg.get("message_id", ""))
            body = msg.get("body", "")
            if parse_search_query(body) is not None:
                responded_ids.add(mid)
        if responded_ids:
            print(f"[INIT] 既存検索リクエスト {len(responded_ids)}件をスキップ")

    print()
    login_time = time.time()

    while True:
        try:
            # 4時間ごとにセッション再取得
            if time.time() - login_time > 3600 * 3.5:
                print("[SESSION] セッション更新中...")
                session = requests.Session()
                cats_login(session)
                login_time = time.time()

            seen_ids = check_and_notify(session, seen_ids)
            responded_ids = check_search_queries(session, responded_ids)

            # 状態保存
            save_state({
                "seen_ids": list(seen_ids)[-500:],
                "responded_msg_ids": list(responded_ids)[-200:],
            })
        except KeyboardInterrupt:
            print("\n[STOP] 停止しました")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_single()
    elif len(sys.argv) > 1 and sys.argv[1] == "loop":
        run_loop()
    else:
        print("使い方:")
        print("  python3 cats_cv_notify.py test  -- テスト実行（1回）")
        print("  python3 cats_cv_notify.py loop  -- ループ実行（30秒間隔）")
