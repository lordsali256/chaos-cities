const app = document.getElementById('app');
const byId = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const rarityLabel = tier => ({white:'Common',green:'Uncommon',blue:'Rare',purple:'Epic',orange:'Legendary'})[tier] || 'Common';
const REALITY_STAGES = ['Ordinary morning','A peculiar forecast','The sky is listening','Unlicensed moon','Suspicious weather','Buildings remember','Gravity takes lunch','The skyline wanders','Portal season','The city blinks','Parallel rush hour','Reality resigns'];
const LANDSCAPES = ['Meadow','Farmland','Small Town','Garden City','Market Town','Harbor','Tech City','Dystopia','Dream City'];
const MOODS = ['Sunny','Hopeful','Cozy','Busy','Curious','Melancholy','Restless','Surreal'];
const PATH_COLORS = ['#4b8b69','#688f58','#789879','#6c9381','#7a8c92','#637f94','#6d88a4','#716e84','#8b7199'];
const MOOD_COLORS = ['#dbc481','#a6c992','#c8a884','#80b5a3','#91a9ca','#8292a8','#b77e87','#a380b8'];
const blendHex = (a,b,t) => '#' + [1,3,5].map(i => Math.round(parseInt(a.slice(i,i+2),16)*(1-t)+parseInt(b.slice(i,i+2),16)*t).toString(16).padStart(2,'0')).join('');
function cityPath(city) {
  const hash = [...city.id].reduce((n,ch) => (n * 33 + ch.charCodeAt(0)) >>> 0, 5381);
  const landscape = hash % LANDSCAPES.length, mood = Math.floor(hash / LANDSCAPES.length) % MOODS.length;
  const age = Math.min(1, Math.max(0, (Date.now()/1000 - city.created_at) / (90*86400)));
  const drift = Math.min(1, age * .86 + Math.max(0, city.weirdness-2) / 100 * .14);
  document.body.style.setProperty('--sky-top', blendHex('#42899a', PATH_COLORS[landscape], drift));
  document.body.style.setProperty('--sky-bottom', blendHex('#b2c889', MOOD_COLORS[mood], drift));
  document.body.style.setProperty('--ground', blendHex('#557d50', PATH_COLORS[landscape], drift));
  document.body.style.setProperty('--tower', blendHex('#496755', PATH_COLORS[landscape], drift));
  document.body.style.setProperty('--city-panel', blendHex('#243b36', blendHex(PATH_COLORS[landscape], '#202b39', .67), drift));
  document.body.style.setProperty('--city-accent', blendHex('#91d3a0', MOOD_COLORS[mood], drift));
  return `${MOODS[mood]} ${LANDSCAPES[landscape]}`;
}
const realityStage = weirdness => Math.max(0, Math.min(11, Math.floor((Number(weirdness) - 2) * 12 / 99)));
const state = {
  server: localStorage.getItem('chaos_server') || location.origin,
  key: localStorage.getItem('chaos_key') || '',
  me: null, phoneServerUrl: '', cities: [], battleRecords: {}, pairAttacks: {}, pairBattleLimit: 2, events: [], feed: [], heroes: [], residents: [], buildings: [], buildingOffers: [], shop: [], techTree: [], specializations: [], trades: [], tradeQuota: {sent_today: 0, daily_limit: 10, pair_sent_today: {}, pair_daily_limit: 4}, rivalHeroes: [], nextOffersAt: 0, research: null, dailyTagline: '',
  eventTab: 'self', logTab: 'all', traitsOpen: false, traitSearch: '', traitCategory: 'All', traitSort: 'high', groupTraits: localStorage.getItem('chaos_group_traits') !== 'false',
  setupMode: 'new', page: 'city', busy: false, selectedTech: 'city_charter', techBranch: 'Commerce',
  googleClientId: '',
};

function toast(message) {
  const element = byId('toast');
  element.textContent = message;
  element.classList.add('show');
  setTimeout(() => element.classList.remove('show'), 3500);
}

async function api(path, options = {}) {
  const {timeoutMs = 30000, ...request} = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(state.server.replace(/\/$/, '') + path, {
      ...request,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(state.key ? {'Authorization': 'Bearer ' + state.key} : {}),
        ...(options.headers || {}),
      },
    });
    let data = {};
    try { data = await response.json(); } catch {}
    if (!response.ok) throw new Error(data.detail || 'Server unavailable');
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('Server did not answer. Check its address and connection.');
    if (error instanceof TypeError) throw new Error('Cannot reach the game server. Check the address and Wi-Fi.');
    throw error;
  } finally { clearTimeout(timer); }
}

function validServer(address) {
  try {
    const url = new URL(address);
    if (url.username || url.password || url.search || url.hash || (url.pathname !== '/' && url.pathname !== '')) return false;
    if (url.protocol === 'https:') return true;
    if (url.protocol !== 'http:') return false;
    const host = url.hostname.toLowerCase();
    const parts = host.split('.').map(Number);
    return host === 'localhost' || host === '127.0.0.1' ||
      (parts.length === 4 && parts.every(part => Number.isInteger(part) && part >= 0 && part <= 255) &&
       (parts[0] === 10 || (parts[0] === 192 && parts[1] === 168) || (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31)));
  } catch { return false; }
}

function clock(seconds) {
  const remaining = Math.max(0, seconds - Math.floor(Date.now() / 1000));
  if (!remaining) return 'ready';
  if (remaining >= 3600) return `${Math.floor(remaining / 3600)}h ${Math.floor(remaining % 3600 / 60)}m`;
  return `${Math.floor(remaining / 60)}m ${remaining % 60}s`;
}
function attackable(city) {
  return Date.now()/1000 >= city.battle_shield_until && (city.incoming_attacks_24h || 0) < (city.incoming_attack_limit || 6);
}

function setup() {
  const defaultUrl = state.server.includes('localhost') ? '' : state.server;
  app.innerHTML = `<div class="shell">
    <header class="brand"><div class="logo"><div class="logo-mark">⚡</div>Chaos Cities</div><span class="pill">ONE CITY. INFINITE NONSENSE.</span></header>
    <div class="form-wrap"><span class="eyebrow">THE WORLD GETS WEIRDER</span>
      <h1>Build a city.<br>Break reality.</h1>
      <p>Each player has one city, hourly Chaos Tokens, and a local AI that keeps inventing trouble even while you are away.</p>
      <label class="field">GAME SERVER ADDRESS<input class="input" id="server" type="url" placeholder="https://your-game.example.com" value="${esc(defaultUrl)}" required></label>
      <details id="key-login" open><summary>Enter with a city key</summary>
      <div class="setup-toggle"><button class="${state.setupMode === 'new' ? 'primary' : 'secondary'}" onclick="setSetupMode('new')">New city</button><button class="${state.setupMode === 'recover' ? 'primary' : 'secondary'}" onclick="setSetupMode('recover')">Return to mine</button></div>
      <form class="form" id="setup-form">
        ${state.setupMode === 'new'
          ? `<label class="field">YOUR NAME<input class="input" id="player" maxlength="24" placeholder="Mayor Noodle" required></label><label class="field">CITY NAME<input class="input" id="city" maxlength="28" placeholder="New Bananopolis" required></label><label class="field">INVITE CODE (IF YOUR HOST USES ONE)<input class="input" id="invite" placeholder="Ask the host for this"></label>`
          : `<label class="field">YOUR CITY KEY<input class="input" id="key" placeholder="Paste your saved city key" required></label>`}
        <button class="primary" type="submit">${state.setupMode === 'new' ? 'Found my city →' : 'Enter my city →'}</button>
      </form></details><div class="notice" id="connection-error" style="display:none"></div>
      <div class="notice">Save your city key. It is your way back on another phone. Internet servers must use HTTPS.</div>
    </div></div>`;
  byId('setup-form').onsubmit = submitSetup;
  byId('server').onchange = () => { state.server = byId('server').value.trim().replace(/\/$/, ''); };
  byId('key-login').open = true;
}

async function prepareGoogleLogin() {
  try {
    const config = await api('/api/auth/config', {timeoutMs:7000});
    if (!config.google_client_id || !byId('google-login')) return;
    state.googleClientId = config.google_client_id;
    byId('google-login').hidden = false;
    byId('key-login').open = false;
    byId('google-invite-wrap').innerHTML = config.invite_required ? '<label class="field">INVITE CODE<input class="input" id="google-invite" placeholder="Ask the host for this"></label>' : '';
    if (window.ChaosGoogleSignIn) {
      byId('google-button').innerHTML = '<button class="primary" onclick="nativeGoogleLogin()">Continue with Google</button>';
    } else {
      const script = document.getElementById('google-identity') || document.createElement('script');
      script.id = 'google-identity'; script.src = 'https://accounts.google.com/gsi/client'; script.async = true;
      script.onload = () => {
        if (!byId('google-button')) return;
        google.accounts.id.initialize({client_id:state.googleClientId,callback:response => finishGoogleLogin(response.credential)});
        google.accounts.id.renderButton(byId('google-button'), {theme:'filled_black',size:'large',text:'continue_with'});
      };
      if (!script.isConnected) document.head.appendChild(script); else if (window.google?.accounts?.id) script.onload();
    }
  } catch { /* City-key login stays available when the server is offline. */ }
}

window.nativeGoogleLogin = async () => {
  try {
    const result = await window.ChaosGoogleSignIn.signIn({clientId:state.googleClientId});
    await finishGoogleLogin(result.credential);
  } catch (error) { toast(error.message || 'Google sign-in was cancelled'); }
};

async function finishGoogleLogin(credential) {
  try {
    const invite_code = byId('google-invite')?.value.trim() || '';
    const result = await api('/api/auth/google', {method:'POST',body:JSON.stringify({credential,invite_code}),timeoutMs:12000});
    state.key = result.session_key;
    localStorage.setItem('chaos_key', state.key);
    localStorage.setItem('chaos_server', state.server);
    await refresh();
  } catch (error) { toast(error.message); }
}

window.setSetupMode = mode => { state.setupMode = mode; setup(); };

async function submitSetup(event) {
  event.preventDefault();
  const server = byId('server').value.trim().replace(/\/$/, '');
  if (!validServer(server)) { byId('connection-error').textContent = 'Use HTTPS for an internet server, or HTTP for a private home-network address such as http://192.168.1.190:3010.'; byId('connection-error').style.display = 'block'; return; }
  state.server = server;
  byId('connection-error').style.display = 'none';
  try {
    if (state.setupMode === 'new') {
      const result = await api('/api/register', {method:'POST', body:JSON.stringify({player:byId('player').value, city:byId('city').value, invite_code:byId('invite').value})});
      state.key = result.city_key;
      localStorage.setItem('chaos_key', state.key);
      alert('Save this city key somewhere safe before continuing:\n\n' + state.key);
    } else {
      state.key = byId('key').value.trim();
      await api('/api/me', {timeoutMs: 9000});
      localStorage.setItem('chaos_key', state.key);
    }
    localStorage.setItem('chaos_server', server);
    await refresh();
  } catch (error) {
    if (state.setupMode === 'recover') state.key = '';
    byId('connection-error').textContent = error.message;
    byId('connection-error').style.display = 'block';
    toast(error.message);
  }
}

async function refresh(quiet = false) {
  if (!state.key) { setup(); return; }
  const scroll = quiet ? window.scrollY : 0;
  const previous = state.feed[0]?.id;
  const previousTradeIds = new Set(state.trades.map(item => item.id));
  const hadCity = Boolean(state.me);
  try {
    const [mine, world, catalog, diplomacy] = await Promise.all([api('/api/me'), api('/api/cities'), api('/api/catalog'), api('/api/trades')]);
    state.me = mine.city;
    state.research = mine.research || null;
    state.dailyTagline = mine.daily_tagline || '';
    state.phoneServerUrl = mine.phone_server_url || '';
    state.feed = mine.feed;
    state.heroes = mine.heroes || [];
    state.residents = mine.residents || [];
    state.buildings = mine.buildings || [];
    state.buildingOffers = mine.building_offers || [];
    state.shop = mine.shop || [];
    state.techTree = mine.tech_tree || [];
    state.specializations = mine.specializations || [];
    state.trades = diplomacy.offers || [];
    state.tradeQuota = diplomacy;
    state.rivalHeroes = diplomacy.rival_heroes || [];
    state.cities = world.cities;
    state.battleRecords = world.battle_records || {};
    state.pairAttacks = world.pair_attacks || {};
    state.pairBattleLimit = world.pair_battle_limit || 2;
    state.events = mine.events || [];
    state.nextOffersAt = mine.next_offers_at || 0;
    render();
    if (quiet) window.scrollTo(0, scroll);
    if (quiet && hadCity && state.trades.some(item => item.status === 'pending' && item.target_id === state.me.id && !previousTradeIds.has(item.id))) toast('A rival city sent you a trade offer');
    else if (quiet && previous && state.feed[0]?.id !== previous && state.feed[0]?.kind === 'battle' && state.feed[0]?.target === state.me.name && state.feed[0]?.actor !== state.me.name) toast('A rival challenged your city. See the battle log.');
    else if (quiet && previous && state.feed[0]?.id !== previous && state.feed[0]?.kind === 'ambient') toast('Your city has new weird news');
  } catch (error) {
    if (error.message.toLowerCase().includes('key')) {
      localStorage.removeItem('chaos_key'); state.key = ''; setup();
    }
    if (!quiet) toast(error.message);
  }
}

function numberDelta(value) { return value > 0 ? `+${value}` : String(value); }
function walletCost(event) {
  const parts = [`✦ ${event.cost} Chaos Tokens`];
  if (event.shard_cost) parts.push(`◆ ${event.shard_cost} Shards`);
  if (event.core_cost) parts.push(`◈ ${event.core_cost} Core`);
  return parts.join(' · ');
}
function canAfford(event) {
  return state.me.tokens >= event.cost && state.me.shards >= event.shard_cost && state.me.cores >= event.core_cost;
}
function stat(icon, label, value, note) {
  return `<div class="stat"><span>${icon} ${label}</span><strong>${value}</strong><small>${note}</small></div>`;
}
function eventCards() {
  return state.events.filter(item => item.kind === state.eventTab).map(item => `
    <div class="card ${item.shard_cost || item.core_cost ? 'big-event' : ''}">
      <div class="event-icon">${item.icon}</div><div class="card-main">
        <h3>${esc(item.name)}</h3><p>${esc(item.tagline)}</p>
        <div class="effect-preview">Base effects: ${Object.entries(item.effects).map(([name, value]) => name === 'weirdness' ? 'gradual weirdness' : `${numberDelta(value)} ${esc(name)}`).join(' · ')}<br>Trait: ${esc(item.trait_display)}</div>
        <div class="meta"><span class="cost">${walletCost(item)}</span><button class="cast" ${canAfford(item) ? '' : 'disabled'} onclick="chooseEvent('${item.id}')">${item.kind === 'self' ? 'Unleash' : 'Attack'} →</button></div>
      </div></div>`).join('') || '<p class="empty">The city AI is preparing fresh choices. Check back in a moment.</p>';
}
function errandCards() {
  const ready = Math.floor(Date.now() / 1000) >= state.me.next_errand_at;
  return state.errands.map(item => `<div class="card desk-card"><div class="event-icon">${item.icon}</div><div class="card-main"><h3>${esc(item.name)}</h3><p>${esc(item.tagline)}</p><div class="effect-preview">${Object.entries(item.effects).map(([name, value]) => name === 'weirdness' ? 'gradual weirdness' : `${numberDelta(value)} ${esc(name)}`).join(' · ')}</div><div class="meta"><span class="cost">FREE CITY JOB</span><button class="cast" ${ready ? '' : 'disabled'} onclick="doErrand('${item.id}')">Do this →</button></div></div></div>`).join('') || '<p class="empty">The city AI is preparing fresh jobs. Check back in a moment.</p>';
}

function changeSection(title, values) {
  const items = Object.entries(values || {}).filter(([, value]) => value && value.delta !== 0);
  if (!items.length) return '';
  return `<div class="change-group"><div class="change-heading">${esc(title)}</div>${items.map(([name, value]) => `<div class="change-row"><span>${esc(name.replaceAll('_', ' '))}</span><span class="numbers">${value.before} → ${value.after}</span><b class="${value.delta >= 0 ? 'positive' : 'negative'}">${numberDelta(value.delta)}</b></div>`).join('')}</div>`;
}
function changeRows(changes) {
  if (!changes || !Object.keys(changes).length) return '<p class="empty">Exact before-and-after numbers were not recorded for this older event.</p>';
  return `<div class="changes">${changeSection(`${changes.target_city || 'City'} stats`, changes.stats)}${changeSection('Personality traits', changes.traits)}${changeSection(`${changes.attacker_city || 'Attacker'} traits`, changes.attacker_traits)}${changeSection(`${changes.defender_city || 'Defender'} traits`, changes.defender_traits)}${changeSection('Special citizens', changes.citizens)}${changeSection('Construction', changes.buildings)}${changeSection(`${changes.wallet_city || 'Mayor'} wallet`, changes.wallet)}${changeSection(`${changes.sender_name || 'Sender'} Wealth`, changes.sender_wallet)}${changeSection(`${changes.target_name || 'Receiver'} Wealth`, changes.target_wallet)}</div>`;
}

function battleSamples(samples, chance, changes = {}) {
  if (!samples?.length) return '';
  const duels = changes.race_duels || [];
  const hero = changes.hero_power || {};
  const traitBuff = changes.hero_trait_bonus || {};
  return `<details class="battle-samples"><summary>See all ${samples.length} traits and fighters${Number.isFinite(chance) ? ` · attacker chance ${chance}%` : ''}</summary><div class="sample-heading"><span>Trait</span><span>Attacker</span><span>Defender</span></div>${samples.map(item => `<div class="sample-row"><span>${esc(item.name)}</span><b>${item.attacker}</b><b>${item.defender}</b></div>`).join('')}${duels.length ? `<h4>Resident race duels</h4><p>Preferred enemy match deals 2 damage instead of 1.</p>${duels.map(item => `<div class="duel-row"><span>${esc(item.attacker)} (${esc(item.attacker_race)}) <b>${item.attacker_damage}</b></span><span>${esc(item.defender)} (${esc(item.defender_race)}) <b>${item.defender_damage}</b></span></div>`).join('')}<p>Equipped hero team power: ${hero.attacker || 0} vs ${hero.defender || 0}. Hero trait bonuses: ${traitBuff.attacker || 0} vs ${traitBuff.defender || 0}.</p>` : ''}</details>`;
}

function feedItems() {
  const filtered = state.feed.filter(item => state.logTab === 'all' || item.kind === state.logTab).slice(0,10);
  if (!filtered.length) return '<p class="empty">No entries here yet. The city AI will have something to say soon.</p>';
  return filtered.map(item => `<div class="feed-item"><div class="feed-icon">${item.kind === 'hero' ? '🧑‍🚀' : item.icon}</div><div class="feed-content"><div class="feed-title">${esc(item.event)} ${item.kind === 'battle' ? (item.success ? '· attacker won' : '· defender won') : item.success ? '' : '· misfired'} <span class="chip">${item.kind === 'ambient' ? 'CITY AI' : item.kind === 'hero' ? 'NEW CITIZEN' : item.kind === 'errand' ? 'PAST CITY JOB' : item.kind === 'building' ? 'CONSTRUCTION' : item.kind === 'battle' ? 'TRAIT BATTLE' : item.kind === 'trade' ? 'CITY TRADE' : 'PLAYER EVENT'}</span></div><div class="feed-story">${esc(item.story)}</div><div class="muted" style="margin-top:6px">${esc(item.actor)} → ${esc(item.target)} · ${new Date(item.created_at * 1000).toLocaleString()}</div>${item.kind === 'hero' ? '' : `<details class="change-details"><summary>See exact changes</summary>${changeRows(item.changes)}</details>`}${item.kind === 'battle' ? battleSamples(item.changes?.sampled_traits, item.changes?.win_chance, item.changes) : ''}</div></div>`).join('');
}
function featuredEvent() {
  const rewards = state.feed.map(item => {
    const changes = item.changes || {};
    const sections = ['stats', 'traits', 'wallet'];
    if (item.kind === 'battle') sections.push(item.success ? 'attacker_traits' : 'defender_traits');
    const gains = sections.flatMap(section => Object.entries(changes[section] || {}).filter(([, value]) => Number(value?.delta) > 0).map(([name,value]) => ({name, amount:Number(value.delta)})));
    if (changes.citizens && Object.values(changes.citizens).some(value => value.after === state.me.name)) gains.push({name:'special citizen',amount:10});
    const score = gains.reduce((sum, gain) => sum + gain.amount * (['shards','cores','special citizen'].includes(gain.name) ? 10 : 1), 0);
    return {item,gains,score};
  }).filter(entry => entry.score > 0).sort((a,b) => b.score-a.score)[0];
  if (!rewards) return '';
  const {item,gains} = rewards;
  return `<div class="surface featured-event"><span class="eyebrow">🏆 BEST RECENT REWARD</span><h2>${esc(item.event)}</h2><p>${esc(item.story)}</p><div class="reward-chips">${gains.sort((a,b) => b.amount-a.amount).slice(0,5).map(gain => `<span>+${gain.amount} ${esc(gain.name.replaceAll('_',' '))}</span>`).join('')}</div></div>`;
}
function traitRows() {
  const search = state.traitSearch.toLowerCase();
  const categories = state.me.trait_categories || {};
  const rows = Object.entries(state.me.traits).filter(([name]) => name.toLowerCase().includes(search) && (state.traitCategory === 'All' || categories[name] === state.traitCategory));
  rows.sort((a,b) => state.traitSort === 'az' ? a[0].localeCompare(b[0]) : state.traitSort === 'za' ? b[0].localeCompare(a[0]) : state.traitSort === 'low' ? a[1]-b[1] || a[0].localeCompare(b[0]) : b[1]-a[1] || a[0].localeCompare(b[0]));
  const draw = items => items.map(([name,value]) => `<div class="trait"><span>${esc(name)}</span><div class="bar"><i style="width:${value}%"></i></div><b>${value}</b></div>`).join('');
  if (!state.groupTraits) return rows.length ? `<div class="traits flat-traits">${draw(rows)}</div>` : '<p class="empty">No matching traits.</p>';
  const groups = state.traitCategory === 'All' ? [...new Set(Object.values(categories))] : [state.traitCategory];
  return groups.map(group => { const items = rows.filter(([name]) => categories[name] === group); return items.length ? `<details class="trait-group" ${search || state.traitCategory !== 'All' ? 'open' : ''}><summary>${esc(group)} <small>${items.length} traits</small></summary><div class="traits">${draw(items)}</div></details>` : ''; }).join('') || '<p class="empty">No matching traits.</p>';
}

function heroCards() {
  return Array.from({length: state.me.hero_slots}, (_, slot) => {
    const hero = state.heroes.find(item => item.slot === slot);
    return `<div class="hero-card ${hero ? 'tier-' + esc(hero.tier) : 'empty-slot'}"><span class="rarity">SLOT ${slot+1}${hero ? ' · ' + rarityLabel(hero.tier).toUpperCase() : ''}</span><h3>${hero ? esc(hero.name) : 'Vacant hero chair'}</h3><p>${hero ? esc(hero.title) : 'Waiting for an extraordinary citizen.'}</p>${hero ? `<span class="muted">${esc(hero.race)} · +${1 + ['white','green','blue','purple','orange'].indexOf(hero.tier)} ${esc(hero.specialty)} each city day · Battle power and defense · Ally: ${esc(hero.ally_race)}</span>` : ''}<button class="secondary" onclick="showRoster(${slot})">${hero ? 'Change citizen' : 'Choose citizen'}</button></div>`;
  }).join('');
}

function shopCards() {
  return state.shop.map(item => `<div class="card"><div class="event-icon">${item.icon}</div><div class="card-main"><h3>${esc(item.name)} <small>Level ${item.level}/${item.max_level}</small></h3><p>${esc(item.effect)}</p><div class="meta"><span class="cost">💵 ${item.cost} Cash · Tech ${item.tech}</span><button class="cast" ${!item.unlocked || item.level >= item.max_level || state.me.cash < item.cost ? 'disabled' : ''} onclick="buyUpgrade('${item.id}')">${item.level >= item.max_level ? 'Complete' : item.unlocked ? 'Upgrade →' : 'Locked'}</button></div></div></div>`).join('');
}

function researchPercent() {
  if (!state.research) return 0;
  return Math.max(0, Math.min(100, 100 * (Date.now()/1000 - state.research.started_at) / (state.research.ready_at - state.research.started_at)));
}
function techTreeView() {
  const known = new Set(state.me.tech_nodes);
  const lookup = Object.fromEntries(state.techTree.map(node => [node.id,node]));
  const visible = state.techTree.filter(node => node.branch === state.techBranch || node.id === 'city_charter').sort((a,b) => a.y-b.y || a.x-b.x);
  const nodes = visible.map(node => {
    const owned = known.has(node.id), researching = state.research?.node_id === node.id;
    const ready = !state.research && node.requires.every(id => known.has(id)) && state.me.tech >= node.tech && state.me.cash >= node.cost;
    const status = researching ? 'Researching' : owned ? 'Researched' : ready ? 'Ready to research' : 'Locked';
    const requirements = node.requires.map(id => lookup[id]?.name || id).join(', ') || 'None';
    return `<div class="tech-lane-row"><button class="tech-dot ${esc(node.branch.toLowerCase())} ${owned ? 'owned' : ready ? 'ready' : 'locked'} ${researching ? 'researching' : ''}" aria-label="${esc(node.name)}: ${esc(node.effect)}. ${status}" onclick="showTechNode('${node.id}')"><span class="dot-core"></span><span class="tech-tooltip"><b>${esc(node.name)}</b><small>Tech ${node.tech} · 💵 ${node.cost} Cash</small><span>${esc(node.effect)}</span><small>Needs: ${esc(requirements)}</small><em>${status}${researching ? ` · <span data-countdown="${state.research.ready_at}">${clock(state.research.ready_at)}</span>` : ''}</em>${researching ? `<span class="mini-progress"><i data-research-progress style="width:${researchPercent()}%"></i></span>` : ''}</span></button><div class="tech-lane-label"><strong>${esc(node.name)}</strong><small>${esc(node.effect)}</small><span>${status}${researching ? ` · <span data-countdown="${state.research.ready_at}">${clock(state.research.ready_at)}</span>` : ''}</span></div></div>`;
  }).join('');
  return `<div class="tree-legend"><span>● Researched</span><span>◉ Available</span><span>○ Locked</span><span>${known.size} / ${state.techTree.length} nodes</span></div><div class="tree-jumps">${['Commerce','Science','Food','Culture','Construction'].map(branch => `<button class="secondary ${state.techBranch === branch ? 'selected' : ''}" onclick="jumpTech('${branch}')">${branch}</button>`).join('')}</div><p class="progress-note">Pick a branch, then tap a dot for its requirements and timer. Completed dots unlock connected research.</p>${state.research ? `<div class="surface research-active"><b>🔬 Researching ${esc(lookup[state.research.node_id]?.name || state.research.node_id)}</b><span data-countdown="${state.research.ready_at}">${clock(state.research.ready_at)}</span><div class="progress"><i data-research-progress style="width:${researchPercent()}%"></i></div></div>` : ''}<div class="tech-lane">${nodes}</div><div class="surface tech-inspector" id="tech-inspector"></div>`;
}

function buildingPerk(item) {
  const bonuses = Object.entries(item.daily || {}).map(([name, amount]) => `+${amount} ${name} each city day`);
  if (item.defense) bonuses.push(`+${item.defense} PvP defense`);
  return bonuses.join(' · ');
}

function specializationCards() {
  const city = state.me;
  const onCooldown = city.specialization && Date.now() / 1000 < city.specialization_next_change_at;
  return state.specializations.map(item => {
    const selected = city.specialization === item.id;
    const disabled = selected || onCooldown || (city.specialization && city.cash < 25);
    return `<div class="class-card ${selected ? 'selected' : ''}"><span class="class-icon">${item.icon}</span><div><h3>${esc(item.name)}</h3><p>${esc(item.effect)}</p></div><button class="secondary" ${disabled ? 'disabled' : ''} onclick="chooseSpecialization('${item.id}')">${selected ? 'My class' : city.specialization ? 'Choose · 25 Cash' : 'Choose · Free'}</button></div>`;
  }).join('');
}

function buildingCards() {
  const slotsFull = state.buildings.length >= state.me.building_slots;
  const built = state.buildings.map(item => `<div class="card building-card built"><div class="event-icon">${item.icon}</div><div class="card-main"><span class="chip">BUILT</span><h3>${esc(item.name)}</h3><p>${esc(item.description)}</p><div class="effect-preview">${esc(buildingPerk(item))}</div></div></div>`).join('');
  const plans = state.buildingOffers.map(item => `<div class="card building-card"><div class="event-icon">${item.icon}</div><div class="card-main"><h3>${esc(item.name)}</h3><p>${esc(item.description)}</p><div class="effect-preview">${esc(buildingPerk(item))}</div><div class="meta"><span class="cost">💰 ${item.cost} Wealth</span><button class="cast" ${slotsFull || state.me.wealth < item.cost ? 'disabled' : ''} onclick="buildCity('${item.id}')">Construct →</button></div></div></div>`).join('');
  return built + plans || '<p class="empty">The city AI is sketching building plans.</p>';
}

function tradeCards() {
  if (!state.trades.length) return '<p class="empty">No offers yet. Invite a rival city to sign a very official napkin.</p>';
  return state.trades.map(item => {
    const incoming = item.target_id === state.me.id;
    const first = [item.offer_hero_name && `🧑‍🚀 ${item.offer_hero_name}`, item.offer_wealth && `💰 ${item.offer_wealth} Wealth`].filter(Boolean).join(' + ') || 'nothing';
    const second = [item.request_hero_name && `🧑‍🚀 ${item.request_hero_name}`, item.request_wealth && `💰 ${item.request_wealth} Wealth`].filter(Boolean).join(' + ') || 'nothing';
    return `<div class="trade-card"><div><span class="chip">${esc(item.status.toUpperCase())}</span><h3>${esc(item.sender_name)} ↔ ${esc(item.target_name)}</h3><p>${esc(item.sender_name)} gives <b>${esc(first)}</b><br>${esc(item.target_name)} gives <b>${esc(second)}</b></p><small>${item.status === 'pending' ? `Expires in <span data-countdown="${item.expires_at}">${clock(item.expires_at)}</span>` : 'Offer closed'}</small></div>${item.status === 'pending' ? `<div class="trade-actions">${incoming ? `<button class="primary" onclick="respondTrade('${item.id}','accept')">Accept</button>` : ''}<button class="secondary" onclick="respondTrade('${item.id}','close')">${incoming ? 'Decline' : 'Cancel'}</button></div>` : ''}</div>`;
  }).join('');
}

function glossaryView() {
  const sections = [
    ['Getting started', 'Your mayor owns one city. Start with City to see your supplies, choose a specialization, and watch your city grow. Use Chaos Tokens in Chaos for events. Visit Research when you have Cash and enough Tech. Citizens holds your equipped special people. Battles and Trades connect your city to other mayors.'],
    ['Citizens', 'The population living in your city. Food shortages can make it shrink; good morale helps it grow. Special citizens are named heroes in limited equipment slots.'],
    ['Wealth', 'A city resource used to build special buildings and start battles. Each point also produces 0.02 Cash per hour. Wealth and Cash are separate.'],
    ['Cash', 'Money earned each hour from base income, Wealth, research, and upgrades. Spend Cash on research nodes, shop upgrades, and some class changes.'],
    ['Food', 'Your city eats this. A shortage reduces the population. Tech, buildings, events, and upgrades can help food production.'],
    ['Morale', 'How content citizens are, on a 0–100 scale. Higher morale helps population growth. Events can raise or lower it.'],
    ['Tech', 'Your city’s research score. It opens research nodes and shop upgrades; the nodes still cost Cash. Tech also helps daily Food production.'],
    ['Chaos Tokens', 'You earn one each hour, up to the cap shown on City. Spend them on the rotating event choices. The server decides the actual result.'],
    ['Anomaly Shards and Reality Cores', 'Rare currencies earned from city incidents. Higher weirdness unlocks more powerful events that may use them.'],
    ['Weirdness and reality drift', 'The city’s unusual side unfolds across 90 real days. The progress bar shows when its next level can unlock. Its skyline and colors move through one of 72 visual paths.'],
    ['Traits', 'Your city has 320 individual personality scores in ten groups. Search and sort them in Traits. Battles randomly sample twenty, so a younger city can challenge an older one.'],
    ['Research and upgrades', 'Research follows connected dots. Tap a dot to see requirements and its exact effect. Shop upgrades spend Cash and can raise hourly growth or add citizen and building slots.'],
    ['Special citizens and buildings', 'Events can bring in special citizens. Only equipped citizens provide daily stat bonuses, matching trait bonuses in battle, team power, and defense. A hero gets an extra team bonus when their ally race fights alongside them. Each city starts with one citizen slot and one building plot; the shop can unlock more.'],
    ['Battles', 'A challenge costs Wealth. Twenty random traits and five resident race duels affect the odds, limited to 35–65%. A resident deals double damage to their preferred enemy race. The winner moves a few trait points and sometimes recruits one of the loser’s special citizens. Buildings and city specialization may add defense. A city can receive six hostile events in 24 hours, counting both battles and Chaos Token attacks.'],
    ['Trades', 'Offer Wealth or a special citizen to another mayor. They must accept before anything moves. Offers expire after 48 hours. You can send ten proposals per 24 hours, at most four to one rival; canceled offers still count.'],
  ];
  return `<div class="section-head"><div><h2>Getting started & glossary</h2><p>A plain language guide to the city and its rules.</p></div></div><div class="glossary-list">${sections.map(([title,body],index) => `<details class="surface" ${index===0 ? 'open' : ''}><summary>${esc(title)}</summary><p>${esc(body)}</p></details>`).join('')}</div>`;
}

function render() {
  const city = state.me;
  const stage = realityStage(city.weirdness);
  document.body.dataset.realityStage = String(stage);
  const pathName = cityPath(city);
  const rivals = state.cities.filter(item => item.id !== city.id);
  app.innerHTML = `<div class="shell">
    <header class="brand"><div class="logo"><div class="logo-mark">⚡</div>Chaos Cities</div><span class="pill">THE CITY IS LISTENING</span></header>
    <nav class="main-nav" aria-label="Game pages">${[['city','🏙️ City'],['chaos','✨ Chaos'],['citizens','🧑‍🚀 Citizens'],['build','🏗️ Buildings'],['research','🧬 Research'],['battles','⚔️ Battles'],['trades','🤝 Trades'],['log','📜 Log'],['traits','🗂️ Traits'],['glossary','📖 Help']].map(([id,label]) => `<button class="tab ${state.page === id ? 'active' : ''}" onclick="setPage('${id}')">${label}</button>`).join('')}</nav>
    <div class="quick-stats" aria-label="City resources">${[['👥','Citizens',city.population],['💰','Wealth',city.wealth],['🥫','Food',city.food],['😊','Morale',city.morale],['🛸','Tech',city.tech]].map(([icon,label,value]) => `<div title="${label}"><span>${icon} ${label}</span><strong>${value}</strong></div>`).join('')}</div>
    ${state.page === 'city' ? `
    <section class="hero"><div class="city-scene" aria-hidden="true"><div class="scene-sun"></div><div class="scene-cloud"></div><div class="scene-portal"></div><div class="scene-ground"></div><div class="scene-building one"></div><div class="scene-building two"></div><div class="scene-building three"></div><div class="scene-eye"></div></div><span class="eyebrow">${esc(city.owner_name)}'S GLORIOUS DISASTER</span><h1>${esc(city.name)}</h1><p>${esc(state.dailyTagline)}</p><button class="secondary rename-button" onclick="renameCity()">Rename city</button><span class="reality-label">${esc(pathName)} · Skyline ${stage + 1}/12 · ${esc(REALITY_STAGES[stage])}</span></section>
    ${featuredEvent()}
    <div class="currency-grid">
      <div class="wallet"><span>✦ CHAOS TOKENS</span><strong>${city.tokens}<small> / ${city.max_tokens}</small></strong><p>+1 each hour · next in <span data-countdown="${city.next_tokens_at}">${clock(city.next_tokens_at)}</span></p></div>
      <div class="wallet cash"><span>💵 CASH</span><strong>${city.cash.toFixed(2)}</strong><p>+${city.cash_per_hour.toFixed(3)} each hour from base income and Wealth</p></div>
      <div class="wallet shard"><span>◆ ANOMALY SHARDS</span><strong>${city.shards}</strong><p>Rare City AI incidents</p></div>
      <div class="wallet core"><span>◈ REALITY CORES</span><strong>${city.cores}</strong><p>Very rare later City AI incidents</p></div>
    </div>
    <div class="grid">${stat('👥','Citizens',city.population,'Can grow or shrink')}${stat('💰','Wealth',city.wealth,'City funds')}${stat('🥫','Food',city.food,'Feeds citizens')}${stat('😊','Morale',city.morale,'Out of 100')}${stat('🛸','Tech',city.tech,'Boosts food')}${stat('🌀','Weirdness',city.weirdness,'Current reality drift')}${stat('🧬','Traits',320,'All distinct')}${stat('🏙️','Rivals',rivals.length,'Cities in range')}</div>
    <details class="surface stat-guide"><summary>What do my city stats do?</summary><div class="guide-grid"><p><b>🥫 Food</b> feeds citizens. A shortage shrinks the population.</p><p><b>😊 Morale</b> helps population grow and reflects daily city life.</p><p><b>💰 Wealth</b> earns Cash at 0.02 per Wealth each hour and also pays for construction and battles.</p><p><b>🛸 Tech</b> unlocks upgrades and branches of the tech tree. It also adds daily Food.</p></div></details>
    <div class="section-head"><div><h2>City specialization</h2><p>Choose your city's first calling for free. You can switch later for 25 Cash, once per day.</p></div>${city.specialization ? `<span class="chip">${esc(state.specializations.find(item => item.id === city.specialization)?.name || 'Chosen')}</span>` : '<span class="chip">CHOOSE A CLASS</span>'}</div>
    ${city.specialization && Date.now() / 1000 < city.specialization_next_change_at ? `<p class="progress-note">Your city can change its calling in <span data-countdown="${city.specialization_next_change_at}">${clock(city.specialization_next_change_at)}</span>.</p>` : ''}
    <div class="class-grid">${specializationCards()}</div>
    <div class="surface growth-summary"><strong>Passive growth starts at +0.001 per hour</strong><p>Each stat keeps its fractional progress until it reaches a whole point. Research and shop upgrades increase the rate.</p>${['food','morale','tech','wealth'].map(stat => `<span>${esc(stat)}: ${(city.growth_bank[stat] || 0).toFixed(3)} saved toward the next point</span>`).join('')}</div>
    <div class="section-head"><div><h2>Reality drift</h2><p>Stranger events unlock gradually over ${city.drift.days_total} real days.</p></div><span class="chip">DAY ${city.drift.day} / ${city.drift.days_total}</span></div>
    <div class="surface"><div class="drift-top"><strong>Weirdness ${city.weirdness} / ${city.drift.cap} available now</strong><span>Next increase in <span data-countdown="${city.drift.next_ramp_at}">${clock(city.drift.next_ramp_at)}</span></span></div><div class="progress"><i style="width:${city.drift.progress}%"></i></div><p class="progress-note">${city.drift.progress}% of the 90-day journey · Full chaos ${new Date(city.drift.full_ramp_at * 1000).toLocaleDateString()}</p></div>
    ` : ''}
    ${state.page === 'chaos' ? `
    <div class="section-head"><div><h2>The chaos menu</h2><p>Your local AI prepares one-use choices. Used choices disappear and fresh ones arrive soon. Full refresh in <span data-countdown="${state.nextOffersAt}">${clock(state.nextOffersAt)}</span>.</p></div><div class="tabs"><button class="tab ${state.eventTab === 'self' ? 'active' : ''}" onclick="setEventTab('self')">✨ My city</button><button class="tab ${state.eventTab === 'attack' ? 'active' : ''}" onclick="setEventTab('attack')">💥 Attack</button></div></div>
    <div class="cards">${eventCards()}</div>
    ` : ''}
    ${state.page === 'citizens' ? `
    <div class="section-head"><div><h2>Special citizens</h2><p>Heroes arrive through city events. Equip up to ${city.hero_slots}; only equipped heroes give daily bonuses.</p></div><span class="chip">${state.heroes.filter(hero => hero.slot !== null).length} / ${city.hero_slots} SLOTS</span></div>
    <div class="hero-roster">${heroCards()}</div>
    <p class="progress-note">${state.heroes.filter(hero => hero.slot === null).length} citizens in reserve. ${city.hero_slots < 3 ? 'Buy more chairs in Research.' : 'All hero chairs unlocked.'}</p><button class="secondary" onclick="showRoster()">Manage all citizens</button>
    <details class="surface residents-list"><summary>Meet all ${state.residents.length} residents</summary><p>Each resident has a race and a preferred enemy. In battle, a matching opponent takes double damage. An equipped hero gains an ally bonus when their ally race joins the fight.</p><div class="resident-grid">${state.residents.map(person => `<div><b>${esc(person.name)}</b><small>${esc(person.race)} · beats ${esc(person.preferred_enemy)}</small></div>`).join('')}</div></details>
    ` : ''}
    ${state.page === 'build' ? `
    <div class="section-head"><div><h2>Special buildings</h2><p>Spend Wealth to shape your city's daily life. The local AI gives each plan its own identity.</p></div><span class="chip">${state.buildings.length} / ${city.building_slots} BUILT</span></div>
    <div class="cards building-list">${buildingCards()}</div>
    <p class="progress-note">Every city starts with one plot. Buy more through the Research shop.</p>
    ` : ''}
    ${state.page === 'research' ? `
    <div class="section-head"><div><h2>The ridiculous tech tree</h2><p>Explore ${state.techTree.length} connected research dots. Your Tech score opens paths; Cash pays for them.</p></div><span class="chip">🛸 ${city.tech} Tech · 💵 ${city.cash.toFixed(2)} Cash</span></div>
    ${techTreeView()}
    <div class="section-head"><div><h2>Upgrade shop</h2><p>Cash comes from Wealth every hour. Upgrades increase passive growth or buy more slots.</p></div></div>
    <div class="cards">${shopCards()}</div>
    ` : ''}
    ${state.page === 'battles' ? `
    <div class="section-head"><div><h2>Other cities</h2><p>Friends on this server can send chaos back. Battle records cover the last 30 days.</p></div><span class="chip">Your record: ${state.battleRecords[city.id]?.wins || 0} W · ${state.battleRecords[city.id]?.losses || 0} L</span></div>
    <div class="surface">${rivals.length ? rivals.map(item => `<div class="row"><div><div class="city-name">${esc(item.name)}</div><div class="muted">Mayor ${esc(item.owner_name)} · ${item.population} citizens · ${state.battleRecords[item.id]?.wins || 0} W / ${state.battleRecords[item.id]?.losses || 0} L · Your attacks ${state.pairAttacks[item.id] || 0}/${state.pairBattleLimit} · Incoming ${item.incoming_attacks_24h || 0}/${item.incoming_attack_limit || 6}</div></div><span class="chip">${Date.now()/1000 < item.battle_shield_until ? `Protected ${clock(item.battle_shield_until)}` : !attackable(item) ? 'Daily defense limit' : (state.pairAttacks[item.id] || 0) >= state.pairBattleLimit ? 'Your daily limit' : `🌀 ${item.weirdness}`}</span></div>`).join('') : '<p class="empty">No rivals yet. Invite a friend with your server address.</p>'}</div>
    <div class="section-head"><div><h2>Twenty-trait battles</h2><p>Twenty random traits shape a unique AI-written encounter. Either city can win regardless of overall level. Winners take trait points and might recruit a rival's special citizen.</p></div><span class="chip" id="battle-timer">${clock(city.next_battle_at) === 'ready' ? 'READY NOW' : 'READY IN ' + clock(city.next_battle_at)}</span></div>
    <div class="surface battle-panel"><div><strong>⚔️ Challenge another city</strong><p class="muted">Costs ${city.battle_cost} Wealth. Challengers rest 4 hours; new cities and recent defenders get 1 hour of protection. You can challenge the same city twice per 24 hours. A city can receive at most ${city.incoming_attack_limit || 6} hostile events in 24 hours.</p></div><button class="cast" onclick="startBattle()" ${clock(city.next_battle_at) !== 'ready' || city.wealth < city.battle_cost || !rivals.some(item => attackable(item) && (state.pairAttacks[item.id] || 0) < state.pairBattleLimit) ? 'disabled' : ''}>Choose a rival →</button></div>
    ` : ''}
    ${state.page === 'trades' ? `
    <div class="section-head"><div><h2>City-to-city trades</h2><p>Propose a citizen swap, a Wealth exchange, or a gift. The other mayor must accept before anything moves.</p></div><button class="cast" onclick="showTradeProposal()" ${rivals.some(item => (state.tradeQuota.pair_sent_today?.[item.id] || 0) < (state.tradeQuota.pair_daily_limit || 4)) && (state.tradeQuota.sent_today || 0) < (state.tradeQuota.daily_limit || 10) ? '' : 'disabled'}>Propose a trade →</button></div>
    <div class="surface"><p class="progress-note">Sent ${state.tradeQuota.sent_today || 0}/${state.tradeQuota.daily_limit || 10} proposals in the past 24 hours; up to ${state.tradeQuota.pair_daily_limit || 4} per rival. Up to three may be open at once. Offers expire after 48 hours. Citizens moving to another city enter its reserve roster.</p><div class="trade-list">${tradeCards()}</div></div>
    ` : ''}
    ${state.page === 'log' ? `
    <div class="section-head"><div><h2>City event log</h2><p>Ten recent entries per category. The local AI also picks weird incidents between player events.</p></div><button class="link" onclick="refresh()">Refresh ↻</button></div>
    <div class="tabs log-tabs"><button class="tab ${state.logTab === 'all' ? 'active' : ''}" onclick="setLogTab('all')">All</button><button class="tab ${state.logTab === 'ambient' ? 'active' : ''}" onclick="setLogTab('ambient')">City AI</button><button class="tab ${state.logTab === 'hero' ? 'active' : ''}" onclick="setLogTab('hero')">Citizens</button><button class="tab ${state.logTab === 'cast' ? 'active' : ''}" onclick="setLogTab('cast')">Events</button><button class="tab ${state.logTab === 'battle' ? 'active' : ''}" onclick="setLogTab('battle')">Battles</button><button class="tab ${state.logTab === 'trade' ? 'active' : ''}" onclick="setLogTab('trade')">Trades</button></div>
    <div class="surface">${feedItems()}</div>
    ` : ''}
    ${state.page === 'traits' ? `
    <div class="section-head"><div><h2>Personality atlas</h2><p>320 unique traits. Group them or show one sortable list.</p></div></div>
    <div class="surface"><div class="trait-controls"><input class="input" placeholder="Search traits…" id="trait-search" value="${esc(state.traitSearch)}"><select id="trait-category" aria-label="Trait category"><option>All</option>${[...new Set(Object.values(city.trait_categories))].map(group => `<option ${state.traitCategory === group ? 'selected' : ''}>${esc(group)}</option>`).join('')}</select><select id="trait-sort" aria-label="Sort traits"><option value="high" ${state.traitSort === 'high' ? 'selected' : ''}>Highest first</option><option value="low" ${state.traitSort === 'low' ? 'selected' : ''}>Lowest first</option><option value="az" ${state.traitSort === 'az' ? 'selected' : ''}>Name A–Z</option><option value="za" ${state.traitSort === 'za' ? 'selected' : ''}>Name Z–A</option></select><label class="group-toggle"><input type="checkbox" id="group-traits" ${state.groupTraits ? 'checked' : ''}> Group traits</label></div><div id="trait-list">${traitRows()}</div></div>
    ` : ''}
    ${state.page === 'glossary' ? glossaryView() : ''}
    <footer class="footer"><span>Local AI chooses city incidents and speaks as the city. The server keeps effects bounded.</span><a class="link" href="${esc(state.server.replace(/\/$/, ''))}/board" target="_blank" rel="noopener">Project board</a><button class="link" onclick="showAccount()">My city key & server</button></footer>
  </div>`;
  if (state.page === 'traits') {
    byId('trait-search').oninput = event => { state.traitSearch = event.target.value; byId('trait-list').innerHTML = traitRows(); };
    byId('trait-category').onchange = event => { state.traitCategory = event.target.value; byId('trait-list').innerHTML = traitRows(); };
    byId('trait-sort').onchange = event => { state.traitSort = event.target.value; byId('trait-list').innerHTML = traitRows(); };
    byId('group-traits').onchange = event => { state.groupTraits = event.target.checked; localStorage.setItem('chaos_group_traits', String(state.groupTraits)); byId('trait-list').innerHTML = traitRows(); };
  }
  if (state.page === 'research') showTechNode(state.selectedTech);
}

window.setEventTab = value => { state.eventTab = value; render(); };
window.setLogTab = value => { state.logTab = value; render(); };
window.setPage = value => { state.page = value; render(); window.scrollTo(0,0); };
window.renameCity = () => {
  const name = prompt('New city name (3–28 letters, numbers, spaces, periods, apostrophes or hyphens):', state.me.name);
  if (name === null || name.trim() === state.me.name) return;
  api('/api/city/rename', {method:'POST', body:JSON.stringify({name:name.trim()})}).then(() => refresh(true)).then(() => toast('Your city has a new name')).catch(error => toast(error.message));
};
window.jumpTech = branch => {
  state.techBranch = branch;
  const branchNodes = state.techTree.filter(node => node.branch === branch).sort((a,b) => a.y-b.y);
  state.selectedTech = branchNodes.find(node => !state.me.tech_nodes.includes(node.id))?.id || branchNodes[0]?.id || 'city_charter';
  render();
};
window.chooseSpecialization = id => {
  const option = state.specializations.find(item => item.id === id);
  if (!option || !confirm(`Choose ${option.name}${state.me.specialization ? ' for 25 Cash' : ' for free'}?`)) return;
  api('/api/specializations', {method:'POST', body:JSON.stringify({specialization_id:id})}).then(() => refresh(true)).catch(error => toast(error.message));
};
window.toggleTraits = () => { state.traitsOpen = !state.traitsOpen; render(); };
window.equipHero = async (id, value) => {
  try { await api('/api/heroes/equip', {method:'POST', body:JSON.stringify({hero_id:id,slot:value === '' ? null : Number(value)})}); await refresh(true); toast('Hero slots updated'); }
  catch (error) { toast(error.message); await refresh(true); }
};

window.showRoster = (slot = 0) => {
  const overlay = document.createElement('div');
  overlay.className = 'modal-backdrop';
  overlay.innerHTML = `<div class="modal result-modal"><h2>Special citizens</h2><p>Choose who occupies each purchased chair. Everyone else waits in reserve.</p>${state.heroes.length ? state.heroes.map(hero => `<div class="roster-row tier-${esc(hero.tier)}"><div><span class="rarity">${rarityLabel(hero.tier).toUpperCase()}</span><strong>${esc(hero.name)}</strong><small>${esc(hero.title)} · +${1 + ['white','green','blue','purple','orange'].indexOf(hero.tier)} ${esc(hero.specialty)} daily</small></div><select aria-label="Equipment slot for ${esc(hero.name)}" onchange="equipHero('${hero.id}',this.value);this.closest('.modal-backdrop').remove()"><option value="" ${hero.slot === null ? 'selected' : ''}>Reserve</option>${Array.from({length:state.me.hero_slots}, (_, index) => `<option value="${index}" ${hero.slot === index ? 'selected' : ''}>Slot ${index+1}</option>`).join('')}</select></div>`).join('') : '<p class="empty">No citizens have joined yet. City AI incidents may introduce one.</p>'}<button class="secondary" id="close-roster">Close</button></div>`;
  document.body.appendChild(overlay);
  byId('close-roster').onclick = () => overlay.remove();
};

window.researchNode = id => {
  const node = state.techTree.find(item => item.id === id);
  const owned = new Set(state.me.tech_nodes);
  if (owned.has(id)) { toast('Already researched'); return; }
  if (state.me.tech < node.tech || !node.requires.every(item => owned.has(item))) { toast(`Need Tech ${node.tech} and earlier connected research`); return; }
  if (state.me.cash < node.cost) { toast('Not enough Cash'); return; }
  api('/api/research', {method:'POST', body:JSON.stringify({node_id:id})}).then(() => refresh(true)).catch(error => toast(error.message));
};

window.showTechNode = id => {
  const node = state.techTree.find(item => item.id === id);
  if (!node) return;
  state.selectedTech = id;
  const names = Object.fromEntries(state.techTree.map(item => [item.id, item.name]));
  const owned = new Set(state.me.tech_nodes);
  const needs = node.requires.map(item => names[item] || item);
  const prerequisites = node.requires.every(item => owned.has(item));
  const researching = state.research?.node_id === id;
  const available = !state.research && !owned.has(id) && prerequisites && state.me.tech >= node.tech && state.me.cash >= node.cost;
  const panel = byId('tech-inspector');
  if (!panel) return;
  panel.innerHTML = `<span class="eyebrow">${esc(node.branch.toUpperCase())} RESEARCH</span><h3>${esc(node.name)}</h3><p>${esc(node.effect)}</p><small>Requires ${needs.length ? esc(needs.join(', ')) : 'no earlier research'} · Tech ${node.tech} · 💵 ${node.cost} Cash</small><p>${researching ? `Researching · <span data-countdown="${state.research.ready_at}">${clock(state.research.ready_at)}</span> left` : owned.has(id) ? 'Already researched' : state.research ? 'Finish your current research first.' : available ? 'Ready to research' : !prerequisites ? 'Research the connected dots first.' : state.me.tech < node.tech ? `Needs ${node.tech} Tech; you have ${state.me.tech}.` : `Needs ${node.cost} Cash; you have ${state.me.cash.toFixed(2)}.`}</p>${researching ? `<div class="progress"><i data-research-progress style="width:${researchPercent()}%"></i></div>` : ''}<button class="primary" ${available ? '' : 'disabled'} onclick="researchNode('${id}')">Start research</button>`;
};

window.buyUpgrade = id => {
  const item = state.shop.find(value => value.id === id);
  if (!item || !confirm(`Buy ${item.name} level ${item.level+1} for ${item.cost} Cash?`)) return;
  api('/api/shop', {method:'POST', body:JSON.stringify({item_id:id})}).then(() => refresh(true)).catch(error => toast(error.message));
};

function resultModal(title, icon, story, changes, note, battle = false, samples = []) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-backdrop';
  const breakdown = battleSamples(samples, changes?.win_chance, changes);
  overlay.innerHTML = `<div class="modal result-modal ${battle ? 'battle-result' : ''}"><span class="eyebrow">WHAT ACTUALLY CHANGED</span><h2>${icon} ${esc(title)}</h2><p>${esc(story)}</p>${changeRows(changes)}${breakdown}<div class="notice">${esc(note)}</div><button class="primary" id="close-result">Back to my city</button></div>`;
  document.body.appendChild(overlay);
  byId('close-result').onclick = () => overlay.remove();
}

window.chooseEvent = id => {
  const event = state.events.find(item => item.id === id);
  const targets = state.cities.filter(item => item.id !== state.me.id && attackable(item));
  if (event.kind === 'attack' && !targets.length) { toast('No rival is available. Shields and daily defense limits protect them.'); return; }
  const overlay = document.createElement('div');
  overlay.className = 'modal-backdrop';
  overlay.innerHTML = `<div class="modal"><h2>${event.icon} ${esc(event.name)}</h2><p>${esc(event.tagline)}</p><p class="cost">Cost: ${walletCost(event)}</p>${event.kind === 'attack' ? `<label class="field">TARGET CITY<select id="target">${targets.map(item => `<option value="${item.id}">${esc(item.name)} · ${esc(item.owner_name)}</option>`).join('')}</select></label>` : '<p>Your city will be the target.</p>'}<div class="actions"><button class="secondary" id="cancel">Cancel</button><button class="primary" id="confirm">Make it happen</button></div></div>`;
  document.body.appendChild(overlay);
  byId('cancel').onclick = () => overlay.remove();
  byId('confirm').onclick = async () => {
    state.busy = true;
    byId('confirm').disabled = true;
    byId('confirm').textContent = 'Bending reality…';
    try {
      const target_city_id = event.kind === 'attack' ? byId('target').value : null;
      const result = await api('/api/events', {method:'POST', body:JSON.stringify({event_id:id, target_city_id})});
      overlay.remove();
      await refresh(true);
      resultModal(event.name, event.icon, result.story, result.changes, result.success ? 'Event succeeded. The numbers above are the actual results.' : 'Event misfired. The token cost still applies.');
    } catch (error) { toast(error.message); byId('confirm').disabled = false; byId('confirm').textContent = 'Make it happen'; }
    finally { state.busy = false; }
  };
};

window.doErrand = async id => {
  const task = state.errands.find(item => item.id === id);
  if (state.busy) return;
  state.busy = true;
  try {
    const result = await api('/api/errands', {method:'POST', body:JSON.stringify({task_id:id})});
    await refresh(true);
    resultModal(task.name, task.icon, result.story, result.changes, 'Free city job completed. Your next job unlocks after the desk cooldown.');
  } catch (error) { toast(error.message); }
  finally { state.busy = false; }
};

window.buildCity = id => {
  const plan = state.buildingOffers.find(item => item.id === id);
  if (!plan || state.busy) return;
  const overlay = document.createElement('div');
  overlay.className = 'modal-backdrop';
  overlay.innerHTML = `<div class="modal"><h2>${plan.icon} ${esc(plan.name)}</h2><p>${esc(plan.description)}</p><p class="effect-preview">${esc(buildingPerk(plan))}</p><p class="cost">Construction cost: 💰 ${plan.cost} Wealth</p><div class="actions"><button class="secondary" id="cancel-build">Cancel</button><button class="primary" id="confirm-build">Build it</button></div></div>`;
  document.body.appendChild(overlay);
  byId('cancel-build').onclick = () => overlay.remove();
  byId('confirm-build').onclick = async () => {
    state.busy = true;
    byId('confirm-build').disabled = true;
    try {
      const result = await api('/api/buildings', {method:'POST', body:JSON.stringify({offer_id:id})});
      overlay.remove();
      await refresh(true);
      resultModal(plan.name, plan.icon, result.story, result.changes, 'Construction complete. Its bonus applies on future city days.');
    } catch (error) { toast(error.message); byId('confirm-build').disabled = false; }
    finally { state.busy = false; }
  };
};

window.startBattle = () => {
  if (state.busy) return;
  const targets = state.cities.filter(item => item.id !== state.me.id && attackable(item) && (state.pairAttacks[item.id] || 0) < state.pairBattleLimit);
  if (!targets.length) { toast('Every rival is resting after a battle'); return; }
  const overlay = document.createElement('div');
  overlay.className = 'modal-backdrop';
  overlay.innerHTML = `<div class="modal"><h2>⚔️ Twenty-trait battle</h2><p>The game randomly chooses 20 traits from both cities and the local AI invents a unique encounter. Either city can win. The winner takes trait points and may recruit a rival's special citizen.</p><label class="field">RIVAL CITY<select id="battle-target">${targets.map(item => `<option value="${item.id}">${esc(item.name)} · ${esc(item.owner_name)}</option>`).join('')}</select></label><p class="cost">Cost: 💰 ${state.me.battle_cost} Wealth · 4-hour rest after fighting</p><div class="actions"><button class="secondary" id="cancel-battle">Cancel</button><button class="primary" id="confirm-battle">Challenge!</button></div></div>`;
  document.body.appendChild(overlay);
  byId('cancel-battle').onclick = () => overlay.remove();
  byId('confirm-battle').onclick = async () => {
    state.busy = true;
    const rivalName = targets.find(item => item.id === byId('battle-target').value)?.name || 'the rival city';
    byId('confirm-battle').disabled = true;
    byId('confirm-battle').textContent = 'Preparing the arena…';
    try {
      const result = await api('/api/battles', {method:'POST', body:JSON.stringify({target_city_id:byId('battle-target').value})});
      const names = (result.sampled_traits || []).map(item => item.name);
      const fallbackBeats = [
        `${state.me.name} and ${rivalName} arrive with deeply questionable flags.`,
        `The judges demand a sudden audit of ${names[0] || 'civic enthusiasm'}.`,
        `A marching band weaponizes ${names[3] || 'confetti'}; both mayors deny hiring it.`,
        `${names[7] || 'The town council'} becomes a competitive sport for six bewildering minutes.`,
        `Someone files a formal complaint against ${names[11] || 'gravity'}. The complaint wins a trophy.`,
        `The defenders deploy emergency ${names[15] || 'snacks'} with alarming confidence.`,
        `The referee consults a duck. The duck asks for a recount.`,
        `Both cities demand that the final score be spelled correctly.`
      ];
      const beats = Array.isArray(result.beats) && result.beats.length >= 3 ? [`${state.me.name} challenges ${rivalName}. The crowd finds a safe distance.`, ...result.beats, 'The judges are counting the last ridiculous points.'] : fallbackBeats;
      const duration = 42000;
      const began = Date.now();
      let shown = 0;
      overlay.innerHTML = `<div class="modal battle-show"><span class="eyebrow">⚔️ BATTLE IN PROGRESS</span><h2>${esc(state.me.name)} vs ${esc(rivalName)}</h2><div class="battle-arena" aria-hidden="true"><span class="battle-fighter left">🏰</span><span class="battle-sparks">💥</span><span class="battle-fighter right">🏰</span></div><div class="progress"><i id="battle-progress" style="width:0%"></i></div><div class="battle-percent" id="battle-percent">0% · about 42 seconds remaining</div><div class="battle-ticker" id="battle-ticker" aria-live="polite"></div></div>`;
      await new Promise(resolve => {
        const timer = setInterval(() => {
          const fraction = Math.min(1, (Date.now()-began)/duration);
          const percent = Math.floor(fraction*100);
          const bar = byId('battle-progress');
          if (bar) bar.style.width = percent+'%';
          const label = byId('battle-percent');
          if (label) label.textContent = `${percent}% · ${Math.max(0,Math.ceil((duration-(Date.now()-began))/1000))} seconds remaining`;
          const shouldShow = Math.min(beats.length, Math.floor(fraction*beats.length)+1);
          const ticker = byId('battle-ticker');
          while (ticker && shown < shouldShow) { const line = document.createElement('p'); line.textContent = beats[shown++]; ticker.appendChild(line); ticker.scrollTop = ticker.scrollHeight; }
          if (fraction >= 1) { clearInterval(timer); resolve(); }
        }, 250);
      });
      overlay.remove();
      await refresh(true);
      resultModal(result.title, '⚔️', result.story, result.changes, `${result.moved} trait points moved. ${result.stolen_hero ? result.stolen_hero + ' changed cities.' : ''} The attacker had a ${result.chance}% win chance from traits, fighters, heroes, and defenses.`, true, result.sampled_traits);
    } catch (error) { toast(error.message); byId('confirm-battle').disabled = false; byId('confirm-battle').textContent = 'Challenge!'; }
    finally { state.busy = false; }
  };
};

window.showTradeProposal = () => {
  if (state.busy) return;
  if ((state.tradeQuota.sent_today || 0) >= (state.tradeQuota.daily_limit || 10)) { toast('Daily trade proposal limit reached'); return; }
  const rivals = state.cities.filter(item => item.id !== state.me.id && (state.tradeQuota.pair_sent_today?.[item.id] || 0) < (state.tradeQuota.pair_daily_limit || 4));
  if (!rivals.length) return;
  const overlay = document.createElement('div');
  overlay.className = 'modal-backdrop';
  overlay.innerHTML = `<div class="modal result-modal"><h2>🤝 Propose a trade</h2><p>Citizens and Wealth move only if the other mayor accepts. An empty side means a gift or request.</p><div class="trade-form"><label class="field">RIVAL CITY<select id="trade-target">${rivals.map(item => `<option value="${item.id}">${esc(item.name)}</option>`).join('')}</select></label><label class="field">CITIZEN YOU GIVE<select id="trade-offer-hero"><option value="">None</option>${state.heroes.map(hero => `<option value="${hero.id}">${esc(hero.name)} · ${rarityLabel(hero.tier)}</option>`).join('')}</select></label><label class="field">CITIZEN YOU ASK FOR<select id="trade-request-hero"></select></label><label class="field">WEALTH YOU GIVE<input class="input" id="trade-offer-wealth" type="number" min="0" max="20" value="0"></label><label class="field">WEALTH YOU ASK FOR<input class="input" id="trade-request-wealth" type="number" min="0" max="20" value="0"></label></div><div class="actions"><button class="secondary" id="cancel-trade">Cancel</button><button class="primary" id="confirm-trade">Send offer</button></div></div>`;
  document.body.appendChild(overlay);
  const fillRequested = () => { byId('trade-request-hero').innerHTML = '<option value="">None</option>' + state.rivalHeroes.filter(hero => hero.city_id === byId('trade-target').value).map(hero => `<option value="${hero.id}">${esc(hero.name)} · ${rarityLabel(hero.tier)}</option>`).join(''); };
  byId('trade-target').onchange = fillRequested;
  fillRequested();
  byId('cancel-trade').onclick = () => overlay.remove();
  byId('confirm-trade').onclick = async () => {
    if (state.busy) return;
    const offer_wealth = Number(byId('trade-offer-wealth').value), request_wealth = Number(byId('trade-request-wealth').value);
    if (![offer_wealth,request_wealth].every(value => Number.isInteger(value) && value >= 0 && value <= 20)) { toast('Wealth amounts must be between 0 and 20'); return; }
    const payload = {target_city_id:byId('trade-target').value,offer_hero_id:byId('trade-offer-hero').value || null,request_hero_id:byId('trade-request-hero').value || null,offer_wealth,request_wealth};
    if (!payload.offer_hero_id && !payload.request_hero_id && !offer_wealth && !request_wealth) { toast('Add a citizen or Wealth to the offer'); return; }
    state.busy = true; byId('confirm-trade').disabled = true;
    try { await api('/api/trades', {method:'POST',body:JSON.stringify(payload)}); overlay.remove(); await refresh(true); toast('Trade offer sent'); }
    catch (error) { toast(error.message); byId('confirm-trade').disabled = false; }
    finally { state.busy = false; }
  };
};

window.respondTrade = async (id, action) => {
  if (state.busy) return;
  const offer = state.trades.find(item => item.id === id);
  if (!offer || !confirm(`${action === 'accept' ? 'Accept' : offer.sender_id === state.me.id ? 'Cancel' : 'Decline'} this trade offer?`)) return;
  state.busy = true;
  try {
    const result = await api(`/api/trades/${id}/${action}`, {method:'POST'});
    await refresh(true);
    if (action === 'accept') resultModal(result.title, '🤝', result.story, result.changes, 'Both cities agreed. Any transferred citizens entered reserve slots in their new cities.');
    else toast(result.status === 'canceled' ? 'Trade canceled' : 'Trade declined');
  } catch (error) { toast(error.message); }
  finally { state.busy = false; }
};

window.showAccount = () => {
  const overlay = document.createElement('div');
  overlay.className = 'modal-backdrop';
  overlay.innerHTML = `<div class="modal"><h2>City passport</h2><p>Scan a code with your phone camera to open this city in the Android app.</p><label class="field">PHONE SERVER ADDRESS<input class="input" id="phone-server" type="url" value="${esc(state.phoneServerUrl || state.server)}"></label><div class="actions"><button class="primary" id="make-qr">Show transfer QR</button></div><div id="transfer-qr" class="transfer-qr"></div><p class="muted">The QR contains your private city key. Show it only to your own phone. For this home server, use <strong>http://192.168.1.190:3010</strong>, without the s.</p><label class="field">YOUR CITY KEY<input class="input" readonly value="${esc(state.key)}" id="saved-key"></label><div class="actions"><button class="secondary" id="change-server">Change server</button><button class="secondary" id="copy-key">Copy key</button><button class="secondary" id="close-account">Close</button></div></div>`;
  document.body.appendChild(overlay);
  byId('close-account').onclick = () => overlay.remove();
  byId('copy-key').onclick = async () => { try { await navigator.clipboard.writeText(state.key); toast('City key copied'); } catch { byId('saved-key').select(); toast('Select and copy your city key'); } };
  byId('change-server').onclick = () => { overlay.remove(); state.key = ''; localStorage.removeItem('chaos_key'); setup(); };
  byId('make-qr').onclick = () => {
    const server = byId('phone-server').value.trim().replace(/\/$/, '');
    if (!validServer(server)) { toast('Enter a private HTTP address or public HTTPS address'); return; }
    if (typeof qrcode !== 'function') { toast('QR maker unavailable. Refresh this page.'); return; }
    const link = new URL('chaoscities://join');
    link.searchParams.set('server', server);
    link.searchParams.set('key', state.key);
    try {
      const qr = qrcode(0, 'M');
      qr.addData(link.toString());
      qr.make();
      byId('transfer-qr').innerHTML = qr.createSvgTag({cellSize: 5, margin: 4, scalable: true});
    } catch { toast('Could not make the QR. Try the city key instead.'); }
  };
};

let lastCityLink = '';
let lastCityLinkAt = 0;
async function openCityLink(raw) {
  if (raw === lastCityLink && Date.now() - lastCityLinkAt < 5000) return;
  lastCityLink = raw;
  lastCityLinkAt = Date.now();
  let link;
  try { link = new URL(raw); } catch { return; }
  if (link.protocol !== 'chaoscities:' || link.hostname !== 'join') return;
  const server = (link.searchParams.get('server') || '').replace(/\/$/, '');
  const key = link.searchParams.get('key') || '';
  if (!validServer(server) || !key) { toast('This city QR is incomplete'); return; }
  const previous = {server: state.server, key: state.key};
  state.server = server;
  state.key = key;
  try {
    await api('/api/me', {timeoutMs: 9000});
    localStorage.setItem('chaos_server', server);
    localStorage.setItem('chaos_key', key);
    document.querySelector('.modal-backdrop')?.remove();
    await refresh();
  } catch (error) {
    state.server = previous.server;
    state.key = previous.key;
    if (!state.me) setup();
    toast(error.message);
  }
}

async function startApp() {
  const cap = window.Capacitor;
  if (window.ChaosNativeApp && cap?.isNativePlatform?.()) {
    const nativeApp = window.ChaosNativeApp;
    nativeApp.addListener('appUrlOpen', event => openCityLink(event.url)).catch(() => {});
    try {
      const launch = await nativeApp.getLaunchUrl();
      if (launch?.url) { await openCityLink(launch.url); return; }
    } catch {}
  }
  await refresh();
}

let nextDueCheck = 0;
setInterval(() => {
  if (!state.me) return;
  document.querySelectorAll('[data-countdown]').forEach(element => { element.textContent = clock(Number(element.dataset.countdown)); });
  document.querySelectorAll('[data-research-progress]').forEach(element => { element.style.width = researchPercent() + '%'; });
  const desk = byId('errand-timer');
  if (desk) desk.textContent = clock(state.me.next_errand_at) === 'ready' ? 'READY NOW' : 'NEXT JOB IN ' + clock(state.me.next_errand_at);
  const arena = byId('battle-timer');
  if (arena) arena.textContent = clock(state.me.next_battle_at) === 'ready' ? 'READY NOW' : 'READY IN ' + clock(state.me.next_battle_at);
  const now = Math.floor(Date.now() / 1000);
  if ((now >= state.me.next_tokens_at || now >= state.me.next_errand_at || (state.research && now >= state.research.ready_at)) && now >= nextDueCheck && !state.busy) {
    nextDueCheck = now + 20;
    refresh(true);
  }
}, 1000);
setInterval(() => { if (state.key && !state.busy && document.visibilityState === 'visible' && !document.querySelector('.modal-backdrop')) refresh(true); }, 20000);
startApp();
