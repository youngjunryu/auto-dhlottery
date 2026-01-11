import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# .env 파일 로드
load_dotenv()

DHLOTTERY_USERNAME = os.getenv('DHLOTTERY_USERNAME')
DHLOTTERY_PASSWORD = os.getenv('DHLOTTERY_PASSWORD')


def login():
    print('🚀 동행복권 로그인 시작...')

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)

        context = browser.new_context(
            viewport={'width': 1280, 'height': 720}
        )

        page = context.new_page()

        try:
            # 동행복권 메인 페이지로 이동
            print('📄 동행복권 메인 페이지로 이동 중...')
            page.goto('https://www.dhlottery.co.kr/', wait_until='networkidle')
            
            # 메인 페이지에서 로그인 버튼 클릭 시도
            login_button_selectors = 'button#loginBtn'

            print('🔍 메인 페이지 로그인 버튼 클릭 시도...')
            page.wait_for_selector(login_button_selectors, timeout=3000)
            page.click(login_button_selectors)
            page.wait_for_load_state('networkidle')
            print(f'✅ 메인 페이지 로그인 버튼 클릭: {login_button_selectors}')

            # 로그인 페이지 로딩 대기
            page.wait_for_timeout(2000)

            # 현재 URL 확인 (로그인 페이지로 이동했는지)
            current_url = page.url
            print(f'📍 현재 URL: {current_url}')

            # 로그인 폼이 나타날 때까지 대기
            print('⏳ 로그인 폼 대기 중...')
            try:
                page.wait_for_selector('input#inpUserId', timeout=10000)
            except Exception:
                raise

            # 아이디 입력
            print('⌨️  아이디 입력 중...')
            page.fill('input#inpUserId', DHLOTTERY_USERNAME)

            # 비밀번호 입력
            print('⌨️  비밀번호 입력 중...')
            page.fill('input#inpUserPswdEncn', DHLOTTERY_PASSWORD)

            # 로그인 버튼 클릭
            print('🔘 로그인 버튼 클릭 중...')
            login_button_selectors = 'button#btnLogin'
            page.click(login_button_selectors)
            print(f'✅ 로그인 버튼 클릭: {login_button_selectors}')

            # 로그인 처리 대기
            page.wait_for_timeout(3000)

            # 로그인 성공 여부 확인
            final_url = page.url
            print(f'📍 최종 URL: {final_url}')

            check_user_do = 'user.do' in final_url
            check_my_page = 'myPage' in final_url
            check_mypage_text = page.query_selector('text=마이페이지') is not None
            check_logout_text = page.query_selector('text=로그아웃') is not None
            is_logged_in = check_user_do or check_my_page or check_mypage_text or check_logout_text

            if is_logged_in:
                print('✅ 로그인 성공!')

                # 로또6/45 버튼 클릭 준비
                page.wait_for_timeout(2000)

                try:
                    page.wait_for_selector('button#btnMoLtgmPrchs', timeout=10000)
                    print('✅ 로또6/45 버튼이 페이지에 나타났습니다.')
                except Exception:
                    print('⚠️  로또6/45 버튼을 기다리는 중 타임아웃. 계속 진행합니다...')

                with context.expect_page() as new_page_info:
                    lotto_button_selectors = 'button#btnMoLtgmPrchs'
                    page.click(lotto_button_selectors)
                    print(f'✅ 로또6/45 버튼 클릭: {lotto_button_selectors}')

                new_page = new_page_info.value
                new_page.wait_for_load_state('networkidle')
                print(f'✅ 새 창 로딩 완료!  새 창 URL: {new_page.url}')

                # 새 창 내에서 조작할 프레임 결정
                frame_target = new_page
                try:
                    new_page.wait_for_selector('iframe#ifrm_tab', timeout=5000)
                    candidate = new_page.frame(name='ifrm_tab')
                    if candidate:
                        frame_target = candidate
                except Exception:
                    pass

                if frame_target is new_page:
                    for frame in new_page.frames:
                        frame_name = frame.name or ''
                        frame_url = frame.url or ''
                        if 'ifrm_tab' in frame_name or 'game645' in frame_url or 'olotto' in frame_url:
                            frame_target = frame
                            break

                if frame_target is not new_page:
                    print('🪟 iframe#ifrm_tab 내부에서 조작합니다.')
                else:
                    print('ℹ️ iframe을 찾지 못해 현재 페이지에서 계속 진행합니다.')

                # 자동선택 옵션 활성화
                auto_selectors ='label[for="checkAutoSelect"]'
                frame_target.wait_for_selector(auto_selectors, timeout=5000)
                frame_target.click(auto_selectors)
                print(f'✅ 자동선택 옵션 클릭 완료! (선택자: {auto_selectors})')
                frame_target.wait_for_timeout(1000)

                # 확인 버튼 클릭
                frame_target.wait_for_selector('input#btnSelectNum', timeout=10000)
                frame_target.click('input#btnSelectNum')
                print('✅ 확인 버튼 클릭 완료!')
                frame_target.wait_for_timeout(2000)

                # 구매하기 버튼 클릭
                frame_target.wait_for_selector('button#btnBuy', timeout=10000)
                frame_target.click('button#btnBuy')
                print('✅ 구매하기 버튼 클릭 완료!')
                frame_target.wait_for_timeout(2000)
                
                # 팝업 확인 버튼 클릭
                print('5️⃣  팝업 확인 버튼 클릭 중...')
                
                # frame_target 내부에서 시도
                popup_confirm_selectors = 'div.layer-alert#popupLayerConfirm div.btns input.button.confirm[value="확인"]'
                frame_target.wait_for_selector(popup_confirm_selectors, timeout=2000)
                # frame_target.click(popup_confirm_selectors)
                print(f'✅ (프레임) 팝업 확인 버튼 클릭 완료! (선택자: {popup_confirm_selectors})')
                frame_target.wait_for_timeout(1000)

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
            print('👋 완료')


if __name__ == '__main__':
    login()
