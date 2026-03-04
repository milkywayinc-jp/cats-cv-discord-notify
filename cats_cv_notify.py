#!/usr/bin/env python3
"""
CATs CV通知 → Chatwork
成果ログを定期チェックし、新しいCVをChatworkに通知する
"""

import os
import json
import time
import datetime
import requests
from typing import Optional, List, Dict, Any

# ===== 設定 =====
CATS_LOGIN_URL = "https://admin.deneb.tokyo/front/login/confirm"
CATS_SEARCH_URL = "https://admin.deneb.tokyo/admin/actionlog/list/search"
CATS_LOGIN_ID = "milkywei001"
CATS_PASSWORD = "#h&fEKO8J_-J"

CHATWORK_API_TOKEN = "ab601292fd699a05b586481604402198"
CHATWORK_ROOM_ID = "424761668"
CHATWORK_API_URL = f"https://api.chatwork.com/v2/rooms/{CHATWORK_ROOM_ID}/messages"

# チェック間隔（秒）
CHECK_INTERVAL = 30  # 30秒（即時通知）

# 最終チェック記録ファイル
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cats_last_check.json")


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
        messages.append(
            f"[info][title]新規CV通知【CATs】[/title]"
            f"\\ CVがつきました‼️🎉 /　{r.get('actionDate', '-')}\n"
            f"・ 媒体: {r.get('partnerName', '-')}\n"
            f"・ 広告主: {r.get('companyName', '-')}[/info]"
        )
    return "\n".join(messages)


def load_state() -> Dict[str, Any]:
    """前回のチェック状態を読み込み"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"last_action_date": None, "seen_ids": []}


def save_state(state: Dict[str, Any]) -> None:
    """チェック状態を保存"""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False)


def check_and_notify(session: requests.Session) -> int:
    """メイン処理：新規CVをチェックして通知"""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    records = fetch_cv_logs(session)

    if records is None or (isinstance(records, list) and len(records) == 0):
        # セッション切れの可能性 → 再ログイン
        print(f"[{now}] セッション再取得中...")
        if not cats_login(session):
            print(f"[{now}] ログイン失敗")
            return 0
        records = fetch_cv_logs(session)

    print(f"[{now}] 取得: {len(records)}件", end="")

    if not records:
        print(" → データなし")
        return 0

    # 前回の状態と比較
    state = load_state()
    seen_ids = set(state.get("seen_ids", []))

    # 新しいレコードをフィルタ
    new_records = []
    for r in records:
        action_date = r.get("actionDate", "")
        record_id = f"{action_date}_{r.get('sessionId', '')}_{r.get('partnerName', '')}"
        if record_id not in seen_ids:
            new_records.append(r)
        seen_ids.add(record_id)

    if new_records:
        print(f" → 新規CV {len(new_records)}件!")
        message = format_cv_message(new_records)
        send_chatwork_message(message)
    else:
        print(" → 新規なし")

    # 状態保存（最新500件のみ保持）
    seen_list = list(seen_ids)[-500:]
    save_state({"seen_ids": seen_list})

    return len(new_records)


def test_single():
    """テスト: 1回だけ実行して結果確認"""
    print("=" * 50)
    print("CATs CV通知テスト")
    print("=" * 50)

    session = requests.Session()

    # ログインテスト
    print("\n[1] ログインテスト...")
    if not cats_login(session):
        print("  ✗ ログイン失敗")
        return
    print("  ✓ ログイン成功")

    # 成果ログ取得テスト
    print("\n[2] 成果ログ取得テスト...")
    records = fetch_cv_logs(session)
    print(f"  ✓ {len(records)}件取得")

    if records:
        print("\n[3] 取得データサンプル（最新3件）:")
        for i, r in enumerate(records[:3]):
            print(f"  --- レコード {i+1} ---")
            print(f"  成果日時: {r.get('actionDate', '-')}")
            print(f"  媒体名: {r.get('partnerName', '-')}")
            print(f"  広告主: {r.get('companyName', '-')}")
            print(f"  広告名: {r.get('contentName', '-')}")
            print(f"  成果地点: {r.get('actionPointId', '-')}")

        # Chatwork送信テスト
        print("\n[4] Chatwork送信テスト（最新1件のみ）...")
        test_msg = format_cv_message(records[:1])
        print(f"  メッセージプレビュー:\n{test_msg}")
        send_chatwork_message(test_msg)
    else:
        print("  本日のCVデータなし")


def run_loop():
    """ループ実行（セッション使い回し）"""
    print(f"CATs CV即時通知を開始（{CHECK_INTERVAL}秒間隔）")
    print("Ctrl+C で停止\n")

    session = requests.Session()
    print("[INIT] CATsにログイン中...")
    if not cats_login(session):
        print("[ERROR] 初回ログイン失敗。認証情報を確認してください。")
        return
    print("[INIT] ログイン成功\n")

    # 初回は既存データを全て「既読」にする（既存CVは通知しない）
    records = fetch_cv_logs(session)
    if records:
        seen_ids = []
        for r in records:
            action_date = r.get("actionDate", "")
            record_id = f"{action_date}_{r.get('sessionId', '')}_{r.get('partnerName', '')}"
            seen_ids.append(record_id)
        save_state({"seen_ids": seen_ids[-500:]})
        print(f"[INIT] 既存CV {len(records)}件を既読化\n")

    login_time = time.time()

    while True:
        try:
            # 4時間ごとにセッション再取得（Cookie有効期限対策）
            if time.time() - login_time > 3600 * 3.5:
                print("[SESSION] セッション更新中...")
                session = requests.Session()
                cats_login(session)
                login_time = time.time()

            check_and_notify(session)
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
        print("  python3 cats_cv_notify.py loop  -- ループ実行（5分間隔）")
