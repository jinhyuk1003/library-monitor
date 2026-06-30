"""
스케줄러: 10분마다 자동 수집
실행: python collect.py
"""

import time
import schedule
from fetch import collect_once

INTERVAL_MINUTES = 10


def job():
    try:
        collect_once(save=True, verbose=True)
    except Exception as e:
        print(f"[오류] {e}")


print(f"서현도서관 수집 시작 (매 {INTERVAL_MINUTES}분)")
job()  # 시작 즉시 1회 실행
schedule.every(INTERVAL_MINUTES).minutes.do(job)

while True:
    schedule.run_pending()
    time.sleep(30)
