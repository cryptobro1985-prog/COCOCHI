const tg = window.Telegram?.WebApp;
if (tg) {
  try {
    tg.ready();
    tg.expand();
    tg.setHeaderColor("#100821");
    tg.setBackgroundColor("#100821");
  } catch (_) {}
}

const I18N = {
  ru: {
    wallet:"Кошелёк", myChicken:"МОЯ COCOCHI", level:"УР.", happy:"Счастливая",
    readyToCollect:"ГОТОВО К СБОРУ", perHour:"яиц/час", collect:"Собрать яйца",
    food:"Еда", water:"Вода", clean:"Чистота", feed:"Покормить", giveWater:"Напоить",
    cleanBtn:"Почистить", upgrade:"АПГРЕЙД КУРЫ", nextLevel:"Следующий уровень",
    upgradeText:"Больше яиц в час и новый внешний вид", upgradeBtn:"Улучшить",
    market:"РЫНОК", eggMarket:"Egg Market", demoPrice:"DEMO PRICE", yourEggs:"Твои яйца",
    buyLimit:"Лимит покупки", sellLimit:"Лимит продажи", day:"день", buyEggs:"Купить яйца",
    sellEggs:"Продать яйца", demoOnly:"Сейчас это DEMO",
    demoOnlyText:"Кнопки рынка работают как симуляция. Реальные переводы TON в MVP отключены.",
    friends:"ДРУЗЬЯ", inviteTitle:"Позови друга — обе куры несутся лучше",
    inviteText:"Когда друг впервые запускает COCOCHI по твоей ссылке, тебе открывается дневной буст в демо-режиме.",
    inviteFriend:"Позвать друга", yourLink:"Твоя ссылка", profile:"ПРОФИЛЬ",
    connectWallet:"Подключить TON-кошелёк",
    connectWalletText:"Подключение не даёт приложению доступ к seed-фразе или приватному ключу.",
    language:"Язык", resetDemo:"Сбросить DEMO", home:"Кура", marketShort:"Рынок",
    friendsShort:"Друзья", profileShort:"Профиль",
    collected:"Яйца собраны", notEnough:"Не хватает яиц", cared:"Люся довольна ❤️",
    upgraded:"Кура улучшена!", demoBuy:"DEMO-покупка", demoSell:"DEMO-продажа",
    confirmDemo:"Подтвердить DEMO", cancel:"Отмена", resetDone:"DEMO сброшено"
  },
  en: {
    wallet:"Wallet", myChicken:"MY COCOCHI", level:"LV.", happy:"Happy",
    readyToCollect:"READY TO COLLECT", perHour:"eggs/hour", collect:"Collect eggs",
    food:"Food", water:"Water", clean:"Clean", feed:"Feed", giveWater:"Give water",
    cleanBtn:"Clean", upgrade:"CHICKEN UPGRADE", nextLevel:"Next level",
    upgradeText:"More eggs per hour and a fresh look", upgradeBtn:"Upgrade",
    market:"MARKET", eggMarket:"Egg Market", demoPrice:"DEMO PRICE", yourEggs:"Your eggs",
    buyLimit:"Buy limit", sellLimit:"Sell limit", day:"day", buyEggs:"Buy eggs",
    sellEggs:"Sell eggs", demoOnly:"DEMO mode",
    demoOnlyText:"Market buttons run a simulation. Real TON transfers are disabled in this MVP.",
    friends:"FRIENDS", inviteTitle:"Invite a friend — both chickens lay better",
    inviteText:"When a friend first launches COCOCHI from your link, you unlock a daily demo boost.",
    inviteFriend:"Invite friend", yourLink:"Your link", profile:"PROFILE",
    connectWallet:"Connect TON wallet",
    connectWalletText:"Connecting never gives the app access to your seed phrase or private key.",
    language:"Language", resetDemo:"Reset DEMO", home:"COCOCHI", marketShort:"Market",
    friendsShort:"Friends", profileShort:"Profile",
    collected:"Eggs collected", notEnough:"Not enough eggs", cared:"Lucy is happy ❤️",
    upgraded:"Chicken upgraded!", demoBuy:"DEMO buy", demoSell:"DEMO sell",
    confirmDemo:"Confirm DEMO", cancel:"Cancel", resetDone:"DEMO reset"
  }
};

const defaultState = () => ({
  lang: localStorage.getItem("cocochi.lang") || "",
  level: 1,
  eggs: 125,
  pending: 12.4,
  food: 78,
  water: 64,
  clean: 82,
  lastTick: Date.now(),
  dailyBuyUsed: 60,
  dailySellUsed: 4,
  demoTon: 1.25
});

let state;
try {
  state = {...defaultState(), ...(JSON.parse(localStorage.getItem("cocochi.state.v1") || "{}"))};
} catch (_) {
  state = defaultState();
}
state.lastTick = Number(state.lastTick || Date.now());

let config = { botUsername:"", marketMode:"demo" };
let session = { demo:true, user:null };
let marketMode = "buy";
let toastTimer;

const $ = (id) => document.getElementById(id);
const clamp = (n,min,max) => Math.max(min,Math.min(max,n));
const upgradeCost = () => Math.round(100 * Math.pow(1.52, state.level - 1));
const baseRate = () => 4.2 * Math.pow(1.12, state.level - 1);

function careMultiplier() {
  const minCore = Math.min(state.food, state.water);
  let core = minCore > 75 ? 1 : minCore > 50 ? .75 : minCore > 25 ? .5 : minCore > 0 ? .25 : 0;
  const cleanliness = state.clean > 50 ? 1 : state.clean > 25 ? .9 : state.clean > 0 ? .75 : 0;
  return core * cleanliness;
}

function liveRate() {
  return baseRate() * careMultiplier();
}

function tick() {
  const now = Date.now();
  const elapsedHours = clamp((now - state.lastTick) / 3600000, 0, 6);
  if (elapsedHours > 0) {
    state.pending += liveRate() * elapsedHours;
    state.food = clamp(state.food - elapsedHours * 1.5, 0, 100);
    state.water = clamp(state.water - elapsedHours * 2.2, 0, 100);
    state.clean = clamp(state.clean - elapsedHours * .7, 0, 100);
  }
  state.lastTick = now;
  persist();
  render();
}

function persist() {
  localStorage.setItem("cocochi.state.v1", JSON.stringify(state));
  if (state.lang) localStorage.setItem("cocochi.lang", state.lang);
}

function tr(key) {
  return I18N[state.lang || "ru"][key] || key;
}

function translate() {
  document.documentElement.lang = state.lang || "ru";
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.dataset.i18n;
    el.textContent = tr(key);
  });
  $("confirmMarketBtn").textContent = tr("confirmDemo");
  $("closeActionBtn").textContent = tr("cancel");
  $("langValue").textContent = (state.lang || "ru").toUpperCase();
}

function render() {
  translate();
  $("levelValue").textContent = state.level;
  $("pendingEggs").textContent = state.pending.toFixed(1);
  $("rateValue").textContent = liveRate().toFixed(1);
  $("foodValue").textContent = `${Math.round(state.food)}%`;
  $("waterValue").textContent = `${Math.round(state.water)}%`;
  $("cleanValue").textContent = `${Math.round(state.clean)}%`;
  $("foodBar").style.width = `${state.food}%`;
  $("waterBar").style.width = `${state.water}%`;
  $("cleanBar").style.width = `${state.clean}%`;
  $("upgradeCost").textContent = upgradeCost();
  $("marketEggs").textContent = Math.floor(state.eggs);

  const mood = liveRate() <= 0 ? "💤" : careMultiplier() < .6 ? "🥺" : "❤️";
  $("moodBubble").firstChild.textContent = mood + " ";
}

function showToast(text) {
  clearTimeout(toastTimer);
  $("toast").textContent = text;
  $("toast").classList.add("show");
  toastTimer = setTimeout(() => $("toast").classList.remove("show"), 1800);
  try { tg?.HapticFeedback?.notificationOccurred("success"); } catch (_) {}
}

function spend(cost) {
  if (state.eggs < cost) {
    showToast(tr("notEnough"));
    try { tg?.HapticFeedback?.notificationOccurred("error"); } catch (_) {}
    return false;
  }
  state.eggs -= cost;
  return true;
}

document.querySelectorAll(".nav-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-btn").forEach(x => x.classList.toggle("active", x === btn));
    document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
    $(`screen-${btn.dataset.screen}`).classList.add("active");
    try { tg?.HapticFeedback?.impactOccurred("light"); } catch (_) {}
  });
});

$("collectBtn").addEventListener("click", () => {
  tick();
  state.eggs += state.pending;
  state.pending = 0;
  persist(); render(); showToast(tr("collected"));
});

document.querySelectorAll(".action-care").forEach(btn => {
  btn.addEventListener("click", () => {
    const care = btn.dataset.care;
    const costs = {food:15, water:10, clean:8};
    if (!spend(costs[care])) return;
    state[care] = 100;
    persist(); render(); showToast(tr("cared"));
  });
});

$("upgradeBtn").addEventListener("click", () => {
  const cost = upgradeCost();
  if (!spend(cost)) return;
  state.level += 1;
  persist(); render(); showToast(tr("upgraded"));
});

function openMarket(mode) {
  marketMode = mode;
  const isBuy = mode === "buy";
  $("actionTitle").textContent = isBuy ? tr("demoBuy") : tr("demoSell");
  $("actionText").textContent = isBuy
    ? "1 🥚 = 0.0010 TON · demo balance only"
    : "1 🥚 = 0.0010 TON · demo balance only";
  $("marketAmount").value = 10;
  updateMarketSummary();
  $("actionModal").classList.add("open");
}

function updateMarketSummary() {
  const amount = clamp(parseInt($("marketAmount").value || "1",10),1,100);
  $("marketAmount").value = amount;
  const ton = amount * .001;
  $("actionSummary").textContent = marketMode === "buy"
    ? `${amount} 🥚  ←  ${ton.toFixed(4)} DEMO TON`
    : `${amount} 🥚  →  ${ton.toFixed(4)} DEMO TON`;
}

$("buyEggsBtn").addEventListener("click", () => openMarket("buy"));
$("sellEggsBtn").addEventListener("click", () => openMarket("sell"));
$("marketAmount").addEventListener("input", updateMarketSummary);
$("closeActionBtn").addEventListener("click", () => $("actionModal").classList.remove("open"));

$("confirmMarketBtn").addEventListener("click", () => {
  const amount = clamp(parseInt($("marketAmount").value || "1",10),1,100);
  const ton = amount * .001;
  if (marketMode === "buy") {
    const remaining = 200 - state.dailyBuyUsed;
    if (amount > remaining) return showToast(`Buy limit: ${remaining} 🥚`);
    if (state.demoTon < ton) return showToast("Not enough DEMO TON");
    state.demoTon -= ton;
    state.eggs += amount;
    state.dailyBuyUsed += amount;
  } else {
    const remaining = 25 - state.dailySellUsed;
    if (amount > remaining) return showToast(`Sell limit: ${remaining} 🥚`);
    if (!spend(amount)) return;
    state.demoTon += ton;
    state.dailySellUsed += amount;
  }
  persist(); render();
  $("actionModal").classList.remove("open");
  showToast("DEMO ✓");
});

function buildRefLink() {
  const uid = session?.user?.id;
  if (!config.botUsername || !uid) return "";
  return `https://t.me/${config.botUsername}?start=ref_${uid}`;
}

$("shareBtn").addEventListener("click", () => {
  const link = buildRefLink();
  if (!link) return showToast(state.lang === "en" ? "Open COCOCHI inside Telegram first" : "Сначала открой COCOCHI внутри Telegram");
  const text = state.lang === "en"
    ? "Get your COCOCHI 🐔"
    : "Заводи свою COCOCHI 🐔";
  const share = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`;
  try {
    tg?.openTelegramLink ? tg.openTelegramLink(share) : window.open(share, "_blank");
  } catch (_) {
    window.open(share, "_blank");
  }
});

$("walletQuick").addEventListener("click", () => {
  document.querySelector('.nav-btn[data-screen="profile"]').click();
  setTimeout(() => $("ton-connect").scrollIntoView({behavior:"smooth", block:"center"}), 120);
});

$("langBtn").addEventListener("click", () => $("languageModal").classList.add("open"));
document.querySelectorAll(".language-choice").forEach(btn => {
  btn.addEventListener("click", () => {
    state.lang = btn.dataset.lang;
    persist(); render();
    $("languageModal").classList.remove("open");
  });
});

$("resetBtn").addEventListener("click", () => {
  const lang = state.lang || "ru";
  state = {...defaultState(), lang};
  persist(); render(); showToast(tr("resetDone"));
});

async function loadSession() {
  try {
    const [cfgRes, sessRes] = await Promise.all([
      fetch("/api/config"),
      fetch("/api/session", {
        method:"POST",
        headers:{"content-type":"application/json"},
        body:JSON.stringify({initData: tg?.initData || ""})
      })
    ]);
    config = await cfgRes.json();
    session = await sessRes.json();

    const u = session.user;
    if (u) {
      const name = [u.first_name, u.last_name].filter(Boolean).join(" ");
      $("userLabel").textContent = `@${u.username || u.id}`;
      $("profileName").textContent = name || u.username || `#${u.id}`;
      $("profileId").textContent = `Telegram ID ${u.id}`;
      $("refLink").textContent = buildRefLink() || "—";
    } else {
      $("refLink").textContent = state.lang === "en" ? "Open in Telegram to get a referral link" : "Открой в Telegram, чтобы получить ссылку";
    }
  } catch (_) {}
}

async function initTonConnect() {
  try {
    const mod = await import("https://cdn.jsdelivr.net/npm/@tonconnect/ui@2.3.1/+esm");
    const tonConnectUI = new mod.TonConnectUI({
      manifestUrl: `${location.origin}/tonconnect-manifest.json`,
      buttonRootId: "ton-connect"
    });
    tonConnectUI.onStatusChange(wallet => {
      const dot = document.querySelector(".wallet-dot");
      if (wallet) {
        dot.style.background = "#6be6a1";
        $("walletQuick").lastElementChild.textContent = "TON ✓";
      } else {
        dot.style.background = "";
        $("walletQuick").lastElementChild.textContent = tr("wallet");
      }
    });
  } catch (e) {
    $("ton-connect").innerHTML = `<div class="muted" style="font-size:12px">TON Connect unavailable in this browser preview.</div>`;
  }
}

if (state.lang) $("languageModal").classList.remove("open");
render();
tick();
setInterval(tick, 30000);
loadSession();
initTonConnect();
