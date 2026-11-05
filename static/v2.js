const tg=window.Telegram?.WebApp;
try{tg?.ready();tg?.expand();tg?.setHeaderColor("#050308");tg?.setBackgroundColor("#050308")}catch(_){}
const home=document.getElementById("homeScreen"),market=document.getElementById("marketScreen"),toast=document.getElementById("toast"),sheet=document.getElementById("sheet"),sheetTitle=document.getElementById("sheetTitle"),sheetText=document.getElementById("sheetText"),sheetIcon=document.getElementById("sheetIcon"),sheetActions=document.getElementById("sheetActions"),sheetClose=document.getElementById("sheetClose"),sheetBackdrop=document.getElementById("sheetBackdrop"),tonMount=document.getElementById("tonConnectMount"),burst=document.getElementById("burst");
let toastTimer,tonUI=null;
function haptic(k="light"){try{tg?.HapticFeedback?.impactOccurred(k)}catch(_){}}
function notify(k="success"){try{tg?.HapticFeedback?.notificationOccurred(k)}catch(_){}}
function showToast(m){clearTimeout(toastTimer);toast.textContent=m;toast.classList.add("show");toastTimer=setTimeout(()=>toast.classList.remove("show"),1700)}
function screen(n){home.classList.toggle("active",n==="home");market.classList.toggle("active",n==="market");window.scrollTo({top:0,behavior:"smooth"});haptic()}
function closeSheet(){sheet.classList.remove("open");sheet.setAttribute("aria-hidden","true");tonMount.classList.add("hidden")}
function addAction(label,klass,fn){const b=document.createElement("button");b.type="button";b.className=("sheet-action "+(klass||"")).trim();b.textContent=label;b.addEventListener("click",fn);sheetActions.appendChild(b)}
function openSheet(o={}){sheetIcon.textContent=o.icon||"🐔";sheetTitle.textContent=o.title||"COCOCHI";sheetText.textContent=o.text||"";sheetActions.innerHTML="";tonMount.classList.add("hidden");(o.actions||[]).forEach(a=>addAction(a.label,a.klass,a.onClick));sheet.classList.add("open");sheet.setAttribute("aria-hidden","false");haptic("medium")}
function confetti(symbol="🥚"){burst.innerHTML="";for(let i=0;i<12;i++){const p=document.createElement("span"),ang=Math.PI*2*i/12+(Math.random()-.5)*.25,dist=90+Math.random()*150;p.className="particle";p.textContent=symbol;p.style.setProperty("--x",Math.cos(ang)*dist+"px");p.style.setProperty("--y",(Math.sin(ang)*dist-80)+"px");p.style.setProperty("--r",((Math.random()-.5)*260)+"deg");burst.appendChild(p)}setTimeout(()=>burst.innerHTML="",900)}
async function ensureTonConnect(){if(tonUI)return tonUI;try{const mod=await import("https://cdn.jsdelivr.net/npm/@tonconnect/ui@2.3.1/+esm");tonMount.classList.remove("hidden");tonUI=new mod.TonConnectUI({manifestUrl:location.origin+"/tonconnect-manifest.json",buttonRootId:"tonConnectMount"});return tonUI}catch(_){showToast("TON Connect не загрузился");return null}}
function shareInvite(){const username="cocochi_bot",uid=tg?.initDataUnsafe?.user?.id,ref=uid?"https://t.me/"+username+"?start=ref_"+uid:"https://t.me/"+username,url="https://t.me/share/url?url="+encodeURIComponent(ref)+"&text="+encodeURIComponent("Заводи свою COCOCHI 🐔");try{tg?.openTelegramLink?tg.openTelegramLink(url):window.open(url,"_blank")}catch(_){}}
const actionMap={
close(){try{tg?.close()}catch(_){showToast("Закрыть Mini App")}},
wallet(){openSheet({icon:"💎",title:"TON Wallet",text:"Подключение кошелька через TON Connect. Seed-фраза приложению не передаётся."});tonMount.classList.remove("hidden");ensureTonConnect()},
collect(){confetti("🥚");notify();showToast("Собрано 3 726 яиц 🥚")},
feed(){openSheet({icon:"🌽",title:"Покормить COCOCHI",text:"Стоимость ухода: 600 🥚. После кормления сытость восстанавливается до 100%.",actions:[{label:"Покормить · 600 🥚",klass:"green",onClick(){confetti("🌽");closeSheet();showToast("Сытость 100% ✓")}}]})},
water(){openSheet({icon:"💧",title:"Напоить COCOCHI",text:"Стоимость ухода: 300 🥚. Вода восстанавливается до 100%.",actions:[{label:"Напоить · 300 🥚",klass:"purple",onClick(){confetti("💧");closeSheet();showToast("Вода 100% ✓")}}]})},
clean(){openSheet({icon:"🫧",title:"Почистить COCOCHI",text:"Стоимость ухода: 400 🥚. Чистота восстанавливается до 100%.",actions:[{label:"Почистить · 400 🥚",klass:"purple",onClick(){confetti("✨");closeSheet();showToast("Чистота 100% ✓")}}]})},
buy(){openSheet({icon:"🥚",title:"Купить яйца",text:"DEMO рынка. В production здесь будет реальная котировка и подтверждение TON-транзакции.",actions:[{label:"Купить 100 🥚",klass:"purple",onClick(){closeSheet();showToast("DEMO: +100 🥚")}}]})},
sell(){openSheet({icon:"💎",title:"Продать яйца",text:"DEMO продажи. Здесь будет виден текущий sell-limit, цена и итог в TON.",actions:[{label:"Продать 25 🥚",klass:"green",onClick(){closeSheet();showToast("DEMO: ордер создан")}}]})},
clothes(){openSheet({icon:"👑",title:"Гардероб COCOCHI",text:"Короны, очки, цепи и сезонные образы — в той же 3D-стилистике.",actions:[{label:"Открыть гардероб",klass:"purple",onClick(){closeSheet();showToast("Гардероб — следующий экран")}}]})},
marketInfo(){showToast("1 🥚 = 0.0042 TON · +6.8% / 24ч")},
upgradeProduction(){openSheet({icon:"⬆️",title:"Производство",text:"+10% к яйцам/час. Стоимость: 5 000 🥚.",actions:[{label:"Улучшить · 5 000 🥚",onClick(){confetti("⚡");closeSheet();showToast("DEMO: производство улучшено")}}]})},
upgradeEnergy(){openSheet({icon:"⚡",title:"Энергия",text:"COCOCHI несёт яйца быстрее. Стоимость: 3 500 🥚.",actions:[{label:"Улучшить · 3 500 🥚",onClick(){closeSheet();showToast("DEMO: энергия улучшена")}}]})},
upgradeHealth(){openSheet({icon:"❤️",title:"Здоровье",text:"Стабильное производство. Стоимость: 8 000 🥚.",actions:[{label:"Улучшить · 8 000 🥚",onClick(){closeSheet();showToast("DEMO: здоровье улучшено")}}]})},
invite(){shareInvite()},
friends(){openSheet({icon:"👥",title:"Друзья",text:"Пригласи друга. После активации COCOCHI вы оба получаете +10% к производству на 24 часа.",actions:[{label:"Пригласить друга",klass:"purple",onClick:shareInvite}]})},
profile(){openSheet({icon:"👤",title:"Профиль",text:"Telegram-профиль, TON-кошелёк, язык и настройки COCOCHI.",actions:[{label:"Подключить TON",klass:"purple",onClick(){tonMount.classList.remove("hidden");ensureTonConnect()}}]})},
coop(){openSheet({icon:"🐔",title:"Курятник",text:"Дом COCOCHI, коллекция образов и состояние курицы. Визуально — тот же премиальный 3D.",actions:[{label:"Понятно",onClick:closeSheet}]})},
reward(){showToast("Награды: ежедневный бонус 🎁")},
tasks(){showToast("Задания открыты ✅")},
events(){showToast("События COCOCHI 🏆")}
};
document.querySelectorAll("[data-screen]").forEach(b=>b.addEventListener("click",()=>screen(b.dataset.screen)));
document.querySelectorAll("[data-action]").forEach(b=>{b.addEventListener("pointerdown",()=>b.classList.add("pressed"));b.addEventListener("pointerup",()=>b.classList.remove("pressed"));b.addEventListener("pointercancel",()=>b.classList.remove("pressed"));b.addEventListener("click",()=>{const fn=actionMap[b.dataset.action];if(fn)fn()})});
sheetClose.addEventListener("click",closeSheet);sheetBackdrop.addEventListener("click",closeSheet);document.addEventListener("keydown",e=>{if(e.key==="Escape")closeSheet()});