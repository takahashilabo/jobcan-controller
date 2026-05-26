# Jobcan Controller

macOS のメニューバーから1クリックでジョブカンの出勤・退勤打刻を行うツールです。
大学の SAML/SSO 認証（2段階認証対応）に対応しています。

## 機能

- メニューバーに常駐（⚪ 未出勤 / 🔴 出勤中）
- クリック1回で出勤・退勤打刻
- 大学 SSO への自動ログイン
- セッション保存により2回目以降はログイン不要
- セッション切れを自動検知 → ブラウザを表示して2FA再認証

## 動作イメージ

```
メニューバー: ⚪ 未出勤
  └─ 「出勤する」クリック
       → Jobcan に自動アクセス・打刻
       → 🔴 出勤中 に変わる

メニューバー: 🔴 出勤中
  └─ 「退勤する」クリック
       → Jobcan に自動アクセス・打刻
       → ⚪ 未出勤 に変わる
```

## セットアップ

### 必要環境

- macOS
- Python 3.9 以上

### インストール

```bash
git clone https://github.com/takahashilabo/jobcan-controller.git
cd jobcan-controller
cp .env.example .env
```

`.env` を編集して設定を記入します（後述）。

```bash
bash install.sh
```

これで仮想環境の作成・パッケージインストール・ログイン時自動起動の登録が完了します。

### .env の設定

| 項目 | 説明 | 例 |
|---|---|---|
| `JOBCAN_URL` | Jobcan のログイン URL（クエリパラメータ含む） | `https://id.jobcan.jp/users/saml/select_idp?client_code=...` |
| `SSO_URL_PATTERN` | 大学 SSO ページの URL に含まれる文字列 | `idp.example-univ.ac.jp` |
| `SSO_USERNAME` | 大学アカウントのID | `0012345` |
| `SSO_PASSWORD` | 大学アカウントのパスワード | `password` |
| `MOCK` | `true` にすると Jobcan に接続せずテスト可能 | `false` |

## 初回起動・2FA 認証

初回（またはセッション切れ時）は Chromium が自動で開きます。
ID・パスワードは自動入力されるので、**2FA 認証だけ手動で完了**してください。
Jobcan に戻ると自動的に打刻が実行されます。

以降はセッションが保存されるため、有効期限が切れるまでブラウザは表示されません。

## 手動起動・停止

```bash
# 起動
.venv/bin/python app.py

# 停止
pkill -f "python app.py"

# ログ確認（install.sh でインストール後）
tail -f /tmp/jobcan.log
```

## ファイル構成

```
jobcan-controller/
├── app.py                  # メニューバーアプリ本体
├── install.sh              # 仮想環境構築 + 自動起動登録
├── requirements.txt
├── .env.example            # 設定テンプレート
└── jobcan/
    ├── browser.py          # Playwright による打刻・SSO 処理
    └── state.py            # 勤務状態の保存・読み込み
```

## アンインストール

```bash
launchctl unload ~/Library/LaunchAgents/com.jobcan.controller.plist
rm ~/Library/LaunchAgents/com.jobcan.controller.plist
```
