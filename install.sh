#!/bin/bash
# ジョブカンコントローラをログイン時自動起動に登録するスクリプト

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
PLIST_NAME="com.jobcan.controller"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

# 仮想環境の作成とパッケージインストール
echo "→ 仮想環境を作成中..."
python3 -m venv "$VENV"
"$VENV/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"
"$VENV/bin/playwright" install chromium

# .env がなければサンプルからコピー
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    echo "→ .env を作成しました。設定を記入してください: $SCRIPT_DIR/.env"
fi

# launchd plist を生成
cat > "$PLIST_DST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV/bin/python</string>
        <string>$SCRIPT_DIR/app.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/jobcan.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/jobcan.err</string>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
</dict>
</plist>
EOF

# launchd に登録
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

echo "✓ インストール完了。メニューバーにアイコンが表示されます。"
echo "  ログ: /tmp/jobcan.log"
echo "  エラーログ: /tmp/jobcan.err"
