"""
dhlottery_auto_buy.py

동행복권(로또6/45) 자동선택 구매 플로우:
1) 메인 접속 -> 로그인
2) TotalGame 구매 페이지 이동(모바일 리다이렉트 방지: PC UA/컨텍스트 강제)
3) iframe(ifrm_tab) 또는 현재 페이지에서 자동선택/확인/구매/팝업확인
4) 결과 화면 스크린샷 저장
5) 텔레그램 전송(send_purchase_capture)

주의:
- 동행복권은 자동화/봇 탐지 또는 정책 변경에 따라 동작이 언제든 깨질 수 있음.
- 본 코드는 "모바일로 리다이렉트되어 selector/iframe이 없어서 타임아웃" 나는 문제를 우선 해결하는 방향.
"""

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
TOTAL_GAME_URL = "https://el.dhlottery.co.kr/game/TotalGame.jsp?LottoId=LO40"

VIEWPORT = {"width": 1280, "height": 720}

MY_NUMBERS_DIR = Path(__file__).parent / "my_numbers"
MY_NUMBERS_DIR.mkdir(exist_ok=True)

SELECTORS = {
    "main_login_button": "button#loginBtn",
    "user_id": "input#inpUserId",
    "user_password": "input#inpUserPswdEncn",
    "login_submit": "button#btnLogin",
    "lotto_iframe": "iframe#ifrm_tab",
    "auto_select": 'label[for="checkAutoSelect"]',
    "confirm_numbers": "input#btnSelectNum",
    "buy_button": "button#btnBuy",
    "popup_confirm": 'div.layer-alert#popupLayerConfirm div.btns input.button.confirm[value="확인"]',
}

LOGIN_SUCCESS_TEXTS = ("마이페이지", "로그아웃")

# Page 또는 Frame에서 동일하게 wait/click 등을 쓰기 위해 Union
Target = Union[Page, Frame]


def _wait_and_click(target: Target, selector: str, description: str, timeout: int = 10_000) -> None:
    target.wait_for_selector(selector, timeout=timeout)
    target.click(selector)
    print(f"✅ {description}: {selector}")


def _check_login_success(page: Page) -> bool:
    final_url = page.url
    print(f"📍 최종 URL: {final_url}")

    # URL 기반 힌트
    if "user.do" in final_url or "myPage" in final_url:
        return True

    # 텍스트 기반 힌트
    for text in LOGIN_SUCCESS_TEXTS:
        if page.query_selector(f"text={text}"):
            return True
    return False


def _print_basic_debug(page: Page) -> None:
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
        # 로딩 대기가 길어질 때 fallback
        print(f"⚠️ goto 타임아웃(wait_until={wait_until}). load로 재시도...")
        page.goto(url, wait_until="load", timeout=timeout)


def _goto_totalgame_force_pc(page: Page) -> None:
    """
    TotalGame 페이지로 이동하되, 모바일(m.)로 리다이렉트되면 실패 처리.
    (컨텍스트에서 이미 PC UA 강제하므로 보통 여기서 해결됨)
    """
    print("🌐 TotalGame 페이지로 이동 중...")
    _goto(page, TOTAL_GAME_URL, wait_until="domcontentloaded", timeout=60_000)

    # 추가로 load/domcontentloaded 상태 안정화
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except Exception:
        pass

    print(f"✅ TotalGame 로딩 완료! URL: {page.url}")
    _print_basic_debug(page)

    if "m.dhlottery.co.kr" in page.url:
        raise RuntimeError(f"모바일 사이트로 리다이렉트됨: {page.url}")


def _resolve_lotto_target(page: Page) -> Target:
    """
    TotalGame이 iframe(ifrm_tab) 안에서 동작하는 경우가 많아 iframe을 우선 타겟으로.
    못 찾으면 Page 자체를 타겟으로 사용.
    """
    if "m.dhlottery.co.kr" in page.url:
        raise RuntimeError(f"모바일 페이지라 구매 UI 없음: {page.url}")

    # name으로 먼저 시도
    frame = page.frame(name="ifrm_tab")
    if frame:
        print("🪟 iframe(ifrm_tab) 내부에서 조작합니다.")
        return frame

    # selector로 존재 확인 후 다시 시도
    try:
        page.wait_for_selector(SELECTORS["lotto_iframe"], timeout=5_000)
        frame = page.frame(name="ifrm_tab")
        if frame:
            print("🪟 iframe(ifrm_tab) 내부에서 조작합니다.")
            return frame
    except Exception:
        pass

    # frame 목록에서 URL/이름 키워드로 탐색
    for f in page.frames:
        n = f.name or ""
        u = f.url or ""
        if "ifrm_tab" in n or any(k in u for k in ("game645", "olotto", "TotalGame", "game")):
            print(f"🪟 frame 탐색으로 타겟 결정: name={n}, url={u}")
            return f

    print("ℹ️ iframe을 찾지 못해 현재 페이지에서 계속 진행합니다.")
    return page


def _purchase_flow(page: Page) -> Path:
    """
    TotalGame 내부에서 자동선택 -> 확인 -> 구매하기 -> 팝업 확인
    완료 후 스크린샷 저장 경로 반환
    """
    target = _resolve_lotto_target(page)

    # 자동선택
    _wait_and_click(target, SELECTORS["auto_select"], "자동선택 옵션 클릭", timeout=15_000)
    target.wait_for_timeout(1_000)

    # 확인(번호확정)
    _wait_and_click(target, SELECTORS["confirm_numbers"], "확인(번호 확정) 버튼 클릭", timeout=15_000)
    target.wait_for_timeout(2_000)

    # 구매하기
    _wait_and_click(target, SELECTORS["buy_button"], "구매하기 버튼 클릭", timeout=15_000)
    target.wait_for_timeout(2_000)

    # 팝업 확인
    print("🧩 팝업 확인 버튼 클릭 중...")
    _wait_and_click(target, SELECTORS["popup_confirm"], "팝업 확인 버튼 클릭", timeout=10_000)
    target.wait_for_timeout(1_000)

    # 결과 페이지 안정화
    print("⌛ 결과 페이지 로딩 대기...")
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15_000)
        except Exception:
            pass
    page.wait_for_timeout(2_000)

    # 스크린샷
    screenshot_filename = f"my_numbers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    screenshot_path = MY_NUMBERS_DIR / screenshot_filename
    page.screenshot(path=str(screenshot_path), full_page=True)
    print(f"🖼️ 스크린샷 저장 완료: {screenshot_path}")

    return screenshot_path


def main() -> None:
    if not DHLOTTERY_USERNAME or not DHLOTTERY_PASSWORD:
        raise RuntimeError("환경변수 DHLOTTERY_USERNAME / DHLOTTERY_PASSWORD 가 설정되지 않았습니다.")

    print("🚀 동행복권 로그인 시작...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # ✅ PC로 강제: 모바일 리다이렉트 방지 핵심
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

        page = context.new_page()

        try:
            print("📄 동행복권 메인 페이지로 이동 중...")
            _goto(page, MAIN_URL, wait_until="networkidle", timeout=60_000)
            _print_basic_debug(page)

            print("🔍 메인 페이지 로그인 버튼 클릭 시도...")
            _wait_and_click(page, SELECTORS["main_login_button"], "메인 페이지 로그인 버튼 클릭", timeout=15_000)
            page.wait_for_timeout(1_500)

            print("⏳ 로그인 폼 대기 중...")
            page.wait_for_selector(SELECTORS["user_id"], timeout=15_000)

            print("⌨️ 아이디 입력 중...")
            page.fill(SELECTORS["user_id"], DHLOTTERY_USERNAME)

            print("⌨️ 비밀번호 입력 중...")
            page.fill(SELECTORS["user_password"], DHLOTTERY_PASSWORD)

            print("🔘 로그인 버튼 클릭 중...")
            _wait_and_click(page, SELECTORS["login_submit"], "로그인 버튼 클릭", timeout=15_000)
            page.wait_for_timeout(2_500)

            if not _check_login_success(page):
                _print_basic_debug(page)
                raise RuntimeError("로그인 성공을 확인하지 못했습니다(텍스트/URL 체크 실패).")

            print("✅ 로그인 성공!")
            page.wait_for_timeout(1_000)

            # TotalGame 이동 (새 창 X: 같은 page에서 진행)
            _goto_totalgame_force_pc(page)

            # 구매 플로우
            screenshot_path = _purchase_flow(page)

            print("✅ 모든 단계 완료!")
            print(f"📦 결과 스크린샷: {screenshot_path}")

            # 디버깅용 대기 (원하면 제거)
            page.wait_for_timeout(2_000)

        except Exception as e:
            print(f"❌ 오류 발생: {e}")
            try:
                _print_basic_debug(page)
                # 실패 시 스크린샷 남기기
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
