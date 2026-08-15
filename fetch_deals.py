import os
import json
import time
import hmac
import hashlib
import requests
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
DATA_FILE = 'data.json'

# ==========================================
# 1. 쿠팡 파트너스 자동 수집 (100% 무인 자동)
# ==========================================
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

def fetch_coupang_goldbox():
    access_key = os.environ.get('COUPANG_ACCESS_KEY')
    secret_key = os.environ.get('COUPANG_SECRET_KEY')
    
    if not access_key or not secret_key:
        print("⚠️ [쿠팡] API Key(Secrets)가 설정되지 않았습니다.")
        return []

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
                    "link": item.get('productUrl'), # 쿠팡 파트너스 수익 링크
                    "createdAt": datetime.now(KST).isoformat()
                })
            print(f"✅ [쿠팡] 골드박스 상품 {len(coupang_items)}개 수집 완료!")
            return coupang_items
        else:
            print(f"❌ [쿠팡] API 호출 실패 (코드: {response.status_code})")
            return []
    except Exception as e:
        print(f"❌ [쿠팡] 수집 에러: {e}")
        return []

# ==========================================
# 2. 토스 쉐어링크 Open API 우회 수집 (수익 100% 자동화)
# ==========================================
BASE_TOSS_URL = "https://sharelink-api.toss.im"

def make_toss_request(method, url, headers=None, json_data=None):
    """토스 API 차단 우회 요청 처리"""
    try:
        if method == "POST":
            return requests.post(url, headers=headers, json=json_data, timeout=10)
        else:
            return requests.get(url, headers=headers, timeout=10)
    except Exception as e:
        print(f"⚠️ 요청 예외: {e}")
        return None

def get_toss_access_token(access_key, secret_key):
    url = f"{BASE_TOSS_URL}/openapi/auth/token"
    payload = {"accessKey": access_key, "secretKey": secret_key}
    res = make_toss_request("POST", url, json_data=payload)
    
    if res and res.status_code == 200:
        data = res.json().get('data', {})
        token = data.get('accessToken') if isinstance(data, dict) else res.json().get('accessToken')
        if token:
            print("✅ [토스] Access Token 발급 성공!")
            return token
    print(f"❌ [토스] 토큰 발급 실패: {res.status_code if res else 'No Response'}")
    return None

def fetch_toss_deals():
    access_key = os.environ.get('TOSS_ACCESS_KEY')
    secret_key = os.environ.get('TOSS_SECRET_KEY')
    
    print("🔍 [토스] 수익 연동 수집 프로세스 시작...")
    if not access_key or not secret_key:
        print("⚠️ [토스] Secrets 키가 설정되지 않았습니다.")
        return []

    token = get_toss_access_token(access_key, secret_key)
    if not token:
        return []

    headers = {"Authorization": f"Bearer {token}"}
    toss_items = []

    # 특가 상품 목록 API 호출
    res = make_toss_request("GET", f"{BASE_TOSS_URL}/openapi/v1/products/daily-deals", headers=headers)
    if not res or res.status_code != 200:
        res = make_toss_request("GET", f"{BASE_TOSS_URL}/openapi/products/daily-deals", headers=headers)

    if res and res.status_code == 200:
        body = res.json()
        products = body.get('data') or body.get('products') or []
        print(f"✅ [토스] 상품 {len(products)}개 원본 데이터 확보!")

        for item in products:
            prod_id = item.get('id') or item.get('productId')
            if not prod_id:
                continue

            # 수익 추적용 shortUrl 발급 요청
            link_res = make_toss_request("POST", f"{BASE_TOSS_URL}/openapi/v1/links", headers=headers, json_data={"productId": str(prod_id)})
            if not link_res or link_res.status_code != 200:
                link_res = make_toss_request("POST", f"{BASE_TOSS_URL}/openapi/links", headers=headers, json_data={"productId": str(prod_id)})

            short_url = None
            if link_res and link_res.status_code == 200:
                l_data = link_res.json().get('data', {})
                short_url = l_data.get('shortUrl') if isinstance(l_data, dict) else link_res.json().get('shortUrl')

            # 수익 주소 확보 실패시 기본 주소 백업
            final_link = short_url or item.get('linkUrl') or f"https://toss.im/shopping/product/{prod_id}"

            orig_price = item.get('originalPrice', 0)
            sale_price = item.get('price') or item.get('productPrice') or 0
            discount_rate = f"{item.get('discountRate')}%" if item.get('discountRate') else ""

            toss_items.append({
                "id": f"toss_{prod_id}",
                "source": "toss",
                "title": item.get('name') or item.get('title') or item.get('productName'),
                "price": f"{sale_price:,}원" if isinstance(sale_price, int) and sale_price > 0 else str(sale_price),
                "originalPrice": f"{orig_price:,}원" if isinstance(orig_price, int) and orig_price > 0 else "",
                "discountRate": discount_rate,
                "imageUrl": item.get('imageUrl') or item.get('thumbnail') or item.get('productImage'),
                "link": final_link, # ★ 수익 정산 전용 shortUrl!
                "createdAt": datetime.now(KST).isoformat()
            })

        print(f"✅ [토스] 최종 {len(toss_items)}개 수익형 핫딜 처리 완료!")
        return toss_items
    else:
        print(f"❌ [토스] 상품 목록 조회 실패")
        return []

# ==========================================
# 3. 메인 실행 및 24시간 만료 관리
# ==========================================
if __name__ == '__main__':
    now = datetime.now(KST)
    
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            deals = json.load(f)
    except Exception:
        deals = []

    # 24시간 지난 만료 상품 삭제
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

    # 쿠팡 + 토스 신규 수집
    new_coupang = fetch_coupang_goldbox()
    new_toss = fetch_toss_deals()
    all_new = new_coupang + new_toss

    existing_links = {d['link'] for d in valid_deals}
    added_count = 0
    for item in all_new:
        if item['link'] not in existing_links:
            valid_deals.insert(0, item)
            added_count += 1

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(valid_deals, f, ensure_ascii=False, indent=2)

    print(f"🎉 총 {len(valid_deals)}개 핫딜 저장 완료! (신규 추가: {added_count}개)")
