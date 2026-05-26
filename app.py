import threading
import rumps
from jobcan.state import State
from jobcan.browser import clock_action


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
        self.title = self.TITLE_BUSY
        self.action_btn.set_callback(None)  # 処理中は連打防止
        threading.Thread(target=self._run_clock, daemon=True).start()

    def _run_clock(self):
        try:
            new_state = clock_action(currently_working=self.state.is_working)
            self.state.set_working(new_state)
            msg = "出勤しました ✓" if new_state else "退勤しました ✓"
            rumps.notification("Jobcan", "", msg)
        except Exception as e:
            print(f"[jobcan] エラー: {e}", flush=True)
            rumps.notification("Jobcan", "エラー", str(e))
        finally:
            self.action_btn.set_callback(self._on_action)
            self._sync_ui()

    def _quit(self, _):
        rumps.quit_application()


if __name__ == "__main__":
    # Dock アイコンを非表示にする（メニューバーアプリとして動作）
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
    NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    JobcanApp().run()
