# workspace

Chatwork連携の業務自動化ツール群

## 1. CATs CV通知 + CV検索Bot

CATsプラットフォームの成果ログを監視し、新規CVをChatworkに即時通知。
Chatworkからの検索リクエストにも自動応答する。

### 機能

- **CV即時通知**: 30秒間隔で成果ログをチェック、新規CVをChatworkに通知
- **CV検索応答**: Chatworkにテンプレートを投稿すると検索結果を自動返信
- **12時間フラグ**: クリック→成果が12時間以上空いている場合は(❌)を表示

### 検索テンプレート

```
【媒体ごと】
【期間】2026-03-03 00:00:00▶︎2026-03-03 23:59:59
【媒体】乳酸菌&イチョウ葉の恵み_DN01(mw成果_rete)

【案件ごと】
【期間】2026-03-03 00:00:00▶︎2026-03-03 23:59:59
【案件】乳酸菌&イチョウ葉の恵み
```

### 実行方法

```bash
# ローカル実行（PC起動中、30秒間隔）
python3 cats_cv_notify.py loop

# テスト（1回だけ実行）
python3 cats_cv_notify.py test
```

### GitHub Actions（PC閉じていても動作）

`.github/workflows/cats_cv_notify.yml` で2分間隔で自動実行。

必要なSecrets: `CATS_LOGIN_ID`, `CATS_PASSWORD`, `CHATWORK_API_TOKEN`, `CHATWORK_ROOM_ID`

---

## 2. ヒートマップ分析システム

SquadBeyondのヒートマップスクリーンショットをClaude Vision APIで分析し、Excelレポートを自動生成。

### 機能

- Claude Vision APIによるヒートマップ画像分析
- ブロック別のExcelレポート生成（滞在時間・離脱率・改善優先度）
- Chatwork Webhook連携（画像投稿→自動分析→CSV返信）

### 実行方法

```bash
# ローカル画像を分析
python -m src.cli analyze image1.png image2.png

# Chatwork監視モード
python -m src.cli watch --interval 30

# Webhookサーバー
python -m src.server
```

詳細は [CLAUDE.md](CLAUDE.md) を参照。
