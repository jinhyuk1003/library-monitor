# -*- coding: utf-8 -*-
"""
빈자리 알림 모듈 - 카카오톡 나에게 보내기
대상: 서현도서관(PLR007) 노트북실, 잔여 SEAT_THRESHOLD석 이하 시 발송
쿨다운: 같은 열람실 COOLDOWN_MIN분 내 중복 발송 방지
"""

import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KAKAO_REST_KEY      = os.getenv("KAKAO_REST_KEY", "")
KAKAO_REFRESH_TOKEN = os.getenv("KAKAO_REFRESH_TOKEN", "")
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", "")
ALERT_ENABLED       = os.getenv("ALERT_ENABLED", "true").lower() == "true"
SUPABASE_URL        = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY        = os.getenv("SUPABASE_KEY", "")

KST = ZoneInfo("Asia/Seoul")

ALERT_LIB_ID   = "PLR007"   # 서현도서관
ALERT_KEYWORD  = "노트북"    # room_name에 이 문자열 포함 시 대상
FULL_THRESHOLD = 0          # 이 값 이하면 "만석"으로 간주 (기본 0석)


def _get_access_token() -> str:
    params = {
        "grant_type": "refresh_token",
        "client_id": KAKAO_REST_KEY,
        "refresh_token": KAKAO_REFRESH_TOKEN,
    }
    if KAKAO_CLIENT_SECRET:
        params["client_secret"] = KAKAO_CLIENT_SECRET
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        "https://kauth.kakao.com/oauth/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())["access_token"]


def _send_message(access_token: str, text: str):
    template = json.dumps({
        "object_type": "text",
        "text": text,
        "link": {"web_url": "", "mobile_web_url": ""},
    }, ensure_ascii=False)
    data = urllib.parse.urlencode({"template_object": template}).encode()
    req = urllib.request.Request(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        data=data,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
    if result.get("result_code") != 0:
        raise RuntimeError(f"카카오 전송 실패: {result}")


def _get_prev_available(room_id: str) -> int | None:
    """직전 수집 기록의 잔여석 반환 (Supabase에서 최근 2개 조회)"""
    if not (SUPABASE_URL and SUPABASE_KEY):
        return None
    from supabase import create_client
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    result = (
        client.table("room_status")
        .select("available")
        .eq("room_id", room_id)
        .order("collected_at", desc=True)
        .limit(2)
        .execute()
    )
    if len(result.data) < 2:
        return None
    return result.data[1]["available"]  # [0]=방금 저장한 현재, [1]=직전


def check_and_alert(rooms: list[dict]):
    """만석 → 빈자리 전환 시 카카오톡 발송"""
    if not ALERT_ENABLED:
        return
    if not (KAKAO_REST_KEY and KAKAO_REFRESH_TOKEN):
        return

    targets = [
        r for r in rooms
        if r["lib_id"] == ALERT_LIB_ID and ALERT_KEYWORD in r["room_name"]
    ]

    for room in targets:
        current = room["available"]

        # 현재도 자리 없으면 패스
        if current <= FULL_THRESHOLD:
            continue

        # 직전 상태 확인
        prev = _get_prev_available(room["room_id"])
        if prev is None:
            continue

        # 직전이 만석이 아니었으면 패스 (이미 자리 있었음)
        if prev > FULL_THRESHOLD:
            continue

        # 만석 → 빈자리 전환 발생
        now_str = datetime.now(KST).strftime("%H:%M")
        msg = (
            f"📚 {room['lib_name']} {room['room_name']} 빈자리 생겼어요!\n"
            f"잔여 {current}석 / 전체 {room['total']}석\n"
            f"⏰ {now_str} KST"
        )
        try:
            token = _get_access_token()
            _send_message(token, msg)
            print(f"  [알림 발송] {room['room_name']} {prev}석→{current}석 전환 → 카카오톡 전송 완료")
        except Exception as e:
            print(f"  [알림 실패] {e}")
