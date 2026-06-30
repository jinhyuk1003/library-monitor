# -*- coding: utf-8 -*-
"""
성남시 공공도서관 열람실 실시간 좌석 현황 수집기
공식 API: 행정안전부 한국지역정보개발원 (data.go.kr 15142580)

[필드 주의] API의 useSeatCnt/rmndSeatCnt 명칭이 실제 의미와 반대
    - useSeatCnt  -> 실제 잔여좌석수 (available)
    - rmndSeatCnt -> 실제 이용중좌석수 (in use)
    iframe 직접 스크래핑과 교차검증으로 확인됨
"""

import sys
import os
import json
import sqlite3
import urllib.request
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ── 설정 ──────────────────────────────────────────────────────────────────────
API_KEY      = os.getenv("LIBRARY_API_KEY", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

API_URL = "https://apis.data.go.kr/B551982/plr_v2/rlt_rdrm_info_v2"
STD_CD  = "4113000000"  # 경기도 성남시

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seohyeon_library.db")
HEADERS = {"User-Agent": "Mozilla/5.0"}
KST     = ZoneInfo("Asia/Seoul")

OPEN_HOUR  = 9   # 09:00 KST
CLOSE_HOUR = 22  # 22:00 KST
# ─────────────────────────────────────────────────────────────────────────────


def is_open_hours() -> bool:
    """도서관 운영시간(09:00~22:00 KST) 여부"""
    h = datetime.now(KST).hour
    return OPEN_HOUR <= h < CLOSE_HOUR


# ── 데이터 수집 ───────────────────────────────────────────────────────────────

def fetch_raw() -> list[dict]:
    """성남시 전체 열람실 데이터 수신 (14개 도서관)"""
    encoded = urllib.parse.quote(API_KEY, safe="")
    url = (
        f"{API_URL}?serviceKey={encoded}"
        f"&type=json&numOfRows=200&pageNo=1&stdgCd={STD_CD}"
    )
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    items = data.get("body", {}).get("item", [])
    if isinstance(items, dict):
        items = [items]
    return items


# ── 파싱 ─────────────────────────────────────────────────────────────────────

def parse_room(raw: dict) -> dict:
    """
    API 원본 -> 올바른 의미로 변환
    [주의] useSeatCnt / rmndSeatCnt 스왑 적용 (교차검증 완료)
    """
    total     = int(raw.get("tseatCnt")    or 0)
    in_use    = int(raw.get("rmndSeatCnt") or 0)  # API명: rmnd -> 실제: 이용중
    available = int(raw.get("useSeatCnt")  or 0)  # API명: use  -> 실제: 잔여
    reserved  = int(raw.get("rsvtSeatCnt") or 0)
    usage_pct = round(in_use / total * 100, 1) if total else 0.0

    raw_dt = raw.get("totDt", "")
    try:
        collected_at = datetime.strptime(raw_dt, "%Y%m%d%H%M%S").replace(tzinfo=KST)
    except ValueError:
        collected_at = datetime.now(KST)

    return {
        "lib_id":       raw.get("pblibId", ""),
        "lib_name":     raw.get("pblibNm", ""),
        "room_id":      raw.get("rdrmId", ""),
        "room_name":    raw.get("rdrmNm", ""),
        "floor":        raw.get("bldgFlrExpln", ""),
        "total":        total,
        "in_use":       in_use,
        "available":    available,
        "reserved":     reserved,
        "usage_pct":    usage_pct,
        "collected_at": collected_at.isoformat(),
        "fetched_at":   datetime.now(KST).isoformat(),
    }


# ── 출력 ─────────────────────────────────────────────────────────────────────

def print_status(rooms: list[dict]):
    now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    print(f"\n{'=' * 65}")
    print(f"  성남시 도서관 열람실 현황  ({now_str} KST)")
    print(f"{'=' * 65}")

    libs: dict[str, list] = {}
    for r in rooms:
        libs.setdefault(r["lib_id"], []).append(r)

    for lib_id, rs in sorted(libs.items()):
        print(f"\n  [{lib_id}] {rs[0]['lib_name']}")
        print(f"  {'열람실':<22} {'총':>4} {'이용중':>6} {'잔여':>6} {'이용률':>7}")
        print(f"  {'-' * 45}")
        for r in rs:
            filled = int(r["usage_pct"] / 5)
            bar = "#" * filled + "-" * (20 - filled)
            print(f"  {r['room_name']:<22} {r['total']:>4} {r['in_use']:>6} {r['available']:>6} {r['usage_pct']:>6.1f}%")
            print(f"  [{bar}]")

    print(f"\n{'=' * 65}")


# ── Supabase 저장 ─────────────────────────────────────────────────────────────

def save_to_supabase(rooms: list[dict]) -> int:
    from supabase import create_client
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    result = client.table("room_status").insert(rooms).execute()
    return len(result.data)


# ── SQLite 저장 (로컬 fallback) ───────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS room_status (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            lib_id       TEXT,
            lib_name     TEXT,
            room_id      TEXT NOT NULL,
            room_name    TEXT,
            floor        TEXT,
            total        INTEGER,
            in_use       INTEGER,
            available    INTEGER,
            reserved     INTEGER,
            usage_pct    REAL,
            collected_at TEXT,
            fetched_at   TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_collected ON room_status(collected_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lib ON room_status(lib_id)")
    conn.commit()
    conn.close()


def save_to_db(rooms: list[dict]):
    conn = sqlite3.connect(DB_PATH)
    conn.executemany("""
        INSERT INTO room_status
          (lib_id, lib_name, room_id, room_name, floor,
           total, in_use, available, reserved, usage_pct,
           collected_at, fetched_at)
        VALUES (:lib_id,:lib_name,:room_id,:room_name,:floor,
                :total,:in_use,:available,:reserved,:usage_pct,
                :collected_at,:fetched_at)
    """, rooms)
    conn.commit()
    conn.close()


# ── 진입점 ────────────────────────────────────────────────────────────────────

def collect_once(verbose: bool = True) -> list[dict]:
    if not is_open_hours():
        now_str = datetime.now(KST).strftime("%H:%M")
        print(f"[SKIP] 운영시간 외 ({now_str} KST) - 수집 생략")
        return []

    raw_list = fetch_raw()
    rooms = [parse_room(r) for r in raw_list]

    if verbose:
        print_status(rooms)

    if SUPABASE_URL and SUPABASE_KEY:
        n = save_to_supabase(rooms)
        print(f"  -> Supabase 저장: {n}행")
    else:
        init_db()
        save_to_db(rooms)
        print(f"  -> SQLite 저장: {DB_PATH} ({len(rooms)}행)")

    return rooms


if __name__ == "__main__":
    collect_once()
