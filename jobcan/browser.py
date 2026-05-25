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


def clock_action(currently_working: bool) -> bool:
    """
    打刻ボタンを押して新しい勤務状態を返す。
    MOCK=true の場合はブラウザを開かず状態を反転するだけ。
    """
    if MOCK:
        time.sleep(1.5)
        return not currently_working

    return _browser_clock(currently_working)


def _browser_clock(currently_working: bool) -> bool:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        ctx_kwargs = {}
        if os.path.exists(SESSION_FILE):
            ctx_kwargs["storage_state"] = SESSION_FILE

        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        try:
            page.goto(JOBCAN_URL)
            page.wait_for_load_state("networkidle")

            # 大学 SSO にリダイレクトされた場合に自動ログイン
            if SSO_URL_PATTERN and SSO_URL_PATTERN in page.url:
                _handle_sso(page)
                page.wait_for_load_state("networkidle")

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
    if SSO_USERNAME:
        page.fill(SSO_USERNAME_SEL, SSO_USERNAME)
    if SSO_PASSWORD:
        page.fill(SSO_PASSWORD_SEL, SSO_PASSWORD)
        page.click(SSO_SUBMIT_SEL)
