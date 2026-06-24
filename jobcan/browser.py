import os
import time
from dotenv import load_dotenv

load_dotenv()

MOCK              = os.getenv("MOCK", "false").lower() == "true"
JOBCAN_URL        = os.getenv("JOBCAN_URL", "https://ssl.jobcan.jp/employee")
JOBCAN_SSO_URL    = os.getenv("JOBCAN_SSO_URL", "")
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
    """打刻ボタンを押して新しい勤務状態を返す。"""
    if MOCK:
        time.sleep(1.5)
        return not currently_working

    if os.path.exists(SESSION_FILE):
        try:
            return _do(currently_working, headless=True)
        except _NeedsAuth:
            print("[jobcan] セッション切れ。再認証が必要です。", flush=True)

    import rumps
    rumps.notification("Jobcan", "認証が必要です", "ブラウザで2FA認証を完了してください")
    return _do(currently_working, headless=False)


def _do(currently_working: bool, headless: bool) -> bool:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        ctx_kwargs = {}
        if os.path.exists(SESSION_FILE):
            ctx_kwargs["storage_state"] = SESSION_FILE

        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        try:
            print(f"[browser] アクセス中: {JOBCAN_URL} (headless={headless})", flush=True)
            page.goto(JOBCAN_URL, wait_until="load")
            print(f"[browser] 現在のURL: {page.url}", flush=True)

            button = page.query_selector(BUTTON_SEL)
            if button is None:
                if headless:
                    print("[browser] 打刻ボタンなし → 再認証が必要", flush=True)
                    raise _NeedsAuth()
                if JOBCAN_SSO_URL:
                    print(f"[browser] SSO URL へ移動: {JOBCAN_SSO_URL}", flush=True)
                    page.goto(JOBCAN_SSO_URL, wait_until="load")
                    print(f"[browser] SSO 後URL: {page.url}", flush=True)
                if SSO_URL_PATTERN and SSO_URL_PATTERN in page.url:
                    _handle_sso(page)
                if "ssl.jobcan.jp" not in page.url:
                    print("[jobcan] 認証を完了してください（最大2分待機）...", flush=True)
                    page.wait_for_url("**/ssl.jobcan.jp/**", timeout=120_000)
                print(f"[browser] 認証後URL: {page.url}", flush=True)
                if "/employee" not in page.url:
                    page.goto(JOBCAN_URL, wait_until="load")
                    print(f"[browser] employee 移動後URL: {page.url}", flush=True)

            print(f"[browser] 打刻ボタン待機中...", flush=True)
            page.wait_for_selector(BUTTON_SEL, timeout=30_000)
            page.click(BUTTON_SEL)
            print(f"[browser] 打刻ボタンをクリック", flush=True)

            try:
                ok_sel = "button:has-text('OK'), button:has-text('はい'), input[value='OK']"
                page.wait_for_selector(ok_sel, timeout=3_000)
                page.click(ok_sel)
                print(f"[browser] 確認ダイアログをOK", flush=True)
            except Exception:
                pass

            page.wait_for_load_state("load")
            time.sleep(2)

            status_text = page.text_content(STATUS_SEL) or ""
            print(f"[browser] ステータス全文: {status_text.strip()!r}", flush=True)
            is_working = WORKING_TEXT in status_text
            print(f"[browser] is_working={is_working}", flush=True)

            context.storage_state(path=SESSION_FILE)
            return is_working

        finally:
            context.close()
            browser.close()


def _handle_sso(page):
    page.wait_for_selector(SSO_USERNAME_SEL, state="visible")
    if SSO_USERNAME:
        page.fill(SSO_USERNAME_SEL, SSO_USERNAME)

    password_filled = False
    if SSO_PASSWORD:
        for sel in [SSO_PASSWORD_SEL, "input[type='password']"]:
            try:
                page.wait_for_selector(sel, state="visible", timeout=2_000)
                page.fill(sel, SSO_PASSWORD)
                password_filled = True
                break
            except Exception:
                continue

    _sso_click_submit(page)

    if not password_filled and SSO_PASSWORD:
        try:
            page.wait_for_selector("input[type='password']", state="visible", timeout=10_000)
            page.fill("input[type='password']", SSO_PASSWORD)
        except Exception:
            pass

    # ２段階認証ボタンが表示されていればクリック（汎用フォールバックより先に試みる）
    try:
        page.wait_for_selector("button:has-text('２段階認証')", state="visible", timeout=3_000)
        page.click("button:has-text('２段階認証')")
        print("[browser] ２段階認証でログインをクリック", flush=True)
        return
    except Exception:
        pass

    _sso_click_submit(page)


def _sso_click_submit(page):
    for sel in [SSO_SUBMIT_SEL,
                "#loginbtn",
                "input[name='loginbtn']",
                "input[type='submit']",
                "button[type='submit']",
                "button"]:
        try:
            page.click(sel, timeout=3_000)
            return
        except Exception:
            continue
