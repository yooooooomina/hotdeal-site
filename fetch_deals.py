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
# 2. 토스쇼핑 웹 크롤링 자동 수집 (Playwright 정밀 탐색)
# ==========================================
def fetch_toss_deals():
    toss_items = []
    print("🔍 [토스] 브라우저 자동 수집 시작...")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                viewport={"width": 390, "height": 844}
            )
            page = context.new_page()
            
            # 토스쇼핑 접속 및 스크롤
            page.goto("https://toss.im/shopping", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000) # 4초 대기
            
            # 화면 아래로 조금 스크롤하여 더 많은 상품 로딩
            page.evaluate("window.scrollBy(0, 800)")
            page.wait_for_timeout(2000)

            # 모든 링크 요소 가져오기
            links = page.query_selector_all('a')
            
            seen_titles = set()
            for idx, link_elem in enumerate(links):
                try:
                    href = link_elem.get_attribute('href') or ''
                    text = link_elem.inner_text().strip()
                    
                    if not text or len(text) < 3:
                        continue
                        
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    
                    # 텍스트에 '원' 또는 숫자가 포함된 쇼핑 항목 추출
                    has_price = any('원' in line or line.replace(',', '').isdigit() for line in lines)
                    
                    if has_price and len(lines) >= 2:
                        title = lines[0]
                        
                        # 가격 문구 찾기
                        price = "특가"
                        for line in lines[1:]:
                            if '원' in line:
                                price = line
                                break

                        if title in seen_titles or len(title) < 2:
                            continue
                        seen_titles.add(title)

                        # 이미지 찾기
                        img_elem = link_elem.query_selector('img')
                        img_url = img_elem.get_attribute('src') if img_elem else "https://via.placeholder.com/150"
                        
                        final_link = href if href.startswith('http') else f"https://toss.im{href}"

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
                
                if len(toss_items) >= 15:
                    break
                    
            browser.close()
            print(f"✅ [토스] 총 {len(toss_items)}개 특가 수집 완료!")
            return toss_items

    except Exception as e:
        print(f"⚠️ [토스] 크롤링 수집 예외 발생: {e}")
        return []

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
