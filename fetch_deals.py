import os
import json
import time
import hmac
import hashlib
import requests
from datetime import datetime, timedelta, timezone

# KST (한국 표준시) 설정
KST = timezone(timedelta(hours=9))
DATA_FILE = 'data.json'

# 1. 쿠팡 파트너스 HMAC 서명 생성 함수 (쿠팡 보안 요구사항)
def generate_coupang_signature(method, url, secret_key, access_key):
    path, _, query = url.partition('?')
    datetime_str = time.strftime('%y%m%dT%H%M%SZ', time.gmtime())
    message = datetime_str + method + path + (query if query else '')
    
    signature = hmac.new(
        bytes(secret_key, 'utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_str}, signature={signature}"

# 2. 쿠팡 파트너스 골드박스(특가) 상품 불러오기
def fetch_coupang_goldbox():
    access_key = os.environ.get('COUPANG_ACCESS_KEY')
    secret_key = os.environ.get('COUPANG_SECRET_KEY')
    
    if not access_key or not secret_key:
        print("⚠️ 쿠팡 API Key(Secrets)가 설정되지 않았습니다.")
        return []

    # 쿠팡 골드박스 API URL
    domain = "https://api-gateway.coupang.com"
    url_path = "/v2/providers/affiliate_open_api/apis/openapi/v1/products/goldbox"
    
    authorization = generate_coupang_signature("GET", url_path, secret_key, access_key)
    headers = {
        "Authorization": authorization,
        "Content-Type": "application/json;charset=UTF-8"
    }

    try:
        response = requests.get(domain + url_path, headers=headers, timeout=10)
        if response.status_code == 200:
            result = response.json()
            products = result.get('data', [])
            
            coupang_items = []
            for item in products:
                # 할인율 계산
                orig_price = item.get('originalPrice', 0)
                sale_price = item.get('productPrice', 0)
                discount_rate = ""
                if orig_price and orig_price > sale_price:
                    rate = round((1 - (sale_price / orig_price)) * 100)
                    discount_rate = f"{rate}%"

                coupang_items.append({
                    "id": f"coupang_{item.get('productId')}",
                    "source": "coupang",
                    "title": item.get('productName'),
                    "price": f"{sale_price:,}원",
                    "originalPrice": f"{orig_price:,}원" if orig_price else "",
                    "discountRate": discount_rate,
                    "imageUrl": item.get('productImage'),
                    "link": item.get('productUrl'), # 내 파트너스 ID가 들어간 수익 링크
                    "createdAt": datetime.now(KST).isoformat()
                })
            print(f"✅ 쿠팡 골드박스 상품 {len(coupang_items)}개 수집 완료!")
            return coupang_items
        else:
            print(f"❌ 쿠팡 API 호출 실패 (상태 코드: {response.status_code})")
            print(response.text)
            return []
    except Exception as e:
        print(f"❌ 쿠팡 API 수집 중 에러 발생: {e}")
        return []

# 3. 메인 실행 로직
if __name__ == '__main__':
    now = datetime.now(KST)
    
    # 기존 data.json 읽어오기
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            deals = json.load(f)
    except Exception:
        deals = []

    # 24시간이 지난 만료된 상품 자동 삭제
    valid_deals = []
    for deal in deals:
        created_at_str = deal.get('createdAt')
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str)
                if now - created_at < timedelta(hours=24):
                    valid_deals.append(deal)
            except ValueError:
                continue

    # 새로운 쿠팡 상품 수집
    new_coupang_deals = fetch_coupang_goldbox()

    # 중복 상품 제거 후 합치기 (동일한 링크가 없으면 추가)
    existing_links = {d['link'] for d in valid_deals}
    added_count = 0
    for item in new_coupang_deals:
        if item['link'] not in existing_links:
            valid_deals.insert(0, item) # 신규 핫딜을 가장 위에 추가
            added_count += 1

    # data.json 파일에 최종 저장
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(valid_deals, f, ensure_ascii=False, indent=2)

    print(f"🎉 총 {len(valid_deals)}개 핫딜 저장 완료! (신규 추가: {added_count}개)")
