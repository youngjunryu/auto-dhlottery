from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError, sync_playwright

from send_email import send_winning_numbers_capture

NAVER_URL = "https://www.naver.com"
SEARCH_TERM = "로또당첨번호"
VIEWPORT = {"width": 1280, "height": 720}
WINNING_NUMBERS_DIR = Path(__file__).parent / "winning_numbers"
WINNING_NUMBERS_DIR.mkdir(exist_ok=True)

SEARCH_INPUT_SELECTOR = "input[name=\"query\"]"
CONTENT_AREA_SELECTOR = "div.content_area"


def capture_naver_search(term: str = SEARCH_TERM) -> Path:
    """Search the provided term on Naver and capture a screenshot of the result page."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = WINNING_NUMBERS_DIR / f"winning_numbers_{timestamp}.png"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport=VIEWPORT)
        page = context.new_page()

        print("🚀 네이버 페이지로 이동 중...")
        page.goto(NAVER_URL, wait_until="networkidle", timeout=60000)

        print("⌛ 검색창 로딩 대기 중...")
        page.wait_for_selector(SEARCH_INPUT_SELECTOR, timeout=10000)

        print(f"⌨️  '{term}' 검색어 입력 중...")
        page.fill(SEARCH_INPUT_SELECTOR, term)
        page.keyboard.press("Enter")

        print("🔍 검색 결과 페이지 로딩 대기 중...")
        try:
            content_area = page.wait_for_selector(CONTENT_AREA_SELECTOR, timeout=10000)
        except TimeoutError:
            print("⚠️  content_area 요소를 찾지 못했습니다. 전체 페이지 스크린샷으로 대체합니다.")
            page.screenshot(path=str(screenshot_path), full_page=True)
        else:
            print("🧩 content_area 요소를 찾았습니다. 해당 영역만 캡처합니다.")
            content_area.screenshot(path=str(screenshot_path))

        print(f"🖼️  검색 결과 스크린샷 저장 완료: {screenshot_path}")

        context.close()
        browser.close()

    return screenshot_path


def main() -> None:
    screenshot = capture_naver_search()
    print(f"📁 생성된 스크린샷: {screenshot}")


if __name__ == "__main__":
    main()
    send_winning_numbers_capture()
