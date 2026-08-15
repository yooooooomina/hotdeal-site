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
# 1. 쿠팡 파트너스 수집 로직
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
        print("⚠️ [쿠팡] API Key가 설정되지 않았습니다.")
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
                    "link": item.get('productUrl'),
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
# 2. 토스쇼핑 쉐어링크 Open API 수집 로직
# ==========================================
BASE_TOSS_URL = "https://sharelink-api.toss.im"

def get_toss_access_token(access_key, secret_key):
    try:
        url = f"{BASE_TOSS_URL}/openapi/auth/token"
        payload = {
            "accessKey": access_key,
            "secretKey": secret_key
        }
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            res_data = res.json()
            token = res_data.get('data', {}).get('accessToken') if isinstance(res_data.get('data'), dict) else res_data.get('accessToken')
            print("✅ [토스] Access Token 발급 성공!")
            return token
        else:
            print(f"❌ [토스] 토큰 발급 실패 (코드: {res.status_code}): {res.text}")
            return None
    except Exception as e:
        print(f"❌ [토스] 토큰 예외: {e}")
        return None

def fetch_toss_deals():
    access_key = os.environ.get('TOSS_ACCESS_KEY')
    secret_key = os.environ.get('TOSS_SECRET_KEY')
    
    print("🔍 [토스] 수집 시작...")
    if not access_key or not secret_key:
        print("⚠️ [토스] Secrets 키가 설정되지 않았습니다.")
        return []

    token = get_toss_access_token(access_key, secret_key)
    if not token:
        return []

    headers = {"Authorization": f"Bearer {token}"}
    toss_items = []

    # 엔드포인트 목록 탐색 (하루특가 / 베스트)
    endpoints = [
        "/openapi/v1/products/daily-deals",
        "/openapi/products/daily-deals",
        "/openapi/v1/products",
        "/openapi/products"
    ]

    products = []
    for ep in endpoints:
        try:
            res = requests.get(f"{BASE_TOSS_URL}{ep}", headers=headers, timeout=5)
            if res.status_code == 200:
                body = res.json()
                data = body.get('data') or body.get('products') or []
                if isinstance(data, list) and len(data) > 0:
                    products = data
                    print(f"✅ [토스] {ep} 에서 상품 {len(products)}개 조회 성공!")
                    break
            else:
                print(f"ℹ️ [토스] 엔드포인트 {ep} 상태코드: {res.status_code}")
        except Exception:
            continue

    if not products:
        print("⚠️ [토스] 오픈 API로 가져온 상품이 0개입니다.")
        return []

    for item in products:
        prod_id = item.get('id') or item.get('productId')
        if not prod_id:
            continue

        # 쉐어링크(shortUrl) 생성 시도
        short_url = None
        try:
            link_res = requests.post(
                f"{BASE_TOSS_URL}/openapi/v1/links", 
                headers=headers, 
                json={"productId": str(prod_id)}, 
                timeout=5
            )
            if link_res.status_code != 200:
                link_res = requests.post(
                    f"{BASE_TOSS_URL}/openapi/links", 
                    headers=headers, 
                    json={"productId": str(prod_id)}, 
                    timeout=5
                )
            if link_res.status_code == 200:
                l_data = link_res.json()
                short_url = l_data.get('data', {}).get('shortUrl') if isinstance(l_data.get('data'), dict) else l_data.get('shortUrl')
        except Exception:
            pass

        final_link = short_url or item.get('linkUrl') or item.get('url') or f"https://toss.im/shopping/product/{prod_id}"
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
            "link": final_link,
            "createdAt": datetime.now(KST).isoformat()
        })

    print(f"✅ [토스] 최종 {len(toss_items)}개 상품 수집 완료!")
    return toss_items

# ==========================================
# 3. 메인 실행
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

    # 쿠팡 + 토스 신규 수집 실행
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
