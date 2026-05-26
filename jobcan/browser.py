import os
import time
from dotenv import load_dotenv

load_dotenv()

MOCK              = os.getenv("MOCK", "false").lower() == "true"
JOBCAN_URL        = os.getenv("JOBCAN_URL", "https://ssl.jobcan.jp/employee")
SSO_URL_PATTERN   = os.getenv("SSO_URL_PATTERN", "")
SSO_USERNAME      = os.getenv("SSO_USERNAME", "")
SSO_PASSWORD      = os.getenv("SSO_PASSWORD", "")
SSO_USERNAME_SEL  = os.getenv("SSO_USERNAME_SELECTOR", "input[name='username']")
SSO_PASSWORD_SEL  = os.getenv("SSO_PASSWORD_SELECTOR", "input[name='password']")
SSO_SUBMIT_SEL    = os.getenv("SSO_SUBMIT_SELECTOR", "button[type='submit']")

SESSION_FILE      = os.path.expanduser("~/.jobcan_session.json")
BUTTON_SEL        = "#adit-button-push"
STATUS_SEL        = "#working_status"
WORKING_TEXT      = "勤務中"


class _NeedsAuth(Exception):
    """セッション切れで再認証が必要"""


def clock_action(currently_working: bool) -> bool:
    """
    打刻ボタンを押して新しい勤務状態を返す。
    MOCK=true の場合はブラウザを開かず状態を反転するだけ。
    """
    if MOCK:
        time.sleep(1.5)
        return not currently_working

    # セッションが存在する場合はまずヘッドレスで試みる
    if os.path.exists(SESSION_FILE):
        try:
            return _do_clock(currently_working, headless=True)
        except _NeedsAuth:
            print("[jobcan] セッション切れ。再認証が必要です。")

    # 認証が必要 → ブラウザを表示して 2FA を待つ
    import rumps
    rumps.notification("Jobcan", "認証が必要です", "ブラウザで2FA認証を完了してください")
    return _do_clock(currently_working, headless=False)


def _do_clock(currently_working: bool, headless: bool) -> bool:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        ctx_kwargs = {}
        if os.path.exists(SESSION_FILE):
            ctx_kwargs["storage_state"] = SESSION_FILE

        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        try:
            page.goto(JOBCAN_URL)
            page.wait_for_load_state("networkidle")

            # SSO にリダイレクトされた場合
            if SSO_URL_PATTERN and SSO_URL_PATTERN in page.url:
                if headless:
                    # ヘッドレスでは 2FA を処理できないので呼び出し元に通知
                    raise _NeedsAuth()
                # ブラウザ表示モード: 自動ログイン → 2FA 待機
                _handle_sso(page)
                if SSO_URL_PATTERN in page.url:
                    print("[jobcan] ブラウザで追加認証を完了してください（最大2分待機）...")
                    page.wait_for_url("**jobcan.jp**", timeout=120_000)

            # 打刻ボタンをクリック
            page.wait_for_selector(BUTTON_SEL, timeout=30_000)
            page.click(BUTTON_SEL)

            # 状態反映を待ってから確認
            time.sleep(2)
            status_text = page.text_content(STATUS_SEL) or ""
            is_working = WORKING_TEXT in status_text

            # セッション保存（次回ログイン省略）
            context.storage_state(path=SESSION_FILE)

            return is_working

        finally:
            context.close()
            browser.close()


def _handle_sso(page):
    # フォームが表示されるまで待機
    page.wait_for_selector("input[name='username']", state="visible")

    # ユーザー名・パスワード入力
    if SSO_USERNAME:
        page.fill(SSO_USERNAME_SEL, SSO_USERNAME)
    if SSO_PASSWORD:
        try:
            page.fill(SSO_PASSWORD_SEL, SSO_PASSWORD)
        except Exception:
            page.fill("input[type='password']", SSO_PASSWORD)

    # ログインボタンをクリック（複数のセレクタを順に試す）
    for sel in [SSO_SUBMIT_SEL,
                "#loginbtn",
                "input[name='loginbtn']",
                "input[type='submit']",
                "button[type='submit']",
                "button"]:
        try:
            page.click(sel, timeout=3000)
            break
        except Exception:
            continue
