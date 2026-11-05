const tg=window.Telegram?.WebApp;
try{tg?.ready();tg?.expand();tg?.setHeaderColor("#090512");tg?.setBackgroundColor("#090512")}catch(_){}

const defaultState=()=>({
  level:12,eggs:12480,pending:3726,food:78,water:64,clean:82,demoTon:1.25,
  dailyBuyUsed:140,dailySellUsed:4,rewardClaimed:false,outfit:"Royal Neon",
  completedTasks:{},lastTick:Date.now(),rate:248
});
let state;
try{state={...defaultState(),...JSON.parse(localStorage.getItem("cocochi.v7")||"{}")}}catch(_){state=defaultState()}
state.completedTasks=state.completedTasks||{};
let config={botUsername:"cocochi_bot"},session={demo:true,user:null},previousRoute="home",currentRoute="home",marketMode="buy",tonUI=null,toastTimer;

const $=id=>document.getElementById(id);
const fmt=n=>Math.floor(Number(n)||0).toLocaleString("ru-RU");
const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
const persist=()=>localStorage.setItem("cocochi.v7",JSON.stringify(state));
const haptic=(kind="light")=>{try{tg?.HapticFeedback?.impactOccurred(kind)}catch(_){}};
const notify=(kind="success")=>{try{tg?.HapticFeedback?.notificationOccurred(kind)}catch(_){}};

function showToast(text){clearTimeout(toastTimer);$("toast").textContent=text;$("toast").classList.add("show");toastTimer=setTimeout(()=>$("toast").classList.remove("show"),1800)}
function burst(symbol="🥚"){const root=$("burst");root.innerHTML="";for(let i=0;i<14;i++){const p=document.createElement("span");const a=Math.PI*2*i/14+(Math.random()-.5)*.25;const d=90+Math.random()*150;p.className="particle";p.textContent=symbol;p.style.setProperty("--x",Math.cos(a)*d+"px");p.style.setProperty("--y",(Math.sin(a)*d-90)+"px");p.style.setProperty("--r",((Math.random()-.5)*280)+"deg");root.appendChild(p)}setTimeout(()=>root.innerHTML="",900)}

function render(){
  const rate=Math.round(state.rate*(Math.min(state.food,state.water,state.clean)/100*.35+.65));
  $("eggBalance").textContent=fmt(state.eggs);
  $("tonBalance").textContent=Number(state.demoTon).toFixed(2);
  $("homeLevel").textContent=state.level;$("coopLevel").textContent=state.level;
  $("upgradeLevel").textContent=state.level+1;$("nextLevel").textContent=state.level+1;
  $("pendingEggs").textContent=fmt(state.pending);$("rateValue").textContent=fmt(rate);$("coopRate").textContent=fmt(rate);
  $("marketEggs").textContent=fmt(state.eggs);
  ["food","water","clean"].forEach(k=>{const v=Math.round(state[k]);$(k+"Value").textContent=v;$(k+"Bar").style.width=v+"%"});
  $("buyLimit").textContent=state.dailyBuyUsed+" / 200";$("sellLimit").textContent=state.dailySellUsed+" / 25";
  $("upgradeCost").textContent=fmt(levelCost());
  $("outfitName").textContent=state.outfit;
  document.querySelectorAll(".outfit").forEach(b=>{const on=b.dataset.outfit===state.outfit;b.classList.toggle("active",on);b.querySelector("small").textContent=on?"Надето":b.dataset.cost||b.querySelector("small").textContent});
  if(state.rewardClaimed){$("dailyRewardBtn").textContent="Уже получено ✓";$("dailyRewardBtn").disabled=true}
}
function levelCost(){return 2500+Math.max(0,state.level-12)*700}
function navigate(name,{remember=true}={}){
  const target=document.querySelector('[data-screen="'+name+'"]');if(!target)return;
  if(remember&&name!==currentRoute)previousRoute=currentRoute;
  currentRoute=name;
  document.querySelectorAll(".screen").forEach(s=>s.classList.toggle("active",s===target));
  document.querySelectorAll(".nav-btn").forEach(b=>b.classList.toggle("active",b.dataset.route===name));
  document.querySelector(".bottom-nav").style.display=["tasks","rewards","events","wardrobe"].includes(name)?"none":"grid";
  window.scrollTo({top:0,behavior:"instant"});haptic();
}
document.querySelectorAll("[data-route]").forEach(b=>b.addEventListener("click",()=>navigate(b.dataset.route)));
document.querySelectorAll("[data-back]").forEach(b=>b.addEventListener("click",()=>navigate(previousRoute||"home",{remember:false})));

function spendEggs(cost){if(state.eggs<cost){showToast("Не хватает яиц 🥚");notify("error");return false}state.eggs-=cost;return true}
document.querySelectorAll("[data-care]").forEach(b=>b.addEventListener("click",()=>{
  const k=b.dataset.care,cost={food:600,water:300,clean:400}[k];if(!spendEggs(cost))return;state[k]=100;persist();render();burst(k==="water"?"💧":"✨");showToast("Люся довольна · "+fmt(cost)+" 🥚");notify();
}));
document.querySelector('[data-action="collect"]').addEventListener("click",()=>{state.eggs+=state.pending;state.pending=0;state.completedTasks.collect=true;persist();render();burst("🥚");showToast("Яйца собраны ✓");notify()});

function openModal({icon="🐔",title="COCOCHI",text="",body="",actions=[]}){
  $("modalIcon").textContent=icon;$("modalTitle").textContent=title;$("modalText").textContent=text;$("modalBody").innerHTML=body;$("modalActions").innerHTML="";
  actions.forEach(a=>{const b=document.createElement("button");b.textContent=a.label;b.className=a.kind==="purple"?"purple-button":"gold-button";b.addEventListener("click",a.onClick);$("modalActions").appendChild(b)});
  $("actionModal").classList.add("open");$("actionModal").setAttribute("aria-hidden","false");haptic("medium")
}
function closeModal(){$("actionModal").classList.remove("open");$("actionModal").setAttribute("aria-hidden","true")}
document.querySelectorAll('[data-action="closeModal"]').forEach(b=>b.addEventListener("click",closeModal));

function marketModal(mode){
  marketMode=mode;const isBuy=mode==="buy";
  openModal({icon:isBuy?"🥚":"💎",title:isBuy?"Купить яйца":"Продать яйца",text:"DEMO-операция. Реальные платежи в MVP отключены.",
    body:'<div class="amount-control"><button id="minusAmount">−</button><input id="marketAmount" type="number" min="1" max="100" value="10"><button id="plusAmount">+</button></div><div class="market-summary" id="marketSummary"></div>',
    actions:[{label:isBuy?"Купить в DEMO":"Продать в DEMO",kind:isBuy?"purple":"gold",onClick:confirmMarket}]
  });
  const input=$("marketAmount");const update=()=>{const amount=clamp(parseInt(input.value||"1",10),1,100);input.value=amount;$("marketSummary").textContent=amount+" 🥚  "+(isBuy?"←":"→")+"  "+(amount*.0042).toFixed(4)+" DEMO TON"};
  $("minusAmount").onclick=()=>{input.value=Math.max(1,+input.value-1);update()};$("plusAmount").onclick=()=>{input.value=Math.min(100,+input.value+1);update()};input.oninput=update;update();
}
function confirmMarket(){
  const amount=clamp(parseInt($("marketAmount").value||"1",10),1,100),ton=amount*.0042;
  if(marketMode==="buy"){const rem=200-state.dailyBuyUsed;if(amount>rem)return showToast("Лимит покупки: "+rem+" 🥚");if(state.demoTon<ton)return showToast("Недостаточно DEMO TON");state.demoTon-=ton;state.eggs+=amount;state.dailyBuyUsed+=amount}
  else{const rem=25-state.dailySellUsed;if(amount>rem)return showToast("Лимит продажи: "+rem+" 🥚");if(!spendEggs(amount))return;state.demoTon+=ton;state.dailySellUsed+=amount}
  persist();render();closeModal();burst(marketMode==="buy"?"🥚":"💎");showToast("DEMO-операция выполнена ✓")
}
document.querySelectorAll('[data-action="buy"]').forEach(b=>b.addEventListener("click",()=>marketModal("buy")));
document.querySelectorAll('[data-action="sell"]').forEach(b=>b.addEventListener("click",()=>marketModal("sell")));

document.querySelectorAll("[data-upgrade]").forEach(b=>b.addEventListener("click",()=>{
  const data={production:["Производство",5000,"+10% к яйцам/час"],energy:["Энергия",3500,"Быстрее восстановление"],health:["Здоровье",8000,"Стабильный бонус"]}[b.dataset.upgrade];
  openModal({icon:"⚡",title:data[0],text:data[2]+" · стоимость "+fmt(data[1])+" 🥚",actions:[{label:"Улучшить · "+fmt(data[1])+" 🥚",onClick:()=>{if(!spendEggs(data[1]))return;state.rate=Math.round(state.rate*1.1);persist();render();closeModal();burst("⚡");showToast(data[0]+" улучшено ✓")}}]})
}));

function shareInvite(){
  const uid=session?.user?.id;const username=config.botUsername||"cocochi_bot";const ref=uid?"https://t.me/"+username+"?start=ref_"+uid:"https://t.me/"+username;
  const share="https://t.me/share/url?url="+encodeURIComponent(ref)+"&text="+encodeURIComponent("Заводи свою COCOCHI 🐔");
  state.completedTasks.invite=true;persist();
  try{tg?.openTelegramLink?tg.openTelegramLink(share):window.open(share,"_blank")}catch(_){window.open(share,"_blank")}
}
document.querySelectorAll('[data-action="invite"]').forEach(b=>b.addEventListener("click",shareInvite));

document.querySelector('[data-action="levelUp"]').addEventListener("click",()=>{const c=levelCost();if(!spendEggs(c))return;state.level++;state.rate=Math.round(state.rate*1.12);persist();render();burst("⭐");showToast("Новый уровень: "+state.level+" ✓")});

document.querySelectorAll("[data-task]").forEach(b=>b.addEventListener("click",()=>{
  const id=b.dataset.task;if(id==="invite"){shareInvite();return}
  if(state.completedTasks[id+"_claimed"])return showToast("Награда уже получена");
  const reward=id==="care"?250:500;state.eggs+=reward;state.completedTasks[id+"_claimed"]=true;persist();render();b.querySelector(".claim").textContent="Получено ✓";burst("🥚");showToast("+"+fmt(reward)+" 🥚")
}));

document.querySelector('[data-action="dailyReward"]').addEventListener("click",()=>{if(state.rewardClaimed)return;state.rewardClaimed=true;state.eggs+=2500;state.demoTon+=1;persist();render();burst("🎁");showToast("Награда получена: 2 500 🥚 + 1 TON");notify()});
document.querySelector('[data-action="joinEvent"]').addEventListener("click",()=>{showToast("Ты участвуешь в EGG RUSH ⚡");burst("⚡")});

document.querySelectorAll(".outfit").forEach(b=>b.addEventListener("click",()=>{
  const name=b.dataset.outfit;if(name===state.outfit)return showToast("Этот образ уже надет");
  const price={RoyalNeon:0,"Street Gold":2000,Cosmic:3500,Angel:5000}[name]||0;if(price&&!spendEggs(price))return;
  state.outfit=name;persist();render();burst("✨");showToast("Образ «"+name+"» надет")
}));

document.querySelector('[data-action="language"]').addEventListener("click",()=>openModal({icon:"🌐",title:"Язык",text:"В текущем MVP активен русский интерфейс.",actions:[{label:"Русский ✓",kind:"purple",onClick:closeModal}]}));
document.querySelector('[data-action="reset"]').addEventListener("click",()=>openModal({icon:"↻",title:"Сбросить DEMO?",text:"Баланс, уровень и прогресс вернутся к стартовому состоянию.",actions:[{label:"Сбросить DEMO",onClick:()=>{state=defaultState();persist();render();closeModal();navigate("home");showToast("DEMO сброшено")}}]}));

async function ensureTon(){
  if(tonUI)return tonUI;try{const mod=await import("https://cdn.jsdelivr.net/npm/@tonconnect/ui@2.3.1/+esm");tonUI=new mod.TonConnectUI({manifestUrl:location.origin+"/tonconnect-manifest.json",buttonRootId:"tonConnectMount"});return tonUI}catch(_){showToast("TON Connect недоступен в этом браузере");return null}
}
document.querySelectorAll('[data-action="wallet"]').forEach(b=>b.addEventListener("click",async()=>{navigate("profile");await ensureTon();try{await tonUI?.openModal()}catch(_){}}));

async function loadSession(){
  try{
    const [c,s]=await Promise.all([fetch("/api/config"),fetch("/api/session",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({initData:tg?.initData||""})})]);
    config=await c.json();session=await s.json();const u=session.user;
    if(u){$("profileName").textContent=[u.first_name,u.last_name].filter(Boolean).join(" ")||u.username||"COCOCHI Player";$("profileId").textContent="@"+(u.username||u.id);$("refLink").textContent="https://t.me/"+(config.botUsername||"cocochi_bot")+"?start=ref_"+u.id}
  }catch(_){}
}

function passiveTick(){const now=Date.now(),hours=clamp((now-(state.lastTick||now))/3600000,0,6);if(hours>0){state.pending+=state.rate*hours;state.food=clamp(state.food-hours*1.5,0,100);state.water=clamp(state.water-hours*2.2,0,100);state.clean=clamp(state.clean-hours*.7,0,100);state.lastTick=now;persist();render()}}
passiveTick();render();loadSession();setInterval(passiveTick,30000);
