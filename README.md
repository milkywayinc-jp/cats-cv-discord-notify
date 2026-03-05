# cats-cv-discord-notify

CATs CV通知 + CV検索Bot — Discord連携

## 機能

- **CV即時通知**: 30秒間隔で成果ログをチェック、新規CVをDiscordに通知
- **CV検索応答**: Discordにテンプレートを投稿すると検索結果を自動返信
- **12時間フラグ**: クリック→成果が12時間以上空いている場合は(❌)を表示

## 検索テンプレート

```
【媒体ごと】
【期間】2026-03-03 00:00:00▶︎2026-03-03 23:59:59
【媒体】乳酸菌&イチョウ葉の恵み_DN01(mw成果_rete)

【案件ごと】
【期間】2026-03-03 00:00:00▶︎2026-03-03 23:59:59
【案件】乳酸菌&イチョウ葉の恵み
```

## 実行方法

### ローカル実行（PC起動中、30秒間隔）

```bash
python3 cats_cv_notify.py loop

# テスト（1回だけ実行）
python3 cats_cv_notify.py test
```

### GitHub Actions（PC閉じていても動作）

`.github/workflows/cats_cv_notify.yml` で5分間隔でスケジュール実行。
各実行は270秒間、20秒おきにチェック。

必要なSecrets: `CATS_LOGIN_ID`, `CATS_PASSWORD`, `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID`

### Render デプロイ（24時間常時稼働）

`render.yaml` のBlueprintで無料Webサービスとしてデプロイ可能。
バックグラウンドスレッドでCV通知ループを実行し、ヘルスチェック用HTTPサーバーを提供。

```bash
# Renderデプロイ手順
# 1. render.com でアカウント作成（GitHub連携）
# 2. New → Blueprint → hana-1220/workspace を接続
# 3. 環境変数を設定して Apply
```

## ファイル構成

```
├── cats_cv_notify.py          # ローカル実行用（30秒ループ）
├── cats_cv_notify_ci.py       # GitHub Actions用（270秒実行）
├── cats_cv_notify_server.py   # Render用（HTTP + バックグラウンドループ）
├── render.yaml                # Render Blueprint
├── .github/workflows/
│   └── cats_cv_notify.yml     # GitHub Actions ワークフロー
├── requirements.txt
└── .env                       # 環境変数（git管理外）
```

## 環境変数

```
CATS_LOGIN_ID=       # CATs ログインID
CATS_PASSWORD=       # CATs パスワード
DISCORD_BOT_TOKEN=   # Discord Bot トークン
DISCORD_CHANNEL_ID=  # Discord チャンネルID
```
