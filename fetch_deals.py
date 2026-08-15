import os
import json
import time
import hmac
import hashlib
import requests
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

KST = timezone(timedelta(hours=9))
DATA_FILE = 'data.json'

# ==========================================
# 1. 쿠팡 파트너스 자동 수집 로직
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
# 2. 토스쇼핑 웹 크롤링 자동 수집 (Playwright)
# ==========================================
def fetch_toss_deals():
    toss_items = []
    print("🔍 [토스] 브라우저 자동 수집 시작...")
    
    try:
        with sync_playwright() as p:
            # 가상 브라우저 실행 (Chrome 모드)
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            # 토스쇼핑 접속 및 데이터 로딩 대기
            page.goto("https://toss.im/shopping", wait_until="networkidle", timeout=20000)
            page.wait_for_timeout(3000) # 자바스크립트 렌더링 3초 대기
            
            # 상품 요소 추출
            cards = page.query_selector_all('a[href*="/shopping/"], div[class*="ProductCard"], div[class*="product"]')
            
            seen_titles = set()
            for idx, card in enumerate(cards):
                try:
                    text_content = card.inner_text()
                    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
                    
                    # 상품 제목, 가격 추출
                    if len(lines) >= 2:
                        title = lines[0]
                        price = lines[1] if '원' in lines[1] or '할인' in lines[0] else (lines[2] if len(lines) > 2 else lines[1])
                        
                        if title in seen_titles or len(title) < 2:
                            continue
                        seen_titles.add(title)

                        # 이미지 및 링크 추출
                        img_elem = card.query_selector('img')
                        img_url = img_elem.get_attribute('src') if img_elem else "https://via.placeholder.com/150"
                        
                        link_attr = card.get_attribute('href')
                        final_link = f"https://toss.im{link_attr}" if link_attr and link_attr.startswith('/') else (link_attr or "https://toss.im/shopping")

                        toss_items.append({
                            "id": f"toss_{idx}_{int(time.time())}",
                            "source": "toss",
                            "title": title,
                            "price": price,
                            "originalPrice": "",
                            "discountRate": "특가",
                            "imageUrl": img_url,
                            "link": final_link,
                            "createdAt": datetime.now(KST).isoformat()
                        })
                except Exception:
                    continue
                
                if len(toss_items) >= 15: # 최대 15개 수집
                    break
                    
            browser.close()
            print(f"✅ [토스] 총 {len(toss_items)}개 특가 수집 완료!")
            return toss_items

    except Exception as e:
        print(f"⚠️ [토스] 크롤링 수집 예외 발생: {e}")
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

    # 24시간 지난 만료 상품 자동 삭제
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
