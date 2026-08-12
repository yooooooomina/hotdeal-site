// =========================================================
// 핫딜 줍줍 — 데이터 + 렌더링 로직 (자동화 연동 버전)
//
// - 쿠팡 핫딜: data/deals-coupang.json (GitHub Actions가 자동 갱신)
// - 토스 핫딜: data/deals-toss.json   (사람이 직접 편집)
// - EXPIRY_HOURS 가 지난 핫딜은 화면에서 자동으로 사라집니다.
//
// ⚠️ 로컬에서 index.html을 더블클릭해서 열면(file:// 방식) fetch가
//    브라우저 보안정책(CORS)에 막혀 동작하지 않습니다.
//    로컬 테스트 시에는 터미널에서 `python3 -m http.server` 실행 후
//    http://localhost:8000 으로 접속하거나, GitHub Pages에 올려서 확인하세요.
// =========================================================

const EXPIRY_HOURS = 48;
const DATA_FILES = {
  쿠팡: "data/deals-coupang.json",
  토스쇼핑: "data/deals-toss.json",
  토스BEST50: "data/deals-toss.json",
};

let deals = []; // 정규화된 형태로 저장: { id, name, price, discount, source, icon/image, link, postedAt(Date) }
let currentTab = "쿠팡";

async function init() {
  bindTabs();
  bindAlertButton();
  bindSimulateButton();

  await loadAllDeals();
  render();
  buildTicker();

  setInterval(() => render(), 60 * 1000);          // 1분마다 "n시간 전" 갱신 + 만료 체크
  setInterval(loadAllDeals, 10 * 60 * 1000);        // 10분마다 데이터 새로 불러오기 (자동 갱신 체감)
}

async function loadAllDeals() {
  const uniqueFiles = [...new Set(Object.values(DATA_FILES))];
  const results = await Promise.all(
    uniqueFiles.map((file) =>
      fetch(file, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : []))
        .catch(() => [])
    )
  );

  const raw = results.flat();
  deals = raw
    .filter((d) => d && d.name && !d._설명 && !d._예시) // 예시/설명용 항목 제외
    .map(normalizeDeal)
    .filter(Boolean);

  render();
  buildTicker();
}

function normalizeDeal(d) {
  const postedAt = d.postedAt ? new Date(d.postedAt) : new Date();
  if (isNaN(postedAt.getTime())) return null;

  return {
    id: d.id || `${d.name}-${postedAt.getTime()}`,
    name: d.name,
    price: Number(d.price) || 0,
    discount: Number(d.discount) || 0,
    source: d.source || "쿠팡",
    icon: d.icon || (d.source === "쿠팡" ? "🛒" : "🧾"),
    image: d.image || null,
    link: d.link || d.url || "#",
    postedAt,
  };
}

function bindTabs() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-selected", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      currentTab = btn.dataset.source;
      render();
    });
  });
}

function bindAlertButton() {
  document.getElementById("alertBtn").addEventListener("click", () => {
    showToast("🔔 실시간 핫딜 알림을 신청했어요!");
  });
}

function bindSimulateButton() {
  const btn = document.getElementById("simulateBtn");
  if (!btn) return;
  btn.textContent = "↻ 지금 새로고침";
  btn.addEventListener("click", () => {
    loadAllDeals();
    showToast("🔄 최신 핫딜을 다시 불러왔어요");
  });
}

function isExpired(deal) {
  const hoursAgo = (Date.now() - deal.postedAt.getTime()) / 3600000;
  return hoursAgo > EXPIRY_HOURS;
}

function hoursAgoLabel(date) {
  const diffMs = Date.now() - date.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "방금 전";
  if (mins < 60) return `${mins}분 전`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}시간 전`;
  const days = Math.floor(hours / 24);
  return `${days}일 전`;
}

function formatWon(n) {
  return n.toLocaleString("ko-KR") + "원";
}

function render() {
  const live = deals.filter((d) => !isExpired(d));
  live.sort((a, b) => b.postedAt - a.postedAt);

  const grid = document.getElementById("dealGrid");
  const empty = document.getElementById("emptyState");
  const visible = live.filter((d) => d.source === currentTab);

  grid.innerHTML = "";

  if (visible.length === 0) {
    empty.hidden = false;
  } else {
    empty.hidden = true;
    visible.forEach((deal) => grid.appendChild(buildCard(deal)));
  }

  document.getElementById("statusText").textContent =
    `실시간으로 업데이트 중 · 살아있는 핫딜 ${live.length}건 · 지난 핫딜은 자동으로 사라져요`;
}

function buildCard(deal) {
  const origPrice = deal.discount > 0
    ? Math.round(deal.price / (1 - deal.discount / 100))
    : deal.price;

  const card = document.createElement("article");
  card.className = "deal-card";
  card.dataset.id = deal.id;

  const thumbInner = deal.image
    ? `<img src="${escapeAttr(deal.image)}" alt="" style="max-width:100%;max-height:100%;object-fit:contain;" loading="lazy">`
    : deal.icon;

  card.innerHTML = `
    <a href="${escapeAttr(deal.link)}" target="_blank" rel="noopener sponsored nofollow" style="text-decoration:none;color:inherit;display:block;">
      <span class="source-flag src-${deal.source}">${deal.source}</span>
      <div class="deal-thumb">${thumbInner}</div>
      <div class="deal-body">
        <p class="deal-name">${escapeHTML(deal.name)}</p>
        <div class="price-row">
          <span class="price-orig">${formatWon(origPrice)}</span>
          <span class="discount">▼${deal.discount}%</span>
        </div>
        <div class="price-row">
          <span class="price-now">${formatWon(deal.price)}</span>
        </div>
        <div class="meta-row">
          <span>${deal.source}</span>
          <span>${hoursAgoLabel(deal.postedAt)}</span>
        </div>
      </div>
      <div class="card-barcode" aria-hidden="true"></div>
    </a>
  `;
  return card;
}

function escapeHTML(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function escapeAttr(str) {
  return String(str).replace(/"/g, "&quot;");
}

let toastTimer = null;
function showToast(msg) {
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
}

function buildTicker() {
  const items = deals
    .slice(0, 8)
    .map((d) => `🔥 ${d.name} ${formatWon(d.price)} (▼${d.discount}%)`)
    .join("     ·     ");
  const track = document.getElementById("tickerTrack");
  if (track) track.textContent = items ? items + "     ·     " + items : "🔥 핫딜 데이터를 불러오는 중...";
}

document.addEventListener("DOMContentLoaded", init);
