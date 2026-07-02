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
            return _do(currently_working)
        except _NeedsAuth:
            print("[jobcan] セッション切れ。再認証します。", flush=True)

    import rumps
    rumps.notification("Jobcan", "認証が必要です", "KINDAIログインを開始します")
    return _do(currently_working, allow_sso=True)


def _do(currently_working: bool, allow_sso: bool = False) -> bool:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        ctx_kwargs = {}
        if os.path.exists(SESSION_FILE):
            ctx_kwargs["storage_state"] = SESSION_FILE

        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        try:
            print(f"[browser] アクセス中: {JOBCAN_URL} (allow_sso={allow_sso})", flush=True)
            page.goto(JOBCAN_URL, wait_until="load")
            print(f"[browser] 現在のURL: {page.url}", flush=True)

            button = page.query_selector(BUTTON_SEL)
            if button is None:
                if not allow_sso:
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
    print(f"[sso] 開始 URL: {page.url}", flush=True)
    try:
        page.wait_for_selector(SSO_USERNAME_SEL, state="visible", timeout=10_000)
    except Exception:
        print(f"[sso] ユーザー名フィールド({SSO_USERNAME_SEL})が見つからず", flush=True)
        return
    print(f"[sso] ユーザー名フィールド発見", flush=True)

    if SSO_USERNAME:
        page.fill(SSO_USERNAME_SEL, SSO_USERNAME)
        page.press(SSO_USERNAME_SEL, "Enter")  # ID確定→パスワード画面へ遷移
        print(f"[sso] ユーザー名入力・Enter送信完了", flush=True)

    # パスワードフィールドが現れるまで待機
    print("[sso] パスワードフィールド待機中...", flush=True)
    try:
        page.wait_for_selector("input[type='password']", state="visible", timeout=10_000)
        if SSO_PASSWORD:
            page.fill("input[type='password']", SSO_PASSWORD)
            print("[sso] パスワード入力完了", flush=True)
    except Exception as e:
        print(f"[sso] パスワード入力失敗: {e}", flush=True)

    # ２段階認証ボタンをクリック（KINDAI は input#loginbtn）
    print("[sso] ２段階認証ボタン探索中...", flush=True)
    clicked = False
    for sel in ["#loginbtn", "input[name='loginbtn']",
                "button:has-text('２段階認証')", "text=２段階認証でログイン"]:
        try:
            page.wait_for_selector(sel, state="visible", timeout=3_000)
            page.click(sel)
            print(f"[browser] ２段階認証でログインをクリック ({sel})", flush=True)
            clicked = True
            break
        except Exception:
            continue

    if not clicked:
        _sso_click_submit(page)

    _handle_confirm_code(page)


def _handle_confirm_code(page):
    """メール確認コード入力画面を処理する。"""
    time.sleep(3)
    conf_input = page.query_selector("input[placeholder='確認コード']")
    if conf_input is None:
        print(f"[sso] 確認コード画面なし URL: {page.url}", flush=True)
        return

    print("[sso] 確認コード入力画面を検出", flush=True)

    # 「30日間スキップ」チェックボックスを確実にONにする
    skip_cb = page.query_selector("input[type='checkbox']")
    if skip_cb and not skip_cb.is_checked():
        skip_cb.check()
        print("[sso] 30日スキップ チェックON", flush=True)

    # osascript でダイアログ表示（バックグラウンドスレッドから安全に呼べる）
    import subprocess
    print("[sso] 確認コード入力ダイアログを表示中...", flush=True)
    result = subprocess.run(
        ["osascript", "-e",
         'display dialog "KINDAIのメールアドレスに届いた確認コードを入力してください" '
         'default answer "" with title "KINDAI 確認コード" '
         'buttons {"キャンセル", "ログイン"} default button "ログイン"'],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        raise Exception("確認コード入力がキャンセルされました")

    # "button returned:ログイン, text returned:123456" を解析
    code = result.stdout.strip().split("text returned:")[-1].strip()
    if not code:
        raise Exception("確認コードが空です")

    print(f"[sso] 確認コードを入力: {'*' * len(code)}", flush=True)
    page.fill("input[placeholder='確認コード']", code)
    # Enterキーで送信（ボタンセレクタに依存しない）
    page.press("input[placeholder='確認コード']", "Enter")
    print("[sso] 確認コードを送信", flush=True)


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
