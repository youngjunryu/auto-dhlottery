from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
MY_NUMBERS_DIR = BASE_DIR / "my_numbers"
WINNING_NUMBERS_DIR = BASE_DIR / "winning_numbers"

MY_NUMBERS_PATTERN = "my_numbers*.png"
WINNING_CONTENT_PATTERN = "winning_numbers_*.png"

CAPTURE_TARGETS: dict[str, tuple[Path, str, str]] = {
    "my_numbers": (MY_NUMBERS_DIR, MY_NUMBERS_PATTERN, "구매"),
    "winning_numbers": (WINNING_NUMBERS_DIR, WINNING_CONTENT_PATTERN, "당첨번호"),
}

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_CAPTION = os.getenv("TELEGRAM_CAPTION", "[동행복권]")


def _ensure_credentials() -> None:
    missing = [
        name
        for name, value in (
            ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
            ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"환경 변수 {', '.join(missing)} 가 설정되지 않았습니다. .env에 추가하세요.")


def _latest_screenshot(directory: Path, pattern: str) -> Path:
    if not directory.exists():
        raise FileNotFoundError(
            f"아직 캡쳐 디렉터리가 없습니다: {directory}. 먼저 캡쳐를 생성하세요."
        )

    screenshots = sorted(
        directory.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not screenshots:
        raise FileNotFoundError(
            f"{directory}에서 '{pattern}' 패턴과 일치하는 파일을 찾을 수 없습니다."
        )

    return screenshots[0]


def send_telegram_photo(photo_path: Path) -> None:
    _ensure_credentials()

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    caption = f"{TELEGRAM_CAPTION}\n({timestamp})"

    with photo_path.open("rb") as f:
        files = {"photo": (photo_path.name, f, "image/png")}
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": caption,
        }
        resp = requests.post(url, data=data, files=files, timeout=30)

    try:
        payload = resp.json()
    except Exception:
        raise RuntimeError(
            f"Telegram API 응답이 JSON이 아닙니다. status={resp.status_code}, text={resp.text}"
        )

    if not payload.get("ok"):
        raise RuntimeError(f"Telegram 전송 실패: {payload}")

    print("✅ 텔레그램 전송 완료!")


def _send_latest_capture(target: str) -> None:
    try:
        directory, pattern, label = CAPTURE_TARGETS[target]
    except KeyError as exc:
        available = ", ".join(CAPTURE_TARGETS.keys())
        raise ValueError(f"지원하지 않는 target '{target}'. 사용 가능: {available}") from exc

    latest = _latest_screenshot(directory, pattern)
    print(f"🖼️ 전송할 최신 {label} 캡쳐: {latest}")
    send_telegram_photo(latest)


def send_purchase_capture() -> None:
    _send_latest_capture("my_numbers")


def send_winning_numbers_capture() -> None:
    _send_latest_capture("winning_numbers")
