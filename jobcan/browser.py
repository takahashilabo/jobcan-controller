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
            print(f"[browser] アクセス中: {JOBCAN_URL} (headless={headless})", flush=True)
            page.goto(JOBCAN_URL)
            page.wait_for_load_state("networkidle")
            print(f"[browser] 現在のURL: {page.url}", flush=True)

            # 打刻ボタンの有無でセッション有効性を判定
            button = page.query_selector(BUTTON_SEL)
            if button is None:
                if headless:
                    print("[browser] 打刻ボタンなし → 再認証が必要", flush=True)
                    raise _NeedsAuth()
                # ブラウザ表示モード: 大学SSOへ直接ジャンプして自動ログイン
                if JOBCAN_SSO_URL:
                    print(f"[browser] SSO URL へ移動: {JOBCAN_SSO_URL}", flush=True)
                    page.goto(JOBCAN_SSO_URL)
                    page.wait_for_load_state("networkidle")
                    print(f"[browser] SSO 後URL: {page.url}", flush=True)
                if SSO_URL_PATTERN and SSO_URL_PATTERN in page.url:
                    _handle_sso(page)
                if SSO_URL_PATTERN and SSO_URL_PATTERN in page.url:
                    print("[jobcan] ブラウザで追加認証を完了してください（最大2分待機）...", flush=True)
                    # ssl.jobcan.jp に到達するまで待つ（id.jobcan.jp では不十分）
                    page.wait_for_url("**/ssl.jobcan.jp/**", timeout=120_000)
                print(f"[browser] 認証後URL: {page.url}", flush=True)
                # 打刻ページでなければ移動
                if "/employee" not in page.url:
                    page.goto(JOBCAN_URL)
                    page.wait_for_load_state("networkidle")
                    print(f"[browser] employee 移動後URL: {page.url}", flush=True)

            print(f"[browser] 打刻ボタン待機中...", flush=True)
            # 打刻ボタンをクリック
            page.wait_for_selector(BUTTON_SEL, timeout=30_000)
            page.click(BUTTON_SEL)
            print(f"[browser] 打刻ボタンをクリック", flush=True)

            # 状態反映を待ってから確認
            time.sleep(2)
            status_text = page.text_content(STATUS_SEL) or ""
            is_working = WORKING_TEXT in status_text
            print(f"[browser] ステータス: '{status_text.strip()}' → is_working={is_working}", flush=True)

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
