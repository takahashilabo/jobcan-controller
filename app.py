import os
import subprocess
import threading
from datetime import datetime, date

import rumps
from dotenv import load_dotenv

from jobcan.state import State
from jobcan.browser import clock_action

load_dotenv()

AUTO_CHECKIN_SSID      = os.getenv("AUTO_CHECKIN_SSID", "")
AUTO_CHECKIN_LAST_FILE = os.path.expanduser("~/.jobcan_last_auto_checkin")
AUTO_CHECKIN_HOUR_FROM = 6
AUTO_CHECKIN_HOUR_TO   = 13


def _get_wifi_ssid() -> str:
    for iface in ["en0", "en1", "en2"]:
        try:
            out = subprocess.run(
                ["networksetup", "-getairportnetwork", iface],
                capture_output=True, text=True, timeout=5
            ).stdout
            if "Current Wi-Fi Network:" in out:
                return out.split("Current Wi-Fi Network:")[-1].strip()
        except Exception:
            continue
    return ""


def _is_auto_checkin_done_today() -> bool:
    try:
        return open(AUTO_CHECKIN_LAST_FILE).read().strip() == date.today().isoformat()
    except FileNotFoundError:
        return False


def _mark_auto_checkin_today():
    with open(AUTO_CHECKIN_LAST_FILE, "w") as f:
        f.write(date.today().isoformat())


class JobcanApp(rumps.App):
    TITLE_WORKING     = "🔴 出勤中"
    TITLE_NOT_WORKING = "⚪ 未出勤"
    TITLE_BUSY        = "⏳ 処理中..."

    def __init__(self):
        self.state = State()
        self.action_btn = rumps.MenuItem("", callback=self._on_action)
        super().__init__(
            self.TITLE_NOT_WORKING,
            menu=[self.action_btn, None, rumps.MenuItem("終了", callback=self._quit)],
            quit_button=None,
        )
        self._sync_ui()

    # ── UI 更新 ───────────────────────────────────────────────────────────────

    def _sync_ui(self):
        if self.state.is_working:
            self.title = self.TITLE_WORKING
            self.action_btn.title = "退勤する"
        else:
            self.title = self.TITLE_NOT_WORKING
            self.action_btn.title = "出勤する"

    # ── ボタン押下 ────────────────────────────────────────────────────────────

    def _on_action(self, _):
        print("[app] ボタンが押されました", flush=True)
        self.title = self.TITLE_BUSY
        self.action_btn.set_callback(None)
        threading.Thread(target=self._run_clock, daemon=True).start()

    def _run_clock(self):
        try:
            print(f"[app] 処理開始 currently_working={self.state.is_working}", flush=True)
            new_state = clock_action(currently_working=self.state.is_working)
            self.state.set_working(new_state)
            msg = "出勤しました ✓" if new_state else "退勤しました ✓"
            print(f"[app] {msg}", flush=True)
            rumps.notification("Jobcan", "", msg)
        except Exception as e:
            print(f"[app] エラー: {e}", flush=True)
            import traceback; traceback.print_exc()
            rumps.notification("Jobcan", "エラー", str(e))
        finally:
            self.action_btn.set_callback(self._on_action)
            self._sync_ui()

    # ── 自動出勤 ──────────────────────────────────────────────────────────────

    @rumps.timer(300)
    def _auto_checkin_check(self, _):
        if not AUTO_CHECKIN_SSID:
            return
        if self.state.is_working:
            return

        now = datetime.now()
        if not (AUTO_CHECKIN_HOUR_FROM <= now.hour < AUTO_CHECKIN_HOUR_TO):
            return

        if _is_auto_checkin_done_today():
            return

        ssid = _get_wifi_ssid()
        if ssid != AUTO_CHECKIN_SSID:
            return

        print(f"[auto] 学内WiFi({ssid})を検出 → 自動出勤します", flush=True)
        _mark_auto_checkin_today()
        rumps.notification("Jobcan", "自動出勤", f"{ssid} に接続中のため出勤打刻します")
        threading.Thread(target=self._run_clock, daemon=True).start()

    # ── その他 ────────────────────────────────────────────────────────────────

    def _quit(self, _):
        rumps.quit_application()


if __name__ == "__main__":
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
    NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    JobcanApp().run()
