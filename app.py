import os
import subprocess
import threading
from datetime import datetime, date

import rumps
from dotenv import load_dotenv

from jobcan.state import State
from jobcan.browser import clock_action

load_dotenv()

AUTO_CHECKIN_SSID               = os.getenv("AUTO_CHECKIN_SSID", "")
AUTO_CHECKIN_GATEWAY_MAC_PREFIX = os.getenv("AUTO_CHECKIN_GATEWAY_MAC_PREFIX", "")
AUTO_CHECKIN_LAST_FILE          = os.path.expanduser("~/.jobcan_last_auto_checkin")
AUTO_CHECKIN_HOUR_FROM          = 6
AUTO_CHECKIN_HOUR_TO            = 13


def _get_wifi_ssid() -> str:
    """SSID を返す。macOS の位置情報制限で取得できない場合は空文字。"""
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


def _get_gateway_mac_prefix() -> str:
    """デフォルトゲートウェイの MAC アドレス OUI (xx:xx:xx) を返す。"""
    try:
        gw = subprocess.run(
            ["ipconfig", "getoption", "en0", "router"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        if not gw:
            return ""
        arp_out = subprocess.run(
            ["arp", "-n", gw], capture_output=True, text=True, timeout=5
        ).stdout
        parts = arp_out.split(" at ")
        if len(parts) >= 2:
            mac = parts[1].split()[0]
            return ":".join(mac.split(":")[:3]).lower()
    except Exception:
        pass
    return ""


def _is_target_network() -> bool:
    """学内ネットワーク判定。SSID → ゲートウェイ MAC OUI の順で試みる。"""
    ssid = _get_wifi_ssid()
    if ssid:
        result = ssid == AUTO_CHECKIN_SSID
        print(f"[wifi] SSID={ssid!r} target={AUTO_CHECKIN_SSID!r} match={result}", flush=True)
        return result
    if AUTO_CHECKIN_GATEWAY_MAC_PREFIX:
        prefix = _get_gateway_mac_prefix()
        result = prefix == AUTO_CHECKIN_GATEWAY_MAC_PREFIX.lower()
        print(f"[wifi] gateway MAC prefix={prefix!r} target={AUTO_CHECKIN_GATEWAY_MAC_PREFIX!r} match={result}", flush=True)
        return result
    return False


def _is_auto_checkin_done_today() -> bool:
    try:
        return open(AUTO_CHECKIN_LAST_FILE).read().strip() == date.today().isoformat()
    except FileNotFoundError:
        return False


def _mark_auto_checkin_today():
    with open(AUTO_CHECKIN_LAST_FILE, "w") as f:
        f.write(date.today().isoformat())


def _notify_problem(title: str, message: str):
    """問題発生時の通知。ログにも残す。"""
    print(f"[notify] {title}: {message}", flush=True)
    rumps.notification("Jobcan ⚠️", title, message)


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
        rumps.Timer(self._auto_checkin_check, 300).start()

    # ── UI 更新 ───────────────────────────────────────────────────────────────

    def _sync_ui(self):
        if self.state.is_working:
            self.title = self.TITLE_WORKING
            self.action_btn.title = "退勤する"
        else:
            self.title = self.TITLE_NOT_WORKING
            self.action_btn.title = "出勤する"

    # ── ボタン押下（手動）────────────────────────────────────────────────────

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
            _notify_problem("打刻エラー", f"Jobcanへの接続に失敗しました: {e}")
        finally:
            self.action_btn.set_callback(self._on_action)
            self._sync_ui()

    # ── 自動出勤 ──────────────────────────────────────────────────────────────

    def _auto_checkin_check(self, _):
        if not AUTO_CHECKIN_SSID:
            return

        # 日をまたいで出勤中のままだったらリセット（退勤打刻し忘れ）
        if self.state.reset_if_stale():
            self._sync_ui()
            _notify_problem(
                "出勤状態をリセット",
                "昨日退勤打刻されていなかったため未出勤に戻しました。"
                "Jobcan側は手動修正が必要な場合があります。"
            )

        if self.state.is_working:
            return

        now = datetime.now()
        if not (AUTO_CHECKIN_HOUR_FROM <= now.hour < AUTO_CHECKIN_HOUR_TO):
            return

        if _is_auto_checkin_done_today():
            return

        if getattr(self, '_auto_in_progress', False):
            return

        if not _is_target_network():
            return

        print(f"[auto] 学内ネットワークを検出 → 自動出勤します", flush=True)
        self._auto_in_progress = True
        threading.Thread(target=self._run_auto_clock, daemon=True).start()

    def _run_auto_clock(self):
        """自動出勤用。成功したときだけ今日分をマーク（失敗時は次のタイマーで再試行）。"""
        try:
            print(f"[app] 自動出勤 処理開始", flush=True)
            new_state = clock_action(currently_working=False)
            self.state.set_working(new_state)
            if new_state:
                _mark_auto_checkin_today()
                print("[app] 自動出勤成功", flush=True)
            else:
                print("[app] 自動出勤失敗（打刻不可） → 次のタイマーで再試行", flush=True)
                _notify_problem(
                    "自動出勤 失敗",
                    "学内ネットワークを検出しましたが打刻が受け付けられませんでした。"
                    "5分後に再試行します。"
                    "繰り返す場合はJobcanのIP認証範囲外の可能性があります。"
                )
        except Exception as e:
            print(f"[app] 自動出勤エラー: {e}", flush=True)
            import traceback; traceback.print_exc()
            _notify_problem("自動出勤 エラー", str(e))
        finally:
            self._auto_in_progress = False
            self._sync_ui()

    # ── その他 ────────────────────────────────────────────────────────────────

    def _quit(self, _):
        rumps.quit_application()


if __name__ == "__main__":
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
    NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    JobcanApp().run()
