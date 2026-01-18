from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Union

from dotenv import load_dotenv
from playwright.sync_api import (
    Page,
    Frame,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from send_telegram import send_purchase_capture

load_dotenv()

DHLOTTERY_USERNAME = os.getenv("DHLOTTERY_USERNAME")
DHLOTTERY_PASSWORD = os.getenv("DHLOTTERY_PASSWORD")

MAIN_URL = "https://www.dhlottery.co.kr/"
VIEWPORT = {"width": 1280, "height": 720}

MY_NUMBERS_DIR = Path(__file__).parent / "my_numbers"
MY_NUMBERS_DIR.mkdir(exist_ok=True)

SELECTORS = {
    "main_login_button": "button#loginBtn",
    "user_id": "input#inpUserId",
    "user_password": "input#inpUserPswdEncn",
    "login_submit": "button#btnLogin",

    # ✅ 메인에서 “구매하기” 진입 버튼(정상 플로우)
    "lotto_button": "button#btnMoLtgmPrchs",

    "lotto_iframe": "iframe#ifrm_tab",
    "auto_select": 'label[for="checkAutoSelect"]',
    "confirm_numbers": "input#btnSelectNum",
    "buy_button": "button#btnBuy",
    "popup_confirm": 'div.layer-alert#popupLayerConfirm div.btns input.button.confirm[value="확인"]',
}

LOGIN_SUCCESS_TEXTS = ("마이페이지", "로그아웃")
Target = Union[Page, Frame]


def _print_debug(page: Page) -> None:
    try:
        ua = page.evaluate("() => navigator.userAgent")
    except Exception:
        ua = "(failed)"
    print(f"🧾 Debug URL: {page.url}")
    print(f"🧾 Debug UA : {ua}")


def _goto(page: Page, url: str, *, wait_until: str = "domcontentloaded", timeout: int = 60_000) -> None:
    try:
        page.goto(url, wait_until=wait_until, timeout=timeout)
    except PlaywrightTimeoutError:
        page.goto(url, wait_until="load", timeout=timeout)


def _wait_and_click(target: Target, selector: str, description: str, timeout: int = 15_000) -> None:
    target.wait_for_selector(selector, timeout=timeout)
    target.click(selector)
    print(f"✅ {description}: {selector}")


def _check_login_success(page: Page) -> bool:
    u = page.url
    if "user.do" in u or "myPage" in u:
        return True
    return any(page.query_selector(f"text={t}") for t in LOGIN_SUCCESS_TEXTS)


def _resolve_lotto_target(popup: Page) -> Target:
    # 모바일이면 여기서 바로 실패(구매 UI 없음)
    if "m.dhlottery.co.kr" in popup.url:
        raise RuntimeError(f"모바일 사이트로 리다이렉트됨: {popup.url}")

    # 우선 이름으로 frame 찾기
    f = popup.frame(name="ifrm_tab")
    if f:
        print("🪟 iframe(ifrm_tab) 내부에서 조작합니다.")
        return f

    # selector로 iframe 확인 후 다시
    try:
        popup.wait_for_selector(SELECTORS["lotto_iframe"], timeout=7_000)
        f = popup.frame(name="ifrm_tab")
        if f:
            print("🪟 iframe(ifrm_tab) 내부에서 조작합니다.")
            return f
    except Exception:
        pass

    # frames 전체 훑기
    for fr in popup.frames:
        n = fr.name or ""
        u = fr.url or ""
        if "ifrm_tab" in n or any(k in u for k in ("game645", "olotto", "TotalGame", "game")):
            print(f"🪟 frame 탐색으로 타겟 결정: name={n}, url={u}")
            return fr

    print("ℹ️ iframe을 찾지 못해 현재 페이지에서 계속 진행합니다.")
    return popup


def _purchase_flow(popup: Page) -> Path:
    target = _resolve_lotto_target(popup)

    _wait_and_click(target, SELECTORS["auto_select"], "자동선택 옵션 클릭", timeout=20_000)
    target.wait_for_timeout(1_000)

    _wait_and_click(target, SELECTORS["confirm_numbers"], "확인(번호 확정) 버튼 클릭", timeout=20_000)
    target.wait_for_timeout(1_500)

    _wait_and_click(target, SELECTORS["buy_button"], "구매하기 버튼 클릭", timeout=20_000)
    target.wait_for_timeout(1_500)

    _wait_and_click(target, SELECTORS["popup_confirm"], "팝업 확인 버튼 클릭", timeout=20_000)
    target.wait_for_timeout(1_000)

    # 결과 안정화
    try:
        popup.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        try:
            popup.wait_for_load_state("domcontentloaded", timeout=15_000)
        except Exception:
            pass
    popup.wait_for_timeout(2_000)

    screenshot_filename = f"my_numbers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    screenshot_path = MY_NUMBERS_DIR / screenshot_filename
    popup.screenshot(path=str(screenshot_path), full_page=True)
    print(f"🖼️ 스크린샷 저장 완료: {screenshot_path}")

    return screenshot_path


def main() -> None:
    if not DHLOTTERY_USERNAME or not DHLOTTERY_PASSWORD:
        raise RuntimeError("환경변수 DHLOTTERY_USERNAME / DHLOTTERY_PASSWORD 가 설정되지 않았습니다.")

    print("🚀 동행복권 로그인 시작...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                # (선택) 자동화 흔적 완화. 안 해도 되지만 리다이렉트가 계속되면 도움될 수 있음.
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context = browser.new_context(
            viewport=VIEWPORT,
            is_mobile=False,
            has_touch=False,
            locale="ko-KR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )

        # (선택) webdriver 흔적 제거
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        page = context.new_page()

        try:
            print("📄 메인 페이지 이동...")
            _goto(page, MAIN_URL, wait_until="networkidle", timeout=60_000)
            _print_debug(page)

            print("🔑 로그인 버튼 클릭...")
            _wait_and_click(page, SELECTORS["main_login_button"], "메인 로그인 버튼 클릭")
            page.wait_for_timeout(1_000)

            print("⌨️ 로그인 폼 입력...")
            page.wait_for_selector(SELECTORS["user_id"], timeout=20_000)
            page.fill(SELECTORS["user_id"], DHLOTTERY_USERNAME)
            page.fill(SELECTORS["user_password"], DHLOTTERY_PASSWORD)

            _wait_and_click(page, SELECTORS["login_submit"], "로그인 제출")
            page.wait_for_timeout(2_000)

            if not _check_login_success(page):
                _print_debug(page)
                raise RuntimeError("로그인 성공 확인 실패(텍스트/URL 체크 실패)")

            print("✅ 로그인 성공!")
            page.wait_for_timeout(1_000)

            # ✅ 핵심: TotalGame을 직접 goto 하지 말고, 메인에서 구매 버튼 클릭 → 팝업/새창을 정상 플로우로 받기
            print("🧾 메인에서 구매 버튼 클릭 → 팝업 대기...")
            with page.expect_popup() as pop:
                _wait_and_click(page, SELECTORS["lotto_button"], "로또 구매 버튼 클릭", timeout=20_000)
            popup = pop.value

            # 팝업 로딩 안정화
            try:
                popup.wait_for_load_state("domcontentloaded", timeout=20_000)
            except Exception:
                pass

            print(f"✅ 팝업 오픈! URL: {popup.url}")
            _print_debug(popup)

            # 여기서도 모바일이면 실패
            if "m.dhlottery.co.kr" in popup.url:
                raise RuntimeError(f"모바일 사이트로 리다이렉트됨: {popup.url}")

            screenshot_path = _purchase_flow(popup)

            print("✅ 구매 플로우 완료")
            print(f"📦 스크린샷: {screenshot_path}")

        except Exception as e:
            print(f"❌ 오류 발생: {e}")
            try:
                _print_debug(page)
                fail_path = MY_NUMBERS_DIR / f"fail_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                page.screenshot(path=str(fail_path), full_page=True)
                print(f"🧯 실패 스크린샷 저장: {fail_path}")
            except Exception:
                pass
        finally:
            context.close()
            browser.close()
            print("👋 완료")


if __name__ == "__main__":
    main()
    send_purchase_capture()
