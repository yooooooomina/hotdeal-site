import os
import json
import time
import hmac
import hashlib
import requests
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
DATA_FILE = 'data.json'

def clean_price(price):
    """소수점 .0 제거 및 원화 포맷팅"""
    if price is None or price == "":
        return ""
    price_str = str(price).strip().replace('.0원', '원').replace('.00원', '원')
    if '.0' in price_str and '원' not in price_str:
        try:
            price_str = str(int(float(price_str)))
        except ValueError:
            price_str = price_str.replace('.0', '')
    if price_str.isdigit():
        return f"{int(price_str):,}원"
    return price_str

# ==========================================
# 1. 쿠팡 파트너스 수집 (할인율 정확히 계산)
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
                orig_price_raw = item.get('originalPrice', 0) or 0
                sale_price_raw = item.get('productPrice', 0) or 0
                
                # 🔴 할인율 자동 수학 계산 (원가 > 할인가 일 경우)
                discount_rate = ""
                try:
                    orig_val = float(orig_price_raw)
                    sale_val = float(sale_price_raw)
                    if orig_val > sale_val and orig_val > 0:
                        rate = round((1 - (sale_val / orig_val)) * 100)
                        if rate > 0:
                            discount_rate = f"▼{rate}%"
                except Exception:
                    pass

                # API에서 기본 제공하는 할인율 정보가 있으면 대체
                if not discount_rate and item.get('discountRate'):
                    discount_rate = f"▼{item.get('discountRate')}%"

                coupang_items.append({
                    "id": f"coupang_{item.get('productId')}",
                    "source": "coupang",
                    "title": item.get('productName'),
                    "price": clean_price(sale_price_raw),
                    "originalPrice": clean_price(orig_price_raw) if orig_price_raw else "",
                    "discountRate": discount_rate, # 저장할 할인율
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
# 2. 토스쇼핑 Open API 수집
# ==========================================
BASE_TOSS_URL = "https://sharelink-api.toss.im"

def fetch_toss_deals():
    access_key = os.environ.get('TOSS_ACCESS_KEY')
    secret_key = os.environ.get('TOSS_SECRET_KEY')
    
    if not access_key or not secret_key:
        return []

    token = None
    try:
        auth_url = f"{BASE_TOSS_URL}/openapi/auth/token"
        res = requests.post(auth_url, json={"accessKey": access_key, "secretKey": secret_key}, timeout=10)
        if res.status_code == 200:
            res_json = res.json()
            data = res_json.get('data') or {}
            token = data.get('accessToken') if isinstance(data, dict) else res_json.get('accessToken')
    except Exception:
        return []

    if not token:
        return []

    headers = {"Authorization": f"Bearer {token}"}
    toss_items = []

    target_endpoints = [
        "/openapi/v1/products/daily-deals",
        "/openapi/products/daily-deals",
        "/openapi/v1/products",
        "/openapi/products"
    ]

    products = []
    for ep in target_endpoints:
        try:
            r = requests.get(f"{BASE_TOSS_URL}{ep}", headers=headers, timeout=10)
            if r.status_code == 200:
                body = r.json()
                items = body.get('data') or body.get('products') or []
                if isinstance(items, list) and len(items) > 0:
                    products = items
                    break
        except Exception:
            continue

    for item in products:
        prod_id = item.get('id') or item.get('productId')
        if not prod_id:
            continue

        short_url = None
        try:
            link_res = requests.post(
                f"{BASE_TOSS_URL}/openapi/v1/links",
                headers=headers,
                json={"productId": str(prod_id)},
                timeout=5
            )
            if link_res.status_code == 200:
                l_body = link_res.json()
                l_data = l_body.get('data') or {}
                short_url = l_data.get('shortUrl') if isinstance(l_data, dict) else l_body.get('shortUrl')
        except Exception:
            pass

        final_link = short_url or item.get('linkUrl') or f"https://toss.im/shopping/product/{prod_id}"
        orig_price_raw = item.get('originalPrice', 0)
        sale_price_raw = item.get('price') or item.get('productPrice') or 0
        
        discount_rate = ""
        if item.get('discountRate'):
            discount_rate = f"▼{item.get('discountRate')}%"

        toss_items.append({
            "id": f"toss_{prod_id}",
            "source": "toss",
            "title": item.get('name') or item.get('title') or item.get('productName'),
            "price": clean_price(sale_price_raw),
            "originalPrice": clean_price(orig_price_raw) if orig_price_raw else "",
            "discountRate": discount_rate,
            "imageUrl": item.get('imageUrl') or item.get('thumbnail') or item.get('productImage'),
            "link": final_link,
            "createdAt": datetime.now(KST).isoformat()
        })

    return toss_items

# ==========================================
# 3. 메인 실행 및 데이터 세척
# ==========================================
if __name__ == '__main__':
    now = datetime.now(KST)
    
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            deals = json.load(f)
    except Exception:
        deals = []

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
