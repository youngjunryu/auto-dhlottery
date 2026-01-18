import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from send_telegram import send_purchase_capture

load_dotenv()

DHLOTTERY_USERNAME = os.getenv('DHLOTTERY_USERNAME')
DHLOTTERY_PASSWORD = os.getenv('DHLOTTERY_PASSWORD')

MAIN_URL = 'https://www.dhlottery.co.kr/'
TOTAL_GAME_URL = 'https://el.dhlottery.co.kr/game/TotalGame.jsp?LottoId=LO40'
VIEWPORT = {'width': 1280, 'height': 720}
MY_NUMBERS_DIR = Path(__file__).parent / 'my_numbers'
MY_NUMBERS_DIR.mkdir(exist_ok=True)

SELECTORS = {
    'main_login_button': 'button#loginBtn',
    'user_id': 'input#inpUserId',
    'user_password': 'input#inpUserPswdEncn',
    'login_submit': 'button#btnLogin',
    'lotto_button': 'button#btnMoLtgmPrchs',
    'lotto_iframe': 'iframe#ifrm_tab',
    'auto_select': 'label[for="checkAutoSelect"]',
    'confirm_numbers': 'input#btnSelectNum',
    'buy_button': 'button#btnBuy',
    'popup_confirm': 'div.layer-alert#popupLayerConfirm div.btns input.button.confirm[value="확인"]',
}

LOGIN_SUCCESS_TEXTS = ('마이페이지', '로그아웃')


def _wait_and_click(page: Page, selector: str, description: str, timeout: int = 3000) -> None:
    page.wait_for_selector(selector, timeout=timeout)
    page.click(selector)
    print(f'✅ {description}: {selector}')


def _check_login_success(page: Page) -> bool:
    final_url = page.url
    print(f'📍 최종 URL: {final_url}')

    if 'user.do' in final_url or 'myPage' in final_url:
        return True

    return any(page.query_selector(f'text={text}') for text in LOGIN_SUCCESS_TEXTS)


def _resolve_lotto_frame(new_page: Page) -> Page:
    frame_target: Page = new_page

    try:
        new_page.wait_for_selector(SELECTORS['lotto_iframe'], timeout=5000)
        candidate = new_page.frame(name='ifrm_tab')
        if candidate:
            frame_target = candidate  # type: ignore[assignment]
    except Exception:
        pass

    if frame_target is new_page:
        for frame in new_page.frames:
            if 'ifrm_tab' in (frame.name or '') or any(keyword in (frame.url or '') for keyword in ('game645', 'olotto')):
                frame_target = frame
                break

    if frame_target is not new_page:
        print('🪟 iframe#ifrm_tab 내부에서 조작합니다.')
    else:
        print('ℹ️ iframe을 찾지 못해 현재 페이지에서 계속 진행합니다.')

    return frame_target  # type: ignore[return-value]


def main():
    print('🚀 동행복권 로그인 시작...')

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport=VIEWPORT)
        page = context.new_page()

        try:
            print('📄 동행복권 메인 페이지로 이동 중...')
            page.goto(MAIN_URL, wait_until='networkidle', timeout=60000)

            print('🔍 메인 페이지 로그인 버튼 클릭 시도...')
            _wait_and_click(page, SELECTORS['main_login_button'], '메인 페이지 로그인 버튼 클릭')
            page.wait_for_timeout(2000)
            print(f'📍 현재 URL: {page.url}')

            print('⏳ 로그인 폼 대기 중...')
            page.wait_for_selector(SELECTORS['user_id'], timeout=10000)

            print('⌨️  아이디 입력 중...')
            page.fill(SELECTORS['user_id'], DHLOTTERY_USERNAME)

            print('⌨️  비밀번호 입력 중...')
            page.fill(SELECTORS['user_password'], DHLOTTERY_PASSWORD)

            print('🔘 로그인 버튼 클릭 중...')
            _wait_and_click(page, SELECTORS['login_submit'], '로그인 버튼 클릭')
            page.wait_for_timeout(3000)

            if _check_login_success(page):
                print('✅ 로그인 성공!')
                page.wait_for_timeout(2000)

                print('🌐 TotalGame 페이지를 새 창에서 여는 중입니다...')
                new_page = context.new_page()
                try:
                    new_page.goto(TOTAL_GAME_URL, wait_until='domcontentloaded', timeout=60000)
                except PlaywrightTimeoutError:
                    print('⚠️ DOMContentLoaded 대기 중 타임아웃 발생. load 상태로 재시도합니다...')
                    try:
                        new_page.goto(TOTAL_GAME_URL, wait_until='load', timeout=60000)
                    except PlaywrightTimeoutError:
                        print('⚠️ load 상태 대기 중에도 타임아웃 발생. 현재 로딩된 상태로 계속 진행합니다.')
                new_page.wait_for_load_state('domcontentloaded', timeout=15000)
                print(f'✅ 새 창 로딩 완료!  새 창 URL: {new_page.url}')

                frame_target = _resolve_lotto_frame(new_page)

                auto_selector = SELECTORS['auto_select']
                frame_target.wait_for_selector(auto_selector, timeout=5000)
                frame_target.click(auto_selector)
                print(f'✅ 자동선택 옵션 클릭 완료! (선택자: {auto_selector})')
                frame_target.wait_for_timeout(1000)

                frame_target.wait_for_selector(SELECTORS['confirm_numbers'], timeout=10000)
                frame_target.click(SELECTORS['confirm_numbers'])
                print('✅ 확인 버튼 클릭 완료!')
                frame_target.wait_for_timeout(2000)

                frame_target.wait_for_selector(SELECTORS['buy_button'], timeout=10000)
                frame_target.click(SELECTORS['buy_button'])
                print('✅ 구매하기 버튼 클릭 완료!')
                frame_target.wait_for_timeout(2000)

                print('5️⃣  팝업 확인 버튼 클릭 중...')
                frame_target.wait_for_selector(SELECTORS['popup_confirm'], timeout=2000)
                frame_target.click(SELECTORS['popup_confirm'])
                print(f'✅ (프레임) 팝업 확인 버튼 클릭 완료! (선택자: {SELECTORS["popup_confirm"]})')
                frame_target.wait_for_timeout(1000)

                print('⌛ 결과 페이지 로딩을 기다리는 중입니다...')
                try:
                    new_page.wait_for_load_state('networkidle', timeout=15000)
                except Exception:
                    print('ℹ️ networkidle 대기 타임아웃 발생. domcontentloaded 상태를 기다립니다...')
                    new_page.wait_for_load_state('domcontentloaded', timeout=15000)
                new_page.wait_for_timeout(2000)

                screenshot_filename = f'my_numbers_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
                screenshot_path = MY_NUMBERS_DIR / screenshot_filename
                new_page.screenshot(path=str(screenshot_path), full_page=True)
                print(f'🖼️  팝업 확인 후 페이지 스크린샷 저장 완료: {screenshot_path}')

                print('✅ 모든 단계 완료!')
                print('⏸️  새 창을 5초간 열어둡니다...')
                new_page.wait_for_timeout(5000)

            else:
                print('⚠️  로그인 상태를 확인할 수 없습니다. 페이지를 확인해주세요.')
                print('⏸️  브라우저를 5초간 열어둡니다...')
                page.wait_for_timeout(5000)

        except Exception as error:
            print(f'❌ 오류 발생: {error}')
            print('⏸️  디버깅을 위해 브라우저를 5초간 열어둡니다...')
            page.wait_for_timeout(5000)
        finally:
            context.close()
            browser.close()
            print('👋 완료')


if __name__ == '__main__':
    main()
    send_purchase_capture()