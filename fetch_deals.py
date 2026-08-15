import os
import json
import time
import requests
from datetime import datetime, timedelta, timezone

# KST (한국 표준시) 설정
KST = timezone(timedelta(hours=9))
DATA_FILE = 'data.json'

# 1. 기존 data.json 읽어오기
try:
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        deals = json.load(f)
except Exception:
    deals = []

# 2. 만료된 상품 자동 삭제 (예: 24시간이 넘은 상품 제거)
now = datetime.now(KST)
valid_deals = []

for deal in deals:
    created_at_str = deal.get('createdAt')
    if created_at_str:
        created_at = datetime.fromisoformat(created_at_str)
        # 24시간 이내 등록된 아이템만 남김 (시간 조절 가능)
        if now - created_at < timedelta(hours=24):
            valid_deals.append(deal)

# 3. 쿠팡 파트너스 API로 최신 핫딜 가져오기 (예시)
def fetch_coupang_deals():
    # 저장소 Secrets에 저장한 API 키 불러오기
    access_key = os.environ.get('COUPANG_ACCESS_KEY')
    secret_key = os.environ.get('COUPANG_SECRET_KEY')
    
    new_items = []
    # ※ 쿠팡 파트너스 API 호출 로직이 들어가는 자리입니다.
    # 골드박스/타임딜 등의 데이터를 가져와 수집합니다.
    return new_items

# 4. 토스 핫딜 수집 (예시)
def fetch_toss_deals():
    new_items = []
    # ※ 토스 웹페이지 크롤링/데이터 수집 로직이 들어가는 자리입니다.
    return new_items

# 5. 새 상품 수집 후 중복 제거 및 등록시간 저장
fetched_items = fetch_coupang_deals() + fetch_toss_deals()

# 기존 링크와 중복되지 않는 신규 상품만 추가
existing_links = {d['link'] for d in valid_deals}
for item in fetched_items:
    if item['link'] not in existing_links:
        item['createdAt'] = now.isoformat() # 생성된 시각 기록
        valid_deals.insert(0, item) # 맨 앞에 추가

# 6. data.json 파일 업데이트 저장
with open(DATA_FILE, 'w', encoding='utf-8') as f:
    json.dump(valid_deals, f, ensure_ascii=False, indent=2)

print(f"업데이트 완료! 총 {len(valid_deals)}개 상품 유지 중.")
