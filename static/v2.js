const tg = window.Telegram?.WebApp;
const $ = id => document.getElementById(id);
let state = null, session = null, config = {}, tonUI, busy = false, previous = 'home';
const fmt = n => Math.floor(Number(n) || 0).toLocaleString('ru-RU');
try { tg?.ready(); tg?.expand(); tg?.setHeaderColor('#090512'); tg?.setBackgroundColor('#090512'); } catch (_) {}
function viewport() {
  document.documentElement.style.setProperty('--tg-height', `${tg?.viewportStableHeight || innerHeight}px`);
  document.documentElement.style.setProperty('--safe-top', `${tg?.contentSafeAreaInset?.top || 0}px`);
}
tg?.onEvent('viewportChanged', viewport); tg?.onEvent('contentSafeAreaChanged', viewport); viewport();
let toastTimer;
function toast(text) { clearTimeout(toastTimer); $('toast').textContent = text; $('toast').classList.add('show'); toastTimer = setTimeout(() => $('toast').classList.remove('show'), 3500); }
function navigate(name) {
  if (!document.querySelector(`[data-screen="${name}"]`)) return;
  previous = document.querySelector('.screen.active')?.dataset.screen || 'home';
  document.querySelectorAll('.screen').forEach(n => n.classList.toggle('active', n.dataset.screen === name));
  document.querySelectorAll('.nav-btn').forEach(n => n.classList.toggle('active', n.dataset.route === name));
  try { tg?.HapticFeedback?.impactOccurred('light'); } catch (_) {}
  scrollTo(0, 0);
}
async function api(path, data, key) {
  const response = await fetch(path, {method: data === undefined ? 'GET' : 'POST', credentials: 'same-origin', headers: {'Content-Type':'application/json', 'X-Cocochi-Request':'1', ...(key ? {'Idempotency-Key':key} : {})}, ...(data !== undefined ? {body:JSON.stringify(data)} : {})});
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Не удалось выполнить запрос');
  return body;
}
function render() {
  if (!state) return;
  for (const id of ['eggBalance','marketEggs']) $(id).textContent = fmt(state.eggs);
  $('tonBalance').textContent = '—'; // wallet holdings are never invented
  for (const id of ['homeLevel','coopLevel']) $(id).textContent = state.level;
  for (const id of ['upgradeLevel','nextLevel']) $(id).textContent = state.level + 1;
  $('pendingEggs').textContent = fmt(state.pending);
  const rate = state.rate * (.25 + .75 * Math.min(state.food,state.water,state.clean) / 100);
  for (const id of ['rateValue','coopRate']) $(id).textContent = fmt(rate);
  for (const k of ['food','water','clean']) { $(k+'Value').textContent = Math.round(state[k]); $(k+'Bar').style.width = `${state[k]}%`; }
  $('upgradeCost').textContent = fmt(state.upgradeCost);
  $('sellLimit').textContent = `${state.sellRemaining} 🥚 осталось`;
  $('buyLimit').textContent = '10 заказов / день';
  $('outfitName').textContent = state.outfit;
  window.cocochiAppearance=state.outfit; window.dispatchEvent(new CustomEvent('cocochi-state',{detail:state}));
  document.querySelector('.mood-pill b').textContent = Math.min(state.food,state.water,state.clean)>60 ? 'Счастливая' : 'Нужен уход';
  document.querySelectorAll('[data-care]').forEach(b=>b.querySelector('.care-cta').textContent=({food:'Покормить',water:'Напоить',clean:'Почистить'})[b.dataset.care]+' · '+state.catalog.care[b.dataset.care]+' 🥚');
  document.querySelector('.wardrobe-preview').dataset.outfit = state.outfit;
  document.querySelectorAll('.outfit').forEach(b => { const name = b.dataset.outfit; b.classList.toggle('active', name === state.outfit); b.querySelector('small').textContent = name === state.outfit ? 'Надето' : state.owned.includes(name) ? 'Надеть' : fmt(state.catalog.outfits[name])+' 🥚'; });
  $('dailyRewardBtn').disabled = state.rewardClaimed;
  $('dailyRewardBtn').textContent = state.rewardClaimed ? 'Сегодня получено ✓' : `Получить ${state.catalog.daily} 🥚`;
  document.querySelectorAll('[data-task]').forEach(b => { const key = b.dataset.task; b.querySelector('em').textContent = '+'+state.catalog.tasks[key]+' 🥚'; b.querySelector('.claim').textContent = state.completedTasks[key] ? 'Получено' : 'Забрать'; });
  $('friendCount').textContent = `${state.friends} приглашённых друзей`;
  $('coinBalance').textContent = fmt(state.coins);
  $('coopUpgradeBtn').textContent = `Курятник ${state.coopUpgrade.level}/10 · ${state.coopUpgrade.cost} монет`;
  $('coopUpgradeBtn').disabled = state.coopUpgrade.level >= 10;
  $('eventProgress').textContent = `${state.event.progress} / 100 🥚`;
  $('eventButton').textContent = state.event.claimed ? 'Награда получена ✓' : state.event.joined ? 'Получить награду · 35 🥚' : 'Участвовать · 10 монет';
  $('eventButton').disabled = state.event.claimed;
  $('eventTime').textContent = 'ДО КОНЦА: ' + Math.max(0, Math.ceil((state.event.endsAt - Date.now()/1000)/3600)) + ' Ч';
  $('ledgerHistory').replaceChildren();
  for (const entry of state.history) {
    const li = document.createElement('div'); li.className = 'limit-row';
    const label = document.createElement('span'); label.textContent = `${({welcome:'Первый запуск',daily:'Ежедневная награда',collect:'Сбор яиц',care:'Уход',upgrade:'Новый уровень',outfit:'Гардероб',sell:'Обмен',coop:'Улучшение курятника',task:'Задание',event_entry:'Вход в событие',event_reward:'Награда события',stars_purchase:'Покупка Stars',refund_reserve:'Возврат'})[entry.type] || entry.type} · ${new Date(entry.created_at*1000).toLocaleDateString()}`;
    const amount = document.createElement('b'); amount.textContent = `${entry.amount > 0 ? '+' : ''}${entry.amount} ${entry.asset==='eggs'?'🥚':'монет'}`;
    li.append(label, amount); $('ledgerHistory').append(li);
  }
}
async function refresh() { state = await api('/api/game'); render(); }
// Preserve request key after uncertain network outcomes. No automatic duplicate spend.
let pendingOperation = null;
async function action(action, value = null) {
  if (busy || !state) return;
  const fingerprint = JSON.stringify([action,value]);
  if (pendingOperation && pendingOperation.fingerprint !== fingerprint) return toast('Повторите предыдущее действие для проверки результата');
  const key = pendingOperation?.key || crypto.randomUUID();
  pendingOperation = {fingerprint, key}; busy = true;
  try { state = await api('/api/game/action', {action,value}, key); pendingOperation = null; render(); toast('Готово ✓'); tg?.HapticFeedback?.notificationOccurred('success'); }
  catch (error) { toast(error.message); if (!(error instanceof TypeError)) pendingOperation = null; }
  finally { busy = false; }
}
document.querySelectorAll('[data-route]').forEach(b => b.onclick = () => navigate(b.dataset.route));
document.querySelectorAll('[data-back]').forEach(b => b.onclick = () => navigate(previous));
document.querySelectorAll('[data-care]').forEach(b => b.onclick = () => action('care', b.dataset.care));
document.querySelectorAll('.outfit').forEach(b => b.onclick = () => action('outfit',b.dataset.outfit));
document.querySelectorAll('[data-task]').forEach(b => b.onclick = () => action('task',b.dataset.task));
document.querySelectorAll('[data-upgrade]').forEach(b => b.onclick = () => toast('Уровень производства улучшается в курятнике'));
function modal(title, text, build) {
  $('modalTitle').textContent = title; $('modalText').textContent = text;
  $('modalBody').replaceChildren(); $('modalActions').replaceChildren();
  build?.($('modalBody'),$('modalActions'));
  $('actionModal').classList.add('open'); $('actionModal').setAttribute('aria-hidden','false');
}
function closeModal() { $('actionModal').classList.remove('open'); $('actionModal').setAttribute('aria-hidden','true'); }
function button(label, fn, root) { const b = document.createElement('button'); b.className = 'gold-button full'; b.textContent = label; b.onclick = fn; root.append(b); }
function buy() {
  modal('Магазин Stars', 'Яйца — цифровой игровой товар без денежной стоимости.', (body,actions) => {
    if (!config.starsEnabled || session?.demo) { body.textContent = 'Платежи пока недоступны. Играть и получать яйца можно бесплатно.'; return; }
    for (const [sku,p] of Object.entries(state.catalog.packages)) button(`${p.eggs} 🥚 · ${p.stars} ⭐`, async () => {
      if (busy) return; busy = true;
      try {
        const order = await api('/api/orders',{sku},crypto.randomUUID());
        if (!tg?.openInvoice) throw new Error('Откройте приложение в Telegram');
        tg.openInvoice(order.invoiceUrl, async status => { toast(status === 'paid' ? 'Платёж отправлен. Ожидаем подтверждение сервера.' : 'Статус: '+status); await refresh(); });
        closeModal();
      } catch (error) { toast(error.message); } finally { busy = false; }
    }, actions);
  });
}
function sell() {
  modal('Обмен яиц', '1 яйцо → 2 внутренние монеты. Комиссия 0. Монеты нельзя вывести в TON.', (body,actions) => {
    const input = document.createElement('input'); input.type='number'; input.min=1; input.max=Math.min(state.eggs,state.sellRemaining); input.value=10; input.className='amount-control';
    const preview = document.createElement('p');
    const update = () => { const n = Number(input.value); preview.textContent = `Получите: ${fmt(n*2)} монет · Остаток: ${fmt(state.eggs-n)} 🥚`; };
    input.oninput=update; body.append(input,preview); update();
    button('Обменять', async () => { await action('sell',Number(input.value)); closeModal(); },actions);
  });
}
function invite() {
  const uid = session?.user?.id;
  if (!uid) return toast('Приглашения доступны в Telegram');
  const link = `https://t.me/${config.botUsername || 'cocochi_bot'}?startapp=ref_${uid}`;
  const share = 'https://t.me/share/url?url='+encodeURIComponent(link);
  if (tg?.openTelegramLink) tg.openTelegramLink(share); else window.open(share,'_blank','noopener');
}
async function ensureTon() {
  if (tonUI) return tonUI;
  const mod = await import('https://cdn.jsdelivr.net/npm/@tonconnect/ui@2.3.1/+esm');
  tonUI = new mod.TonConnectUI({manifestUrl:location.origin+'/tonconnect-manifest.json',buttonRootId:'tonConnectMount'});
  tonUI.onStatusChange(wallet => {
    $('walletAddress').textContent = wallet ? `${wallet.account.address.slice(0,8)}…${wallet.account.address.slice(-6)} · ${wallet.account.chain === '-3' ? 'testnet' : 'mainnet'}` : 'Кошелёк не подключён';
    // This is wallet UI state, never proof of account ownership on the backend.
  });
  await tonUI.connectionRestored;
  return tonUI;
}
const actions = {
  collect: () => action('collect'), levelUp: () => action('upgrade'), dailyReward: () => action('daily'), buy, sell, invite,
  closeModal,
  wallet: async () => { navigate('profile'); try { const ui = await ensureTon(); if (!ui.connected) await ui.openModal(); } catch (_) { toast('TON Connect недоступен. Попробуйте позже'); } },
  disconnect: async () => { try { await tonUI?.disconnect(); } catch (_) { toast('Не удалось отключить кошелёк'); } },
  testTransaction: async () => {
    try {
      const ui=await ensureTon();
      if(!ui.connected) return toast('Сначала подключите testnet-кошелёк');
      if(ui.account.chain!=='-3') return toast('Переключите кошелёк на testnet. Mainnet-переводы отключены.');
      modal('Перевод себе в testnet','0.01 тестового TON на ваш же подключённый адрес. Кошелёк запросит подпись и сетевую комиссию. Это не покупка игровых товаров.',(_,buttons)=>{
        button('Подписать в testnet',async()=>{
          closeModal();$('tonTransactionStatus').textContent='Ожидается подпись в кошельке…';
          try {
            await ui.sendTransaction({validUntil:Math.floor(Date.now()/1000)+300,network:'-3',from:ui.account.address,messages:[{address:ui.account.address,amount:'10000000'}]});
            $('tonTransactionStatus').textContent='Кошелёк вернул подписанную транзакцию. Подтверждение в блокчейне ещё не проверено.';
          } catch(_) { $('tonTransactionStatus').textContent='Перевод отменён или кошелёк вернул ошибку. Начислений в игре нет.'; }
        },buttons);
      });
    } catch(_) {toast('Не удалось загрузить TON Connect');}
  },
  language: () => toast('Русский интерфейс'), reset: () => toast('Серверный прогресс нельзя сбросить в браузере'),
  joinEvent: () => action(state?.event.joined ? 'event_claim' : 'event_join'),
  coopUpgrade: () => action('coop'),
  payments: async () => {
    try { const orders=await api('/api/orders'); modal('История платежей','При обращении в /paysupport укажите номер заказа.', body => { for(const o of orders) { const p=document.createElement('p'); p.textContent=`${o.id} · ${o.stars} ⭐ · ${o.status}`; body.append(p); } if(!orders.length) body.textContent='Заказов пока нет'; }); } catch(e) { toast(e.message); }
  }
};
document.querySelectorAll('[data-action]').forEach(b => b.onclick=() => actions[b.dataset.action]?.());
async function boot() {
  document.body.classList.add('loading');
  try {
    config = await api('/api/config');
    session = await api('/api/session',{initData:tg?.initData || ''});
    const u=session.user;
    if(u) { $('profileName').textContent=[u.first_name,u.last_name].filter(Boolean).join(' ') || u.username || 'Player'; $('profileId').textContent='@'+(u.username || u.id); $('refLink').textContent=`https://t.me/${config.botUsername || 'cocochi_bot'}?startapp=ref_${u.id}`; }
    $('sessionStatus').textContent = session.demo ? 'Локальная демосессия · серверное сохранение' : 'Telegram · серверное сохранение';
    await refresh();
    ensureTon().catch(() => {});
  } catch(error) { $('sessionStatus').textContent=error.message; toast(error.message); }
  finally { document.body.classList.remove('loading'); }
}
boot();
setInterval(() => { if(state && !busy && !document.hidden) refresh().catch(() => {}); },30000);
