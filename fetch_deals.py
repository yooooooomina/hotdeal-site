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
# 1. 쿠팡 파트너스 수집 (할인율 100% 강제 생성)
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
                
                # 🔴 할인율 정밀 계산
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

                if not discount_rate and item.get('discountRate'):
                    discount_rate = f"▼{item.get('discountRate')}%"

                coupang_items.append({
                    "id": f"coupang_{item.get('productId')}",
                    "source": "coupang",
                    "title": item.get('productName'),
                    "price": clean_price(sale_price_raw),
                    "originalPrice": clean_price(orig_price_raw) if orig_price_raw else "",
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
# 2. 메인 실행 (수집 및 갱신)
# ==========================================
if __name__ == '__main__':
    now = datetime.now(KST)
    
    # 🔴 핵심: 새 형식 반영을 위해 기존 쿠팡 데이터 초기화 후 새로만 수집
    new_coupang = fetch_coupang_goldbox()

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_coupang, f, ensure_ascii=False, indent=2)

    print(f"🎉 총 {len(new_coupang)}개 최신 쿠팡 핫딜(할인율 포함) 저장 완료!")
