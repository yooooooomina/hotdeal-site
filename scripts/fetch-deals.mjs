// =========================================================
// 쿠팡파트너스 오픈API로 가격을 주기적으로 수집해서
// "예전보다 확 싸진 상품"만 핫딜로 자동 등록하는 스크립트.
//
// 실행: node scripts/fetch-deals.mjs
// 필요한 환경변수:
//   COUPANG_ACCESS_KEY  (파트너스 대시보드에서 발급받은 Access Key)
//   COUPANG_SECRET_KEY  (파트너스 대시보드에서 발급받은 Secret Key)
//
// GitHub Actions에서는 이 값들을 절대 코드에 직접 쓰지 말고
// Settings > Secrets and variables > Actions 에 등록해서 사용하세요.
// =========================================================

import { createHmac } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";

const ACCESS_KEY = process.env.COUPANG_ACCESS_KEY;
const SECRET_KEY = process.env.COUPANG_SECRET_KEY;
const SUB_ID = process.env.COUPANG_SUB_ID || "hotdealsite"; // 파트너스 채널 구분용 (선택)

const DOMAIN = "https://api-gateway.coupang.com";
const SEARCH_PATH = "/v2/providers/affiliate_open_api/apis/openapi/products/search";

const DISCOUNT_THRESHOLD = 0.15;   // 15% 이상 떨어지면 "핫딜"로 판정
const HISTORY_KEEP = 10;           // 상품별로 최근 몇 개의 가격 기록을 남길지
const DEAL_EXPIRY_HOURS = 48;      // 이 시간이 지나면 핫딜 목록에서 자동 제외
const REQUEST_DELAY_MS = 700;      // 요청 사이 대기 시간 (API 과호출 방지)

const KEYWORDS_FILE = new URL("../data/keywords.json", import.meta.url);
const HISTORY_FILE = new URL("../data/price-history.json", import.meta.url);
const OUTPUT_FILE = new URL("../data/deals-coupang.json", import.meta.url);

function assertEnv() {
  if (!ACCESS_KEY || !SECRET_KEY) {
    console.error(
      "❌ COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY 환경변수가 없습니다.\n" +
      "   로컬 테스트라면: COUPANG_ACCESS_KEY=xxx COUPANG_SECRET_KEY=yyy node scripts/fetch-deals.mjs"
    );
    process.exit(1);
  }
}

// 쿠팡 공식 문서 기준 HMAC 서명 생성
function buildAuthHeader(method, pathWithQuery) {
  const [path, query = ""] = pathWithQuery.split("?");
  const now = new Date();
  const datetime =
    now
      .toISOString()
      .replace(/[-:]/g, "")
      .slice(2, 15) + "Z"; // yyMMddTHHmmssZ (UTC)

  const message = datetime + method + path + query;
  const signature = createHmac("sha256", SECRET_KEY)
    .update(message)
    .digest("hex");

  return `CEA algorithm=HmacSHA256, access-key=${ACCESS_KEY}, signed-date=${datetime}, signature=${signature}`;
}

async function searchProducts(keyword) {
  const query = `keyword=${encodeURIComponent(keyword)}&limit=20&subId=${encodeURIComponent(SUB_ID)}`;
  const pathWithQuery = `${SEARCH_PATH}?${query}`;
  const url = DOMAIN + pathWithQuery;

  const res = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: buildAuthHeader("GET", pathWithQuery),
      "Content-Type": "application/json",
    },
  });

  if (!res.ok) {
    console.error(`⚠️ [${keyword}] 요청 실패: ${res.status} ${res.statusText}`);
    return [];
  }

  const json = await res.json();
  return json?.data?.productData || [];
}

async function loadJSON(fileUrl, fallback) {
  try {
    const text = await readFile(fileUrl, "utf-8");
    return JSON.parse(text);
  } catch {
    return fallback;
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function main() {
  assertEnv();

  const { keywords = [] } = await loadJSON(KEYWORDS_FILE, { keywords: [] });
  const history = await loadJSON(HISTORY_FILE, {});
  const now = Date.now();

  console.log(`🔍 ${keywords.length}개 키워드 검색 시작...`);

  for (const keyword of keywords) {
    const products = await searchProducts(keyword);
    console.log(`  · "${keyword}" → ${products.length}건`);

    for (const p of products) {
      const id = String(p.productId);
      const entry = history[id] || {
        name: p.productName,
        image: p.productImage,
        url: p.productUrl,
        isRocket: !!p.isRocket,
        records: [],
      };

      entry.name = p.productName;
      entry.image = p.productImage;
      entry.url = p.productUrl;
      entry.records.push({ price: p.productPrice, at: now });
      entry.records = entry.records.slice(-HISTORY_KEEP);

      history[id] = entry;
    }

    await sleep(REQUEST_DELAY_MS);
  }

  await writeFile(HISTORY_FILE, JSON.stringify(history, null, 2), "utf-8");
  console.log(`💾 가격 기록 저장 완료 (${Object.keys(history).length}개 상품)`);

  // ---- 핫딜 판정 ----
  const deals = [];

  for (const [id, entry] of Object.entries(history)) {
    const records = entry.records;
    if (records.length < 2) continue; // 비교할 이전 기록이 없으면 패스

    const latest = records[records.length - 1];
    const isExpired = now - latest.at > DEAL_EXPIRY_HOURS * 3600 * 1000;
    if (isExpired) continue; // 최근에 관측 안 된 상품은 제외

    const priorMax = Math.max(...records.slice(0, -1).map((r) => r.price));
    if (priorMax <= 0) continue;

    const dropRatio = (priorMax - latest.price) / priorMax;
    if (dropRatio >= DISCOUNT_THRESHOLD) {
      deals.push({
        id,
        name: entry.name,
        price: latest.price,
        discount: Math.round(dropRatio * 100),
        source: "쿠팡",
        image: entry.image,
        link: entry.url,
        isRocket: entry.isRocket,
        postedAt: new Date(latest.at).toISOString(),
      });
    }
  }

  deals.sort((a, b) => b.discount - a.discount);

  await writeFile(OUTPUT_FILE, JSON.stringify(deals, null, 2), "utf-8");
  console.log(`🔥 핫딜 ${deals.length}건을 deals-coupang.json에 기록했습니다.`);
}

main().catch((err) => {
  console.error("스크립트 실행 중 오류:", err);
  process.exit(1);
});
