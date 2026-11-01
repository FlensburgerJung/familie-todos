/* Familie ToDos - Frontend ohne Framework.
   Alle Texte im DOM werden über textContent gesetzt, nie über innerHTML. */

const state = {
  todos: [], lists: [], people: [], settings: {}, keys: {},
  horizons: {}, repeats: {}, efforts: [], listKinds: {},
  recentlyDone: [], areas: [], engineChain: [], deployment: {},
  pain: [],              // Schmerztagebuch, neueste zuerst
  meds: [],              // Einnahmen von Schmerzmitteln, neueste zuerst
  medOffen: '',          // welches Mittel gerade seine Mengen zeigt
  painNachtrag: false,   // traegt gerade etwas Vergangenes ein
  painZeitpunkt: '',     // fuer wann, als 'JJJJ-MM-TTTHH:MM' (leer = jetzt)
  cycle: [],             // Zyklusmarken, neueste zuerst
  painWert: 3,           // Stellung des Schiebers, noch nicht eingetragen
  painOrt: '',           // zuletzt gewaehlte Koerperstelle
  painTage: 14,          // Spanne des Verlaufs in Tagen
  me: '',                // wer gerade an diesem Geraet arbeitet
  stale: false,          // zeigt gerade den gepufferten Stand
  engineProblem: null,   // warum zuletzt kein Modell antwortete
  tab: 'start',
  horizon: 'soon',
  busy: false,
  statsRange: 7,        // Tage; 0 = alles
  statsMeasure: 'time', // 'time' oder 'count'
  focus: null,          // vom Start aus geöffnete Unteransicht
  editing: null,        // id des Todos, das gerade bearbeitet wird
  weekOffset: 0,        // 0 = laufende Woche
};

const QUEUE_KEY = 'familie-todos-queue';
const CACHE_KEY = 'familie-todos-state';
const SHARED_KEY = 'familie-todos-shared';
const ME_KEY = 'familie-todos-me';
const THEME_KEY = 'familie-todos-theme';

/* Hell, dunkel oder wie das Geraet es haelt. Die Wahl wird sofort gesetzt -
   noch bevor die Oberflaeche steht, damit nichts kurz aufblitzt. */
const THEMES = [
  { id: 'auto', icon: '🌓', label: 'Farbschema: wie das Gerät' },
  { id: 'light', icon: '☀️', label: 'Farbschema: hell' },
  { id: 'dark', icon: '🌙', label: 'Farbschema: dunkel' },
];

function readTheme() {
  try { return localStorage.getItem(THEME_KEY) || 'auto'; } catch { return 'auto'; }
}

function applyTheme(id) {
  const root = document.documentElement;
  if (id === 'auto') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', id);
  try {
    if (id === 'auto') localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, id);
  } catch { /* egal */ }
  const farbe = getComputedStyle(root).getPropertyValue('--bg').trim();
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta && farbe) meta.setAttribute('content', farbe);
}

applyTheme(readTheme());

function setupTheme() {
  const knopf = document.getElementById('theme-toggle');
  if (!knopf) return;
  const zeige = () => {
    const aktuell = THEMES.find(t => t.id === readTheme()) || THEMES[0];
    knopf.textContent = aktuell.icon;
    knopf.title = aktuell.label + ' — tippen zum Wechseln';
  };
  knopf.addEventListener('click', () => {
    const index = THEMES.findIndex(t => t.id === readTheme());
    applyTheme(THEMES[(index + 1) % THEMES.length].id);
    zeige();
  });
  zeige();
}

/* Wer sitzt gerade vor dem Geraet? Wird pro Geraet gemerkt - Simones Handy
   ist Simone. Dadurch laesst sich festhalten, wer etwas erledigt hat, ohne
   dass jemand drei Passwoerter braucht. */
function readMe() {
  try { return localStorage.getItem(ME_KEY) || ''; } catch { return ''; }
}

function setMe(id) {
  try {
    if (id) localStorage.setItem(ME_KEY, id);
    else localStorage.removeItem(ME_KEY);
  } catch { /* egal */ }
  state.me = id || '';
}

/* Android kann Text aus jeder App hierher teilen (share_target im Manifest).
   Der Text wird sofort weggeschrieben: Zwischen Teilen und fertig geladener
   Oberflaeche kann eine Anmeldung liegen, die die Adresse verwirft. */
(function catchShared() {
  const params = new URLSearchParams(location.search);
  const shared = [params.get('title'), params.get('text'), params.get('url')]
    .filter(Boolean).join(' ').trim();
  if (shared) {
    try { localStorage.setItem(SHARED_KEY, shared); } catch { /* egal */ }
  }
  if (shared || params.has('neu')) {
    try { history.replaceState(null, '', '/'); } catch { /* egal */ }
    window.__openCapture = true;
  }
})();
const SOON_DAYS = 7;

// Am Telefon soll nach dem Absenden die Tastatur zugehen, damit man sieht,
// wohin der Einwurf einsortiert wurde. Mit Maus bleibt der Fokus im Feld.
const isTouch = window.matchMedia('(pointer: coarse)').matches;

/* ---------- kleine Helfer ---------- */

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'text') node.textContent = value;
    else if (key === 'class') node.className = value;
    else if (key === 'html') node.innerHTML = value;   // nur für eigene Markup-Fragmente
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of [].concat(children)) {
    if (child) node.append(child.nodeType ? child : document.createTextNode(child));
  }
  return node;
}

function today() {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function parseDate(value) {
  if (!value) return null;
  const [y, m, d] = value.split('-').map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

function daysUntil(value) {
  const date = parseDate(value);
  if (!date) return null;
  return Math.round((date - today()) / 86400000);
}

function formatDue(value) {
  const days = daysUntil(value);
  if (days === null) return 'ohne Datum';
  if (days === 0) return 'heute';
  if (days === 1) return 'morgen';
  if (days === -1) return 'gestern';
  if (days < 0) return `${-days} Tage überfällig`;
  if (days < 7) return `in ${days} Tagen`;
  const date = parseDate(value);
  return date.toLocaleDateString('de-DE', { day: '2-digit', month: 'short' });
}

const ENGINE_NAMES = {
  mistral: 'Mistral', anthropic: 'Claude', openai: 'ChatGPT',
  ollama: 'lokales Modell', heuristic: 'Stichwortsuche', manuell: 'von Hand',
};

function engineName(engine) {
  return ENGINE_NAMES[engine] || engine || '—';
}

function formatEffort(minutes) {
  minutes = Number(minutes) || 0;
  if (minutes <= 0) return 'ohne Angabe';
  if (minutes < 60) return `${minutes} Min`;
  const hours = Math.floor(minutes / 60), rest = minutes % 60;
  return rest === 0 ? `${hours} h` : `${hours}:${String(rest).padStart(2, '0')} h`;
}

function toast(message, isError = false, undo = null) {
  const node = document.getElementById('toast');
  node.textContent = '';
  node.append(document.createTextNode(message));
  if (undo) {
    node.append(el('button', {
      class: 'toast-undo', type: 'button', text: 'Rückgängig',
      onclick: async () => {
        node.className = '';
        await undo();
      },
    }));
  }
  node.className = 'show' + (isError ? ' error' : '');
  clearTimeout(node._timer);
  // Mit Rückgängig länger stehen lassen - man muss es ja lesen und treffen.
  node._timer = setTimeout(() => { node.className = ''; },
                           isError ? 6000 : (undo ? 8000 : 3500));
}

/* Schlafende Server geduldig wecken.

   Auf günstigen Tarifen fährt der Dienst nach einer Viertelstunde Ruhe
   herunter; der erste Aufruf danach braucht bis zu einer Minute. Ohne
   Wiederholung sieht die Familie dann eine Fehlermeldung statt ihrer Listen. */
/* Nach Zeit begrenzen, nicht nach Versuchen: ein schlafender Dienst antwortet
   sofort mit 502, statt in eine Zeitüberschreitung zu laufen. Feste Versuche
   wären darum in Sekunden aufgebraucht, lange bevor er wach ist. */
const WAKE_BUDGET_MS = 90000;

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function apiWithPatience(path, onWaiting, method, body) {
  const until = Date.now() + WAKE_BUDGET_MS;
  let lastError, attempt = 0;

  while (Date.now() < until) {
    attempt++;
    try {
      return await api(path, method, body);
    } catch (error) {
      lastError = error;
      // Eine abgelehnte Anmeldung wiederholt sich nicht von selbst.
      if (error.status === 401) throw error;
      const left = Math.max(0, Math.round((until - Date.now()) / 1000));
      if (left <= 0) break;
      if (onWaiting) onWaiting(attempt, left);
      // Kurz steigende Pausen: schnell beim ersten Mal, dann ruhiger.
      await sleep(Math.min(5000, 1000 * attempt));
    }
  }
  throw lastError;
}

/* Sichtbar machen, dass gewartet wird.

   Schlaeft der Dienst, dauert die erste Anfrage bis zu einer Minute. Ohne
   Rueckmeldung tippt man in der Zeit immer weiter, weil man denkt, es sei
   nichts angekommen. Ein Balken nach gut einer Sekunde sagt, was los ist -
   und bittet ausdruecklich, nicht mehrfach zu tippen. */
let offeneAnfragen = 0;
let balkenTimer = null;
let balkenSeit = 0;
let balkenText = null;

function zeigeWarteBalken() {
  let balken = document.getElementById('waitbar');
  if (!balken) {
    balkenText = el('span', {});
    balken = el('div', { id: 'waitbar', role: 'status', 'aria-live': 'polite' }, [
      el('span', { class: 'spin' }), balkenText,
    ]);
    document.body.append(balken);
  }
  balkenSeit = Date.now();
  const aktualisiere = () => {
    if (!balkenText) return;
    const sekunden = Math.round((Date.now() - balkenSeit) / 1000);
    balkenText.textContent = sekunden < 6
      ? ' Moment — der Server antwortet gleich …'
      : ` Der Server war eingeschlafen und fährt hoch (${sekunden} s). `
        + 'Bitte nicht mehrfach tippen, es geht nichts verloren.';
  };
  aktualisiere();
  balken.classList.add('show');
  balken._ticker = setInterval(aktualisiere, 1000);
}

function versteckeWarteBalken() {
  const balken = document.getElementById('waitbar');
  if (!balken) return;
  clearInterval(balken._ticker);
  balken.classList.remove('show');
}

/* Nicht jede laufende Anfrage ist eine, auf die jemand wartet. Ein
   eingeworfener Eintrag gilt als erledigt, sobald er in der Warteschlange
   liegt - die Anfrage dazu läuft noch, aber niemand schaut ihr zu. Ohne
   diese Unterscheidung dreht sich oben weiter ein Balken, während unten
   „Gemerkt" steht: zwei Aussagen, die einander widersprechen. */
let stilleAnfragen = 0;

function jemandWartet() {
  return offeneAnfragen - stilleAnfragen > 0;
}

function pruefeWarteBalken() {
  if (jemandWartet()) return;
  clearTimeout(balkenTimer);
  versteckeWarteBalken();
}

function anfrageBeginnt() {
  offeneAnfragen++;
  if (jemandWartet() && !balkenTimer) {
    // Kurze Anfragen sollen keinen Balken aufblitzen lassen.
    balkenTimer = setTimeout(() => { balkenTimer = null; zeigeWarteBalken(); }, 1200);
  }
}

function anfrageEndet() {
  offeneAnfragen = Math.max(0, offeneAnfragen - 1);
  pruefeWarteBalken();
}

/* Ab hier wartet niemand mehr auf dieses Versprechen. */
function inDenHintergrund(versprechen) {
  stilleAnfragen++;
  pruefeWarteBalken();
  return versprechen.finally(() => {
    stilleAnfragen = Math.max(0, stilleAnfragen - 1);
  });
}

async function api(path, method = 'GET', body) {
  // Ohne Zeitgrenze hängt der Aufruf minutenlang, statt es neu zu versuchen.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  let response;
  anfrageBeginnt();
  try {
    response = await fetch(path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
    anfrageEndet();
  }
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && path !== '/api/login') {
    // Sitzung abgelaufen oder von anderswo beendet.
    const unauthorized = new Error('Nicht angemeldet');
    unauthorized.status = 401;
    throw unauthorized;
  }
  if (!response.ok) {
    const failure = new Error(data.error || `Fehler ${response.status}`);
    failure.status = response.status;
    throw failure;
  }
  return data;
}

/* ---------- Anmeldung ---------- */

function showLogin(message) {
  const wrap = document.querySelector('.wrap');
  wrap.textContent = '';
  const fab = document.getElementById('fab');
  if (fab) fab.hidden = true;

  const input = el('input', {
    type: 'password', autocomplete: 'current-password',
    placeholder: 'Familienpasswort', autofocus: true,
  });
  // Wer sich anmeldet, sagt gleich wer er ist - das Passwort ist gemeinsam.
  const whoWrap = el('div', { class: 'login-who' });
  const error = el('div', { class: 'login-error', text: message || '' });
  const button = el('button', { class: 'btn btn-primary', type: 'submit', text: 'Anmelden' });

  const form = el('form', {
    class: 'login',
    onsubmit: async event => {
      event.preventDefault();
      button.disabled = true;
      button.textContent = 'Moment…';
      try {
        await api('/api/login', 'POST', { password: input.value });
        const gewaehlt = whoWrap.querySelector('select');
        if (gewaehlt && gewaehlt.value) setMe(gewaehlt.value);
        location.reload();
      } catch (err) {
        error.textContent = err.message;
        input.value = '';
        input.focus();
        button.disabled = false;
        button.textContent = 'Anmelden';
      }
    },
  }, [
    el('h1', { text: 'Familie ToDos' }),
    el('p', { text: 'Bitte einmal anmelden, danach bleibt das Gerät angemeldet.' }),
    input, whoWrap, error, button,
  ]);

  wrap.append(form);

  // Die Namensliste braucht die Personen - die holen wir nebenbei.
  api('/api/people-public').then(data => {
    if (!data.people || !data.people.length) return;
    whoWrap.append(el('select', { 'aria-label': 'Wer bist du?' }, [
      el('option', { value: '', text: 'Wer bist du? (später wählbar)' }),
      ...data.people.map(p => el('option', {
        value: p.id, text: `${p.emoji} ${p.name}`, selected: p.id === readMe(),
      })),
    ]));
  }).catch(() => { /* ohne Namensliste geht es auch */ });
}

/* ---------- Offline-Warteschlange ---------- */

function readQueue() {
  try { return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'); }
  catch { return []; }
}

function writeQueue(items) {
  try { localStorage.setItem(QUEUE_KEY, JSON.stringify(items)); } catch { /* voll oder gesperrt */ }
}

function enqueue(entry) {
  const queue = readQueue();
  queue.push(entry);
  writeQueue(queue);
}

/* Ein angekommener Eintrag verlässt die Warteschlange wieder. Erkannt wird
   er an der Kennung, die der Browser beim Einwerfen vergeben hat. */
function dequeue(clientId) {
  if (!clientId) return;
  writeQueue(readQueue().filter(entry => entry.clientId !== clientId));
}

function neueKennung() {
  if (self.crypto && crypto.randomUUID) return crypto.randomUUID();
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
}

async function flushQueue() {
  const queue = readQueue();
  if (!queue.length) return;
  const remaining = [];
  for (const entry of queue) {
    try { await api('/api/capture', 'POST', entry); }
    catch { remaining.push(entry); }
  }
  writeQueue(remaining);
  const sent = queue.length - remaining.length;
  if (sent > 0) {
    toast(`${sent} nachgereicht${sent > 1 ? 'e Einträge' : 'er Eintrag'}.`);
    await refresh();
  }
}

/* ---------- Daten ---------- */

/* Der zuletzt geladene Stand bleibt im Browser liegen. Dadurch sind die
   Listen sofort da - auch während der Dienst noch aufwacht oder gar kein Netz
   da ist. Geändert werden kann in dem Zustand nichts; das sagt ein Hinweis. */
function cacheState(data) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ at: Date.now(), data }));
  } catch { /* Speicher voll oder gesperrt - dann eben ohne Puffer */ }
}

function readCachedState() {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && parsed.data && parsed.data.lists ? parsed : null;
  } catch {
    return null;
  }
}

async function refresh() {
  const data = await api('/api/state');
  Object.assign(state, data);
  state.stale = false;
  cacheState(data);
  render();
}

/* ---------- Ableitungen ---------- */

const openTodos = () => state.todos.filter(t => t.status === 'open');
const inboxTodos = () => state.todos.filter(t => t.status === 'inbox');
const overdueTodos = () => openTodos().filter(t => (daysUntil(t.dueDate) ?? 99) < 0);
const soonTodos = () => openTodos().filter(t => {
  const days = daysUntil(t.dueDate);
  return days !== null && days >= 0 && days <= SOON_DAYS;
});

const listById = id => state.lists.find(l => l.id === id);
const personById = id => state.people.find(p => p.id === id);

/* Wünsche, Einkäufe und Medien sind Sammlungen: kein Termin, keine
   Überfälligkeit. Ohne diese Unterscheidung würde jeder Buchtipp irgendwann
   als überfällig erscheinen.

   Termine zählen dagegen sehr wohl mit - ein täglich wiederkehrender Eintrag
   steht heute an, egal ob er auf der Aufgaben- oder der Terminliste liegt. */
const listKind = id => (listById(id) || {}).kind || 'tasks';
const isTask = todo => {
  const bereich = (state.areas || []).find(a => a.id === listKind(todo.listId));
  return bereich ? bereich.dated : true;
};

/* „Bald" heißt: ab morgen, innerhalb der Woche. Heute Fälliges bleibt
   draußen, sonst stünde dieselbe Aufgabe in zwei Kacheln und die Zahlen
   ergäben zusammen mehr, als es Aufgaben gibt. */
const baldTodos = () => openTodos().filter(t => {
  const tage = daysUntil(t.dueDate);
  return isTask(t) && tage !== null && tage >= 1 && tage <= SOON_DAYS;
});

/* Genau heute - Liegengebliebenes zählt unter „überfällig".

   Vorher galt hier „heute oder früher". Neben einer eigenen Kachel für
   Überfälliges hieß das: Dieselbe Aufgabe wurde zweimal gezählt, und die
   Summe der vier Zahlen war größer als die Zahl der Aufgaben. Jetzt teilen
   überfällig / heute / bald die Aufgaben sauber untereinander auf. */
const todayTodos = () => openTodos().filter(
  t => isTask(t) && daysUntil(t.dueDate) === 0);
const unassignedTodos = () => openTodos().filter(t => isTask(t) && !t.assigneeId);
const repeatingTodos = () => openTodos().filter(t => t.repeat);
const kindTodos = kind => openTodos().filter(t => listKind(t.listId) === kind);
const personTodos = id => openTodos().filter(t => isTask(t) && t.assigneeId === id);

/* Was jetzt zählt, von dem trennen, was wirklich noch Zeit hat.

   Zwei Fälle sind zu unterscheiden:

   Die meisten Todos haben kein echtes Fristdatum - „bald" heißt in drei Tagen,
   weil jemand beim Einwerfen auf „Bald" getippt hat. Die gehören in die Liste,
   sonst stünde dort fast nichts.

   Ein beim Abhaken erzeugter Folgetermin ist etwas anderes: Wer den Müll
   gerade rausgebracht hat, will ihn nicht sofort wieder dort stehen sehen.
   Der bleibt weg, bis er dran ist - erkennbar daran, dass er von einem
   abgehakten Vorgänger stammt. */
function splitByDue(todos) {
  const faellig = [], spaeter = [];
  for (const todo of todos) {
    const tage = daysUntil(todo.dueDate);
    if (tage === null || tage <= 0) faellig.push(todo);
    else if (todo.createdFrom) spaeter.push(todo);
    else if (tage <= SOON_DAYS) faellig.push(todo);
    else spaeter.push(todo);
  }
  return { faellig, spaeter };
}

/* Was später dran ist, bleibt sichtbar - nur abgetrennt.

   Weggeklappt gerät es aus dem Blick, und genau das will man nicht: Wer
   gerade Luft hat, soll sehen, was sich vorziehen lässt. Eine gestrichelte
   Linie macht trotzdem deutlich, was drängt und was Zeit hat. */
function laterBlock(todos, zeichne) {
  if (!todos.length) return null;
  return el('div', { class: 'later-block' }, [
    el('div', { class: 'later-divider' },
      el('span', { text: `später — ${todos.length} ${todos.length === 1 ? 'Eintrag' : 'Einträge'}` })),
    el('div', { class: 'later-items' }, todos.map(zeichne)),
  ]);
}

/* Notizen für heute. Ein PostIt mit Datum soll an seinem Tag auf der
   Startseite auftauchen - nicht vorher und, wenn es liegen bleibt, auch
   danach noch. Ohne Datum bleibt es nur in seiner Kachel. */
const POSTIT_AREA = 'postits';

function todayNotes() {
  return openTodos().filter(todo => {
    if (listKind(todo.listId) !== POSTIT_AREA) return false;
    const tage = daysUntil(todo.dueDate);
    return tage !== null && tage <= 0;
  });
}

function sumMinutes(todos) {
  return todos.reduce((total, t) => total + (Number(t.minutes) || 0), 0);
}

/* Was eine vom Start geöffnete Unteransicht zeigt. */
const FOCUS_VIEWS = {
  today: { title: 'Heute fällig', get: todayTodos },
  soon: {
    title: 'Die nächsten Tage',
    hint: 'Ab morgen bis in einer Woche — was sich vorziehen lässt, wenn gerade Luft ist.',
    get: baldTodos,
  },
  overdue: { title: 'Überfällig', get: () => overdueTodos().filter(isTask) },
  inbox: { title: 'Kurz bestätigen', get: inboxTodos },
  unassigned: {
    title: 'Noch niemandem zugewiesen',
    hint: 'Nimmt sich, wer gerade Luft hat.',
    get: unassignedTodos,
  },
  repeating: {
    title: 'Regelmäßige Aufgaben',
    hint: 'Nach dem Abhaken entsteht jeweils der nächste Termin.',
    get: repeatingTodos,
  },
  wishes: { title: 'Wünsche', get: () => kindTodos('wishes') },
  recent: {
    title: 'Zuletzt erledigt',
    hint: 'Die letzten 24 Stunden. Versehentlich abgehakt? Hier zurückholen.',
    get: () => state.recentlyDone || [],
  },
  media: { title: 'Bücher, Filme & Podcasts', get: () => kindTodos('media') },
};

/* ---------- Bausteine ---------- */

function metaChips(todo) {
  const chips = [];
  const list = listById(todo.listId);
  if (list) chips.push(el('span', { class: 'chip', text: `${list.emoji} ${list.name}` }));

  const person = personById(todo.assigneeId);
  if (person) {
    // In einer Sammlung ist die Person der Empfaenger, nicht der Zustaendige.
    const fuer = isTask(todo) ? '' : 'für ';
    chips.push(el('span', { class: 'chip', text: `${person.emoji} ${fuer}${person.name}` }));
  }

  if (todo.dueDate) {
    const days = daysUntil(todo.dueDate);
    const cls = days < 0 ? 'chip due-over' : days <= SOON_DAYS ? 'chip due-soon' : 'chip';
    chips.push(el('span', { class: cls, text: formatDue(todo.dueDate) }));
  }
  if (todo.priority === 'high') chips.push(el('span', { class: 'chip prio-high', text: 'wichtig' }));
  if (todo.priority === 'low') chips.push(el('span', { class: 'chip', text: 'kann warten' }));
  if (todo.repeat && state.repeats[todo.repeat]) {
    chips.push(el('span', { class: 'chip repeat', text: `↻ ${state.repeats[todo.repeat]}` }));
  }
  if (todo.minutes > 0) chips.push(el('span', { class: 'chip', text: formatEffort(todo.minutes) }));
  return el('div', { class: 'meta' }, chips);
}

/* Der Haken zum Abhaken. Eigener Baustein, weil er in der Karte und im
   Tagesstreifen oben vorkommt - zwei Umsetzungen desselben Knopfes würden
   garantiert auseinanderlaufen. */
function hakenKnopf(todo, klasse = 'check') {
  const check = el('button', {
    class: klasse,
    title: 'Erledigt',
    'aria-label': `„${todo.title}“ als erledigt markieren`,
    text: '✓',
    onclick: async () => {
      check.disabled = true;
      // Fokus abgeben, sonst bleibt die Hervorhebung am Platz hängen und
      // wirkt nach dem Neuzeichnen wie ein Haken am nächsten Eintrag.
      check.blur();
      try {
        const result = await api(`/api/todos/${todo.id}`, 'PATCH',
                                 { status: 'done', doneBy: state.me });
        toast(result.next
          ? `Erledigt. Wieder fällig ${formatDue(result.next.dueDate)}.`
          : 'Erledigt. 🎉', false,
          async () => {
            try {
              await api(`/api/todos/${todo.id}/restore`, 'POST', {});
              toast('Zurückgeholt.');
              await refresh();
            } catch (error) { toast(error.message, true); }
          });
        await refresh();
      } catch (error) { toast(error.message, true); check.disabled = false; }
    },
  });
  return check;
}

function todoCard(todo, { overdue = false } = {}) {
  /* Wird dieser Eintrag gerade bearbeitet, steht hier die Bearbeitungskarte -
     an genau derselben Stelle. Vorher wurde sie oben an die Ansicht gehängt:
     Die Seite sprang nach oben, der Eintrag blieb unten stehen, und jeder
     weitere Druck auf ⋯ erzeugte eine weitere Karte. */
  if (state.editing === todo.id) {
    return reviewCard({ ...todo, question: '', suggestion: {} }, { inline: true });
  }

  const check = hakenKnopf(todo);

  const body = el('div', { class: 'todo-body' }, [
    el('div', { class: 'todo-title', text: todo.title }),
    todo.note
      ? el('div', { class: 'todo-note' + (todo.noteSource === 'model' ? ' from-model' : '') },
          todo.noteSource === 'model'
            ? [el('span', { class: 'note-tag', title: 'Hinweis aus der Einordnung — '
                            + 'bearbeiten über ⋯, dann gilt er als deiner', text: 'KI' }),
               ' ', todo.note]
            : todo.note)
      : null,
    metaChips(todo),
  ]);

  const edit = el('button', {
    class: 'btn btn-ghost btn-sm', text: '⋯', title: 'Bearbeiten',
    'aria-expanded': 'false',
    onclick: () => { state.editing = todo.id; render(); },
  });

  /* Auf dem Einkaufszettel ein Stern: „daran muss ich denken".

     Ein Posten erinnert niemanden daran, auch hinzufahren - „Vitamin D"
     steht beim Einkauf, der Weg zur Apotheke nirgends. Der Stern legt dafür
     ein Todo an, eines je Zettel. */
  const istEinkauf = listKind(todo.listId) === 'shopping';
  const wichtig = todo.priority === 'high';
  const stern = istEinkauf ? el('button', {
    class: 'btn btn-ghost btn-sm star' + (wichtig ? ' an' : ''),
    text: wichtig ? '★' : '☆',
    title: wichtig
      ? 'Nicht mehr merken — das Besorgungs-Todo fällt weg'
      : 'Daran denken — legt ein Todo für den Gang an',
    'aria-pressed': String(wichtig),
    onclick: async () => {
      stern.disabled = true;
      stern.blur();
      try {
        await api(`/api/todos/${todo.id}`, 'PATCH',
                  { priority: wichtig ? 'normal' : 'high' });
        toast(wichtig ? 'Merker entfernt.' : 'Kommt als Todo dazu.');
        await refresh();
      } catch (error) { toast(error.message, true); stern.disabled = false; }
    },
  }) : null;

  // Bei Essensideen gibt es zusätzlich den Rezeptvorschlag.
  const istEssen = listKind(todo.listId) === 'meals';
  const karte = el('div', { class: 'card' + (overdue ? ' overdue' : '') },
    el('div', { class: 'todo' }, [check, body, stern, edit]));

  if (istEssen) {
    const fach = el('div', { hidden: !todo.detail });
    if (todo.detail) fach.append(recipePanel(todo));
    const auf = el('button', {
      class: 'recipe-toggle', type: 'button',
      text: todo.detail ? '▾ Rezept' : '🍲 Rezept',
      onclick: () => {
        if (!fach.childElementCount) fach.append(recipePanel(todo));
        fach.hidden = !fach.hidden;
        auf.textContent = (fach.hidden ? '▸ ' : '▾ ')
          + (todo.detail ? 'Rezept' : 'Rezept vorschlagen');
      },
    });
    karte.append(auf, fach);
  }

  return karte;
}

/* Abgehaktes mit Knopf zum Zurückholen. */
function doneCard(todo) {
  const restore = el('button', {
    class: 'btn btn-sm', type: 'button', text: '↩ Zurückholen',
    onclick: async () => {
      restore.disabled = true;
      try {
        const result = await api(`/api/todos/${todo.id}/restore`, 'POST', {});
        toast(result.removedFollowUp
          ? 'Zurückgeholt — der Folgetermin wurde entfernt.'
          : 'Zurückgeholt.');
        await refresh();
      } catch (error) { toast(error.message, true); restore.disabled = false; }
    },
  });

  const wann = todo.doneAt
    ? new Date(todo.doneAt).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
    : '';

  return el('div', { class: 'card done-card' }, [
    el('div', { class: 'todo' }, [
      el('span', { class: 'done-mark', text: '✓' }),
      el('div', { class: 'todo-body' }, [
        el('div', { class: 'todo-title struck', text: todo.title }),
        metaChips(todo),
        wann ? el('div', { class: 'todo-note', text: `abgehakt um ${wann} Uhr` }) : null,
      ]),
    ]),
    el('div', { class: 'actions' }, [restore]),
  ]);
}

/* Rezeptvorschlag zu einer Essensidee.

   Eigener Knopf statt automatisch: ein Rezept will man, wenn man kochen will -
   nicht zu jeder Idee, die einem einfällt. Jeder Aufruf kostet schliesslich. */
function recipePanel(todo) {
  const personen = el('input', {
    type: 'number', min: '1', max: '20', value: '4', class: 'recipe-people',
    'aria-label': 'Für wie viele Personen?',
  });
  const wuensche = el('input', {
    type: 'text', placeholder: 'z. B. vegetarisch, kalorienarm, schnell',
    'aria-label': 'Besondere Wünsche',
  });

  const knopf = el('button', {
    class: 'btn btn-sm', type: 'button',
    text: todo.detail ? '↻ Neues Rezept' : '🍲 Rezept vorschlagen',
    onclick: async () => {
      knopf.disabled = true;
      const vorher = knopf.textContent;
      knopf.textContent = 'Kocht nach …';
      try {
        const result = await api(`/api/todos/${todo.id}/recipe`, 'POST', {
          people: Number(personen.value) || 4,
          notes: wuensche.value,
        });
        toast(`Rezept von ${engineName(result.engine)}.`);
        await refresh();
      } catch (error) {
        toast(error.message, true);
        knopf.disabled = false;
        knopf.textContent = vorher;
      }
    },
  });

  return el('div', { class: 'recipe-box' }, [
    el('div', { class: 'recipe-controls' }, [
      el('label', { class: 'recipe-label' }, [
        el('span', { text: 'Für' }), personen, el('span', { text: 'Personen' })]),
      wuensche,
      knopf,
    ]),
    todo.detail
      ? rezeptText(todo.detail)
      : el('p', { class: 'hint', style: 'margin:8px 0 0',
          text: 'Wünsche sind freiwillig — ohne Angabe kommt ein alltagstaugliches Rezept.' }),
  ]);
}

/* Ein Rezept ist lang. Steht es ganz da, schiebt es alles andere aus dem
   Bild - dabei will man beim Durchsehen der Essensideen nur wissen, was es
   ist. Also die ersten Zeilen zeigen, der Rest auf Klick. Der weiche
   Übergang nach unten sagt dabei deutlicher als jeder Pfeil, dass da noch
   mehr kommt. */
function rezeptText(inhalt) {
  const text = el('pre', { class: 'recipe-text', text: inhalt });
  const huelle = el('div', { class: 'recipe-collapse' }, text);
  const mehr = el('button', {
    class: 'recipe-more', type: 'button', text: '▾ Ganzes Rezept',
    'aria-expanded': 'false',
    onclick: () => {
      const offen = huelle.classList.toggle('offen');
      mehr.textContent = offen ? '▴ Einklappen' : '▾ Ganzes Rezept';
      mehr.setAttribute('aria-expanded', String(offen));
      if (!offen) huelle.scrollIntoView({ block: 'nearest' });
    },
  });
  return el('div', {}, [huelle, mehr]);
}

/* Karte für einen Eintrag, bei dem sich das Modell nicht sicher war. */
function reviewCard(todo, { inline = false } = {}) {
  const suggestion = todo.suggestion || {};
  const wantsNewList = Boolean(suggestion.newList);

  /* Auf einem Wunschzettel oder einer Merkliste gibt es nichts zu terminieren,
     zu schätzen oder zu wiederholen - ein Buchwunsch dauert keine 30 Minuten.
     Diese Felder bleiben dort weg, statt leer herumzustehen. */
  const areaOf = kind => (state.areas || []).find(a => a.id === kind);

  /* Welche Felder sinnvoll sind, haengt an der gewaehlten Liste - und die
     laesst sich mitten im Bearbeiten wechseln. Deshalb wird der Zustand bei
     Bedarf neu bestimmt, statt ihn einmal festzuschreiben. */
  const istDatiert = (kind) => (areaOf(kind) || { dated: true }).dated;
  const targetKind = listKind(todo.listId);
  let dated = istDatiert(targetKind);

  const titleInput = el('input', { type: 'text', value: todo.title });
  // Bisher liess sich die Notiz nicht aendern - dabei schreibt das Modell
  // gelegentlich Ueberfluessiges hinein, das man loswerden will.
  const noteInput = el('textarea', {
    rows: '2', placeholder: 'Notiz (optional)',
  });
  noteInput.value = todo.note || '';

  const listSelect = el('select', {}, [
    el('option', { value: '', text: '— Liste wählen —' }),
    ...state.lists.map(list => el('option', {
      value: list.id, text: `${list.emoji} ${list.name}`,
      selected: list.id === todo.listId,
    })),
    el('option', {
      value: '__new__', text: wantsNewList ? `➕ Neue Liste: ${suggestion.newList}` : '➕ Neue Liste…',
      selected: wantsNewList && !todo.listId,
    }),
  ]);

  const newListInput = el('input', {
    type: 'text', placeholder: 'Name der neuen Liste',
    value: suggestion.newList || '',
  });
  const newListWrap = el('label', { class: 'field wide' }, [
    el('span', { text: 'Neue Liste' }), newListInput,
  ]);
  const syncNewList = () => { newListWrap.hidden = listSelect.value !== '__new__'; };
  listSelect.addEventListener('change', syncNewList);

  const personSelect = el('select', {}, [
    el('option', { value: '', text: dated ? '— niemand —' : '🏠 für alle' }),
    ...state.people.map(person => el('option', {
      value: person.id, text: `${person.emoji} ${person.name}`,
      selected: person.id === todo.assigneeId,
    })),
  ]);

  const dueInput = el('input', { type: 'date', value: todo.dueDate || '' });

  const prioSelect = el('select', {}, [
    ['low', 'kann warten'], ['normal', 'normal'], ['high', 'wichtig'],
  ].map(([value, label]) => el('option', {
    value, text: label, selected: todo.priority === value,
  })));

  const repeatSelect = el('select', {}, Object.entries(state.repeats).map(
    ([value, label]) => el('option', {
      value, text: label, selected: (todo.repeat || '') === value,
    })));

  const effortSelect = el('select', {}, (state.efforts || [0]).map(
    minutes => el('option', {
      value: String(minutes), text: formatEffort(minutes),
      selected: Number(todo.minutes || 0) === minutes,
    })));

  // Beschriftungen gesondert halten: sie wechseln mit der Liste mit.
  const personLabel = el('span', { text: dated ? 'Wer' : 'Für wen' });
  const dueLabel = el('span', { text: dated ? 'Fällig' : 'Für welchen Tag' });
  const personWrap = el('label', { class: 'field' }, [personLabel, personSelect]);
  const dueWrap = el('label', { class: 'field' }, [dueLabel, dueInput]);
  const prioWrap = el('label', { class: 'field' }, [el('span', { text: 'Priorität' }), prioSelect]);
  const repeatWrap = el('label', { class: 'field' }, [el('span', { text: 'Wiederholung' }), repeatSelect]);
  const effortWrap = el('label', { class: 'field' }, [el('span', { text: 'Dauer' }), effortSelect]);

  /* Beim Wechsel der Liste die passenden Felder zeigen - ohne die Karte neu
     zu bauen. Vorher wurde hier die ganze Ansicht neu gezeichnet, wodurch die
     Karte samt Eingaben verschwand und sich nichts mehr speichern liess. */
  function syncFelder() {
    const kind = listSelect.value === '__new__'
      ? (todo.listId ? listKind(todo.listId) : 'tasks')
      : listKind(listSelect.value);
    dated = istDatiert(kind);
    personLabel.textContent = dated ? 'Wer' : 'Für wen';
    dueLabel.textContent = dated ? 'Fällig' : 'Für welchen Tag';
    const ersteOption = personSelect.options[0];
    if (ersteOption) ersteOption.textContent = dated ? '— niemand —' : '🏠 für alle';
    dueWrap.hidden = !(dated || kind === 'postits');
    prioWrap.hidden = !dated;
    repeatWrap.hidden = !dated;
    effortWrap.hidden = !dated;
  }
  listSelect.addEventListener('change', syncFelder);

  const confirmBtn = el('button', { class: 'btn btn-primary', text: 'Passt so' });
  confirmBtn.addEventListener('click', async () => {
    confirmBtn.disabled = true;
    const payload = {
      title: titleInput.value,
      note: noteInput.value.trim(),
      assigneeId: personSelect.value,
    };
    // Nicht sichtbare Felder nicht mitschicken - sonst schriebe man einer
    // Sammlung eine Dauer zu, die sie gar nicht anzeigt.
    if (!dueWrap.hidden) payload.dueDate = dueInput.value;
    if (!prioWrap.hidden) payload.priority = prioSelect.value;
    if (!repeatWrap.hidden) payload.repeat = repeatSelect.value;
    if (!effortWrap.hidden) payload.minutes = Number(effortSelect.value);
    if (listSelect.value === '__new__') {
      if (!newListInput.value.trim()) {
        toast('Bitte der neuen Liste einen Namen geben.', true);
        confirmBtn.disabled = false;
        return;
      }
      payload.newListName = newListInput.value.trim();
      payload.newListEmoji = suggestion.newListEmoji || '📋';
    } else {
      payload.listId = listSelect.value;
    }
    try {
      await api(`/api/todos/${todo.id}/confirm`, 'POST', payload);
      toast(inline ? 'Gespeichert.' : 'Einsortiert.');
      state.editing = null;
      await refresh();
    } catch (error) { toast(error.message, true); confirmBtn.disabled = false; }
  });

  const deleteBtn = el('button', {
    class: 'btn btn-ghost btn-sm', text: inline ? 'Löschen' : 'Verwerfen',
    onclick: async () => {
      if (inline && !confirm(`„${todo.title}“ wirklich löschen?`)) return;
      try {
        await api(`/api/todos/${todo.id}`, 'DELETE');
        state.editing = null;
        await refresh();
      } catch (error) { toast(error.message, true); }
    },
  });

  // Beim nachträglichen Bearbeiten braucht es einen Weg zurück, ohne zu
  // speichern - und die Sicherheitsangabe der Einordnung ist dann vorbei.
  const abbrechen = el('button', {
    class: 'btn btn-ghost btn-sm', text: 'Abbrechen',
    onclick: () => { state.editing = null; render(); },
  });

  const card = el('div', { class: 'card review' }, [
    el('label', { class: 'field' }, [el('span', { text: 'Todo' }), titleInput]),
    el('label', { class: 'field' }, [
      el('span', {}, todo.noteSource === 'model'
        ? [el('span', { class: 'note-tag', text: 'KI' }), ' Notiz — beim Speichern wird sie deine']
        : 'Notiz'),
      noteInput]),
    todo.question ? el('div', { class: 'question', text: `❓ ${todo.question}` }) : null,
    todo.rawInput && todo.rawInput !== todo.title
      ? el('div', { class: 'todo-note', text: `Eingeworfen: „${todo.rawInput}“` }) : null,
    el('div', { class: 'fields' }, [
      el('label', { class: 'field wide' }, [el('span', { text: 'Liste' }), listSelect]),
      newListWrap,
      personWrap,
      dueWrap,
      prioWrap,
      repeatWrap,
      effortWrap,
    ]),
    el('div', { class: 'actions' }, [
      confirmBtn,
      inline ? abbrechen : null,
      el('span', { class: 'spacer' }),
      inline ? null : el('span', {
        class: 'capture-hint',
        text: `${Math.round((todo.confidence || 0) * 100)} % sicher · ${engineName(todo.engine)}`,
      }),
      deleteBtn,
    ]),
  ]);
  syncNewList();
  syncFelder();
  return card;
}

/* ---------- Ansichten ---------- */

function viewInbox() {
  const items = inboxTodos();
  if (!items.length) {
    return el('div', { class: 'empty' }, [
      el('strong', { text: 'Nichts zu bestätigen' }),
      'Alles Eingeworfene wurde sicher einsortiert.',
    ]);
  }
  return el('div', {}, [
    el('p', { class: 'hint', style: 'font-size:13px;color:var(--muted);margin:0 2px 10px',
      text: 'Hier war sich die Einordnung nicht sicher. Kurz prüfen, dann ist es durch.' }),
    ...items.map(reviewCard),
  ]);
}

function viewLists() {
  // Nur Listen, die hier erscheinen sollen. Ein Einkaufszettel oder ein
  // Wunschzettel gehoert nicht Posten fuer Posten in die Gesamtuebersicht -
  // dort will man Aufgaben sehen, nicht Milch und Brot.
  const sichtbar = new Set(state.lists.filter(l => l.inOverview !== false)
                                      .map(l => l.id));
  const items = openTodos().filter(t => !t.listId || sichtbar.has(t.listId));
  if (!items.length) {
    return el('div', { class: 'empty' }, [
      el('strong', { text: 'Alles abgearbeitet' }), 'Nichts Offenes in den Listen.',
    ]);
  }
  const groups = el('div', {});

  /* Zwei Gruppen vorweg, quer über alle Listen: was heute dran ist und was
     in den nächsten Tagen kommt. Nach Listen sortiert zu sein ist richtig,
     wenn man eine Liste abarbeitet - aber nicht, wenn man wissen will, was
     heute ansteht. Dafür müsste man sonst jede Gruppe einzeln durchsehen. */
  const zeichneQuer = t => todoCard(t, { overdue: (daysUntil(t.dueDate) ?? 99) < 0 });
  const nachDatum = (a, b) => (a.dueDate || '').localeCompare(b.dueDate || '');
  for (const [titel, eintraege, leerText] of [
    ['🔴 Überfällig', overdueTodos().filter(isTask).sort(nachDatum), ''],
    ['📌 Heute', todayTodos().sort(nachDatum), ''],
    ['🕒 Bald', baldTodos().sort(nachDatum), ''],
  ]) {
    if (!eintraege.length) continue;
    groups.append(el('section', { class: 'list-group' }, [
      el('div', { class: 'list-head' }, [
        titel,
        el('span', { class: 'count', text: String(eintraege.length) }),
      ]),
      ...eintraege.map(zeichneQuer),
    ]));
  }
  if (groups.childElementCount) {
    groups.append(el('div', { class: 'kind-divider' },
      el('span', { text: 'Nach Listen' })));
  }

  let letzteArt = null;
  for (const list of state.lists.slice()
      .filter(l => l.inOverview !== false)
      .sort((a, b) => {
        const reihenfolge = (state.areas || []).map(x => x.id);
        const rang = k => { const i = reihenfolge.indexOf(k); return i < 0 ? 99 : i; };
        return rang(a.kind) - rang(b.kind) || a.sort - b.sort;
      })) {
    const listItems = items.filter(t => t.listId === list.id);
    if (!listItems.length) continue;
    // Trennlinie, sobald eine neue Art beginnt.
    if (letzteArt !== null && list.kind !== letzteArt) {
      groups.append(el('div', { class: 'kind-divider' },
        el('span', { text: ((state.areas || []).find(a => a.id === list.kind) || {}).name
                           || 'Weiteres' })));
    }
    letzteArt = list.kind;
    const zeichne = t => todoCard(t, { overdue: (daysUntil(t.dueDate) ?? 99) < 0 });
    const { faellig, spaeter } = splitByDue(listItems);
    groups.append(el('section', { class: 'list-group' }, [
      el('div', { class: 'list-head' }, [
        `${list.emoji} ${list.name}`,
        el('span', { class: 'count', text: String(faellig.length || listItems.length) }),
      ]),
      ...faellig.map(zeichne),
      laterBlock(spaeter, zeichne),
    ]));
  }
  const orphans = items.filter(t => !listById(t.listId));
  if (orphans.length) {
    groups.append(el('section', { class: 'list-group' }, [
      el('div', { class: 'list-head' }, ['📥 Ohne Liste',
        el('span', { class: 'count', text: String(orphans.length) })]),
      ...orphans.map(t => todoCard(t)),
    ]));
  }
  return groups;
}

function viewSoon() {
  const items = soonTodos().sort((a, b) => (a.dueDate || '').localeCompare(b.dueDate || ''));
  if (!items.length) {
    return el('div', { class: 'empty' }, [
      el('strong', { text: 'Die nächsten Tage sind frei' }),
      `Nichts fällig in den nächsten ${SOON_DAYS} Tagen.`,
    ]);
  }
  const byDay = new Map();
  for (const todo of items) {
    const key = formatDue(todo.dueDate);
    if (!byDay.has(key)) byDay.set(key, []);
    byDay.get(key).push(todo);
  }
  return el('div', {}, [...byDay.entries()].map(([label, group]) =>
    el('section', { class: 'list-group' }, [
      el('div', { class: 'list-head' }, [label,
        el('span', { class: 'count', text: String(group.length) })]),
      ...group.map(t => todoCard(t)),
    ])));
}

function viewOverdue() {
  const items = overdueTodos().sort((a, b) => (a.dueDate || '').localeCompare(b.dueDate || ''));
  if (!items.length) {
    return el('div', { class: 'empty' }, [
      el('strong', { text: 'Nichts überfällig' }), 'Sauber. 👏',
    ]);
  }
  return el('div', {}, items.map(t => todoCard(t, { overdue: true })));
}



/* ---------- Start ----------
   Eine Übersicht, von der aus man in jede Teilansicht springt: erst was
   drängt, dann wer was hat, dann die Sammlungen ohne Termindruck. */

/* Schritte innerhalb der App im Verlauf des Browsers vermerken.

   Ohne das führt der Zurück-Knopf - und am Telefon die Zurück-Geste - aus der
   App heraus auf die zuvor besuchte Website, obwohl man nur eine Ebene höher
   wollte. Jeder Wechsel von Ansicht oder Bereich legt deshalb einen Eintrag
   an; der Browser gibt ihn beim Zurückgehen zurück, und die App stellt ihn
   wieder her. Die Adresse bleibt dabei unverändert. */
function pushStep() {
  try {
    history.pushState({ tab: state.tab, focus: state.focus }, '');
  } catch { /* in manchen eingebetteten Ansichten nicht erlaubt */ }
}

function rememberStep() {
  try {
    history.replaceState({ tab: state.tab, focus: state.focus }, '');
  } catch { /* egal */ }
}

/* Der Titel oben links führt nach Hause - das erwartet man von einer
   Kopfzeile, und es ist am Telefon der kürzeste Weg mit dem Daumen. */
function setupHomeLink() {
  const link = document.getElementById('home-link');
  if (!link) return;
  link.addEventListener('click', () => {
    if (state.tab === 'start' && !state.focus) {
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    state.tab = 'start';
    state.focus = null;
    pushStep();
    render();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
}

function setupHistory() {
  rememberStep();
  window.addEventListener('popstate', event => {
    const schritt = event.state;
    if (!schritt) return;          // vor der App - der Browser verlässt sie
    state.tab = schritt.tab || 'start';
    state.focus = schritt.focus || null;
    render();
    window.scrollTo({ top: 0 });
  });
}

function openFocus(kind, id, from) {
  state.focus = { kind, id, from };
  pushStep();
  render();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function goHome() {
  state.focus = null;
  pushStep();
  render();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

/* Pfad als Brotkrumen: zeigt, wo man ist, und lässt jede Stufe anspringen.
   Das übliche Muster für geschachtelte Listen - verlässlicher als ein
   einzelner Zurück-Knopf, weil der Weg nach Hause immer sichtbar bleibt. */
function breadcrumb(trail) {
  const parts = [];
  trail.forEach((step, index) => {
    const last = index === trail.length - 1;
    if (index > 0) parts.push(el('span', { class: 'crumb-sep', text: '›' }));
    parts.push(last
      ? el('span', { class: 'crumb current', text: step.label })
      : el('button', { class: 'crumb', type: 'button', text: step.label,
                       onclick: step.go }));
  });
  return el('nav', { class: 'crumbs', 'aria-label': 'Pfad' }, parts);
}

/* Direkt in dieser Liste anlegen - ohne Sprachmodell, ohne Wartezeit.
   Wer schon in der richtigen Liste steht, soll nicht den Umweg über die
   Einordnung gehen müssen; das kostet sonst bei jedem Eintrag Geld. */
function quickAdd(listId) {
  const list = listById(listId);
  const bereich = list ? (state.areas || []).find(a => a.id === list.kind) : null;
  const dated = bereich ? bereich.dated : true;

  const istNotiz = list && list.kind === POSTIT_AREA;
  const input = el('input', {
    type: 'text', id: 'quick-add-input', autocomplete: 'off',
    placeholder: istNotiz ? 'Notiz …'
               : dated ? 'Direkt hinzufügen …' : 'Auf die Liste setzen …',
  });

  // Nur bei Notizen: der Tag, an dem sie auf der Startseite erscheinen soll.
  const dateInput = istNotiz
    ? el('input', { type: 'date', class: 'quick-date', title: 'Für welchen Tag?' })
    : null;

  const personSelect = state.people.length
    ? el('select', { class: 'quick-person' }, [
        el('option', { value: '', text: dated ? '🙋 wer?' : '🏠 für alle' }),
        ...state.people.map(person => el('option', {
          value: person.id, text: `${person.emoji} ${person.name}`,
        })),
      ])
    : null;

  /* `weiter` heißt: nach dem Anlegen gleich die Bearbeitungskarte öffnen.

     Schnelles Eintippen und das Vergeben von Frist, Dauer und Wichtigkeit
     sind zwei verschiedene Bedürfnisse. Alle Felder dauerhaft anzuzeigen
     macht das Eintippen schwerfällig; sie wegzulassen heißt, erst anlegen
     und dann suchen zu müssen. Der zweite Knopf erledigt beides in einem
     Zug - und nur, wenn man ihn drückt. */
  const anlegen = async (weiter) => {
    const title = input.value.trim();
    if (!title) return;
    input.disabled = true;
    try {
      const antwort = await api('/api/todos', 'POST', {
        title, listId,
        assigneeId: personSelect ? personSelect.value : '',
        dueDate: dateInput ? dateInput.value : '',
        horizon: state.horizon,
      });
      if (dateInput) dateInput.value = '';
      input.value = '';
      if (weiter && antwort && antwort.todo) state.editing = antwort.todo.id;
      await refresh();
      // Nach dem Neuzeichnen weitertippen können - beim Einkaufszettel
      // schreibt man selten nur eine Zeile.
      const again = document.getElementById('quick-add-input');
      if (again && !weiter) again.focus();
    } catch (error) {
      toast(error.message, true);
      input.disabled = false;
    }
  };

  return el('form', {
    class: 'quick-add',
    onsubmit: (event) => { event.preventDefault(); anlegen(false); },
  }, [
    input,
    dateInput,
    personSelect,
    el('button', { class: 'btn btn-primary btn-sm', type: 'submit', text: '+' }),
    // Nur dort, wo es etwas zu vergeben gibt: ein Wunschzettel kennt weder
    // Frist noch Dauer.
    dated ? el('button', {
      class: 'btn btn-sm quick-more', type: 'button', text: '＋⋯',
      title: 'Anlegen und gleich Frist, Dauer und Wichtigkeit vergeben',
      'aria-label': 'Anlegen und bearbeiten',
      onclick: () => anlegen(true),
    }) : null,
  ]);
}

function tile(label, value, detail, tone, onclick) {
  return el('button', {
    class: 'tile tile-action' + (tone ? ' ' + tone : ''),
    type: 'button', onclick,
  }, [
    el('div', { class: 'tile-value', text: String(value) }),
    el('div', { class: 'tile-label', text: label }),
    detail ? el('div', { class: 'tile-detail', text: detail }) : null,
  ]);
}

/* „Ich bin bei …" - die Einkaufszettel quer durchsehen.

   Die Zettel sind nach Anlass geordnet: täglicher Bedarf, Baumarkt,
   persönlich. Im Laden fragt man umgekehrt - nicht „was steht auf dem
   Baumarktzettel", sondern „was von allem brauche ich, das es hier gibt".
   Shampoo steht beim täglichen Bedarf, ist aber bei Rossmann zu haben.

   Gefragt wird das Modell, statt eine Tabelle „welcher Laden führt was" zu
   pflegen. Kennt es den Laden nicht, sagt es das, statt zu raten. */
function ladenSuche() {
  const feld = el('input', {
    type: 'text', placeholder: 'z. B. Rossmann, Edeka, Bauhaus …',
    'aria-label': 'In welchem Geschäft bist du?', autocomplete: 'off',
  });
  const ausgabe = el('div', { class: 'laden-ergebnis', hidden: true });

  const suche = async (name) => {
    const laden = (name || feld.value).trim();
    if (!laden) { feld.focus(); return; }
    feld.value = laden;
    knopf.disabled = true;
    const vorher = knopf.textContent;
    knopf.textContent = 'Sieht nach …';
    try {
      const r = await api('/api/shopping/here', 'POST', { shop: laden });
      zeigeLaden(ausgabe, r);
      // Die Zettel selbst sind unverändert - nur die Ladenliste wächst.
      state.settings = { ...state.settings, shops: [laden, ...zuletztLaeden()
        .filter(l => l.toLowerCase() !== laden.toLowerCase())].join(',') };
    } catch (error) {
      ausgabe.hidden = false;
      ausgabe.textContent = '';
      ausgabe.append(el('p', { class: 'hint', text: error.message }));
    } finally {
      knopf.disabled = false;
      knopf.textContent = vorher;
    }
  };

  const knopf = el('button', {
    class: 'btn btn-sm', type: 'submit', text: 'Nachsehen',
  });

  const zuletzt = zuletztLaeden().slice(0, 5);

  return el('div', { class: 'laden-box' }, [
    el('form', {
      class: 'laden-zeile',
      onsubmit: (event) => { event.preventDefault(); suche(); },
    }, [
      el('span', { class: 'laden-marke', text: '📍' }),
      el('span', { class: 'laden-text', text: 'Ich bin bei' }),
      feld,
      knopf,
    ]),
    zuletzt.length
      ? el('div', { class: 'laden-zuletzt' }, zuletzt.map(name => el('button', {
          class: 'chip chip-knopf', type: 'button', text: name,
          onclick: () => suche(name),
        })))
      : null,
    ausgabe,
  ]);
}

function zuletztLaeden() {
  return String((state.settings || {}).shops || '')
    .split(',').map(s => s.trim()).filter(Boolean);
}

function zeigeLaden(ziel, r) {
  ziel.hidden = false;
  ziel.textContent = '';

  // Manche Modelle geben als Art den Ladennamen zurück - dann nicht doppeln.
  const art = (r.kind || '').trim();
  const kopf = art && art.toLowerCase() !== 'unbekannt'
               && art.toLowerCase() !== r.shop.toLowerCase()
    ? `${r.shop} — ${art}` : r.shop;
  ziel.append(el('div', { class: 'laden-kopf', text: kopf }));

  if (r.hint) ziel.append(el('p', { class: 'hint', text: r.hint }));

  if (!r.hits.length && !r.maybe.length) {
    ziel.append(el('p', { class: 'hint', text: 'Nichts von den Zetteln passt hierher.' }));
    return;
  }

  const zeile = (todo) => el('div', { class: 'heute-zeile' }, [
    hakenKnopf(todo, 'check check-klein'),
    el('span', { class: 'laden-posten' }, [
      todo.title,
      // Wo es im Laden steht - im Gang nützlicher als der Zettelname.
      todo.abteilung
        ? el('span', { class: 'laden-abteilung', text: todo.abteilung })
        : null,
    ]),
  ]);

  if (r.hits.length) ziel.append(...r.hits.map(zeile));
  if (r.maybe.length) {
    ziel.append(el('div', { class: 'laden-vielleicht' },
      el('span', { text: 'vielleicht auch' })));
    ziel.append(...r.maybe.map(zeile));
  }
  if (r.total > r.checked) {
    ziel.append(el('p', { class: 'hint',
      text: `Geprüft wurden die ersten ${r.checked} von ${r.total} Posten.` }));
  }
}

/* ---------- Schmerztagebuch ---------- */

/* Eine visuelle Analogskala (VAS), wie sie in der Schmerzmedizin üblich ist:
   0 heißt kein Schmerz, 10 der stärkste vorstellbare. Die Werte sind darum
   nicht frei wählbar und die Skala nicht einstellbar - sonst lässt sich der
   Verlauf später mit nichts vergleichen, auch nicht mit dem, was eine Praxis
   erhebt.

   Jeder Eintrag bekommt Datum und Uhrzeit. Der Zeitstempel kommt vom Gerät,
   damit man einen Schmerz auch nachtragen kann, ohne dass er auf „jetzt"
   rutscht. */
const VAS_MIN = 0;
const VAS_MAX = 10;

/* Grün nach Rot über den gelben Bereich - der gewohnte Verlauf einer solchen
   Skala. Der Farbton läuft von 130° (Grün) auf 0° (Rot).

   Die Farbe sagt den Wert nie allein: Neben jedem Balken steht die Zahl.
   Das ist nicht nur eine Frage der Rot-Grün-Sehschwäche - eine Farbe lässt
   sich auch schlecht erinnern, eine Zahl schon. */
function vasTon(wert) {
  const stufe = Math.max(VAS_MIN, Math.min(VAS_MAX, Number(wert) || 0));
  return Math.round(130 - stufe * 13);
}

/* Für Flächen ohne Schrift darauf: Balken, Säulen, Ränder. */
function vasFarbe(wert) {
  return `hsl(${vasTon(wert)} 68% 42%)`;
}

/* Dieselbe Skala, nur dunkler - für die Flächen, auf denen die weiße Zahl
   steht.

   Nachgerechnet: Bei 42 % Helligkeit erreicht Weiß im gelbgrünen Bereich der
   Skala nur 2,3:1, nötig sind 3:1 für große fette Schrift. Gerade die Mitte
   der Skala wäre also am schlechtesten zu lesen gewesen. Bei 33 % besteht
   jede der elf Stufen mit Luft (schlechteste 3,5:1 bei VAS 5).

   Die Balken bleiben bei 42 %: Dort steht keine Schrift drauf, und der
   Verlauf soll kräftig bleiben. */
function vasFarbeTief(wert) {
  return `hsl(${vasTon(wert)} 70% 33%)`;
}

/* Worte zur Zahl. Eine 6 allein sagt in drei Monaten nichts mehr. */
const VAS_WORTE = [
  'kein Schmerz', 'kaum spürbar', 'leicht', 'gut erträglich', 'unangenehm',
  'mittel', 'deutlich', 'stark', 'sehr stark', 'kaum auszuhalten',
  'stärkster vorstellbarer',
];

function vasWort(wert) {
  return VAS_WORTE[Math.max(VAS_MIN, Math.min(VAS_MAX, Number(wert) || 0))] || '';
}

/* Die Mittel, die hier vorkommen - mit ihren üblichen Stärken.

   Die Liste ist eine Abkürzung, keine Beschränkung: Unten gibt es ein
   freies Feld für alles andere, und der Server nimmt jeden Namen an. Ein
   Tagebuch, das nur fünf Mittel kennt, wäre beim sechsten wertlos.

   Die Mengen sind die handelsüblichen Stärken, damit Eintragen zwei Tipps
   bleibt. Sie sind ausdrücklich keine Empfehlung: Diese App hält fest, was
   genommen wurde - sie sagt nicht, was zu nehmen ist. Darum gibt es hier
   auch keine Tageshöchstmengen und keine Warnungen. Das gehört in die
   Packungsbeilage und in die Sprechstunde, nicht in einen Familienkalender. */
const MEDIKAMENTE = [
  { id: 'ibuprofen', name: 'Ibuprofen', kurz: 'Ibu',
    dosen: [[400, 'mg'], [200, 'mg'], [600, 'mg'], [800, 'mg']] },
  { id: 'paracetamol', name: 'Paracetamol', kurz: 'Para',
    dosen: [[500, 'mg'], [1000, 'mg']] },
  { id: 'naproxen', name: 'Naproxen', kurz: 'Naproxen',
    dosen: [[250, 'mg'], [500, 'mg']] },
  { id: 'tilidin', name: 'Tilidin', kurz: 'Tilidin',
    dosen: [[50, 'mg'], [100, 'mg'], [150, 'mg'], [200, 'mg'], [20, 'Tropfen']] },
  { id: 'novalgin', name: 'Novalgin', kurz: 'Novalgin',
    dosen: [[500, 'mg'], [1000, 'mg'], [20, 'Tropfen'], [40, 'Tropfen']] },
];

/* Für welchen Zeitpunkt der nächste Eintrag gilt - und ob er als
   nachgetragen zu vermerken ist.

   Der Normalfall ist „jetzt": Man sitzt mit den Schmerzen da und trägt ein.
   Nachtragen muss aber gehen, denn im schlimmsten Moment greift niemand zum
   Telefon. Nur darf das eine nicht als das andere durchgehen - ein Wert, der
   drei Tage später aus dem Gedächtnis kommt, ist nicht dasselbe wie einer vom
   Moment. Deshalb hängt am Eintrag ein Vermerk, und der steht auch im
   Tagebuch und in der Sicherung.

   Der Schalter gilt für beides, Schmerz und Mittel: „Gestern Abend war es
   eine 8 und ich habe Tilidin genommen" ist ein Vorgang, nicht zwei. */
function painZeitAngabe() {
  if (!state.painNachtrag || !state.painZeitpunkt) {
    return { recordedAt: painJetztStempel(), retro: false };
  }
  // datetime-local liefert 16 Zeichen ohne Sekunden.
  const wann = state.painZeitpunkt.length === 16
    ? state.painZeitpunkt + ':00'
    : state.painZeitpunkt;
  return { recordedAt: wann, retro: true };
}

/* Der Eintrag gilt als nachgetragen, solange der Schalter steht - auch wenn
   die eingestellte Zeit zufällig die jetzige ist. Das ist eine Aussage des
   Menschen, keine Rechnung: Nur er weiß, ob er aus dem Moment oder aus der
   Erinnerung schreibt. */
function painZeitSchalter() {
  const jetztKnopf = el('button', {
    type: 'button',
    class: 'zeit-knopf' + (state.painNachtrag ? '' : ' an'),
    text: 'Jetzt',
    onclick: () => {
      state.painNachtrag = false;
      render();
    },
  });
  const nachKnopf = el('button', {
    type: 'button',
    class: 'zeit-knopf' + (state.painNachtrag ? ' an' : ''),
    text: 'Nachtragen',
    onclick: () => {
      state.painNachtrag = true;
      // Mit der jetzigen Zeit vorbelegen: so muss man nur daran drehen,
      // statt alles einzugeben.
      if (!state.painZeitpunkt) state.painZeitpunkt = painJetztStempel().slice(0, 16);
      render();
    },
  });

  return el('div', { class: 'zeit-box' + (state.painNachtrag ? ' ist-nachtrag' : '') }, [
    el('div', { class: 'zeit-wahl', role: 'group', 'aria-label': 'Zeitpunkt' }, [
      jetztKnopf, nachKnopf,
    ]),
    state.painNachtrag
      ? el('div', { class: 'zeit-feld' }, [
          el('input', {
            type: 'datetime-local', id: 'zeit-wann', class: 'zeit-wann',
            value: state.painZeitpunkt,
            'aria-label': 'Wann war das?',
            // Nur mitschreiben, nicht neu zeichnen - sonst verliert das Feld
            // unter dem Finger den Fokus.
            oninput: event => { state.painZeitpunkt = event.target.value; },
          }),
          el('span', { class: 'zeit-vermerk',
            text: 'wird als nachgetragen vermerkt' }),
        ])
      : null,
  ]);
}

function medEintraege() {
  return (state.meds || []).filter(e => !state.me || !e.personId
                                        || e.personId === state.me);
}

/* Menge und Einheit, wie man sie hinschreibt: „400 mg", „20 Tropfen".
   Ganze Zahlen ohne Nachkomma, Bruchteile mit Komma (halbe Tabletten). */
function medMenge(eintrag) {
  const zahl = Number(eintrag.dose) || 0;
  if (!zahl) return eintrag.unit === 'mg' ? '' : eintrag.unit;
  const text = Number.isInteger(zahl) ? String(zahl)
                                      : String(Math.round(zahl * 100) / 100).replace('.', ',');
  return `${text} ${eintrag.unit}`;
}

async function medEintragen(name, menge, einheit) {
  const zeit = painZeitAngabe();
  try {
    await api('/api/meds', 'POST', {
      drug: name, dose: menge, unit: einheit,
      personId: state.me || '',
      loggedAt: painJetztStempel(),
      ...zeit,
    });
    state.medOffen = '';
    toast(`${name} ${menge} ${einheit} eingetragen`
        + (zeit.retro ? ' (nachgetragen).' : '.'));
    await refresh();
  } catch (fehler) {
    toast(fehler.message, true);
  }
}

function painEintraege() {
  return (state.pain || []).filter(e => !state.me || !e.personId
                                        || e.personId === state.me);
}

/* Die Körperstellen, die schon einmal vorkamen - als Knöpfe statt als
   Tippaufgabe. Wer ein Tagebuch führt, hat meist zwei oder drei Stellen,
   und die will man nicht jedes Mal buchstabieren. */
function painOrte() {
  const gesehen = [];
  for (const eintrag of painEintraege()) {
    if (eintrag.place && !gesehen.includes(eintrag.place)) gesehen.push(eintrag.place);
    if (gesehen.length >= 6) break;
  }
  return gesehen;
}

function painZeit(wert) {
  const zeit = new Date(wert);
  if (Number.isNaN(zeit.getTime())) return { tag: '', uhr: '' };
  return {
    tag: zeit.toLocaleDateString('de-DE',
      { weekday: 'short', day: '2-digit', month: 'short' }),
    uhr: zeit.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }),
  };
}

/* Örtliche Zeit im Format, das die Datenbank erwartet. `toISOString` wäre
   falsch: Das rechnet auf UTC um, und ein Eintrag von 00:30 landete dann auf
   dem Vortag. */
function painJetztStempel() {
  const jetzt = new Date();
  const zwei = n => String(n).padStart(2, '0');
  return `${jetzt.getFullYear()}-${zwei(jetzt.getMonth() + 1)}-${zwei(jetzt.getDate())}`
       + `T${zwei(jetzt.getHours())}:${zwei(jetzt.getMinutes())}:${zwei(jetzt.getSeconds())}`;
}

function painSchnitt(eintraege) {
  if (!eintraege.length) return null;
  const summe = eintraege.reduce((s, e) => s + (Number(e.value) || 0), 0);
  return Math.round((summe / eintraege.length) * 10) / 10;
}

/* Der Verlauf als schmale Balken - einer je Eintrag, der jüngste rechts.

   Kein Liniendiagramm: Die Einträge liegen zeitlich unregelmäßig, und eine
   Linie würde zwischen zwei Messungen einen Verlauf behaupten, den niemand
   beobachtet hat. Balken sagen nur, was gemessen wurde. */
function painVerlauf(eintraege) {
  if (eintraege.length < 2) return null;
  const grenze = Date.now() - state.painTage * 24 * 3600 * 1000;
  const fenster = eintraege
    .filter(e => new Date(e.recordedAt).getTime() >= grenze)
    .slice()
    .reverse();
  if (fenster.length < 2) return null;

  const schnitt = painSchnitt(fenster);
  // Wie oft in derselben Zeit etwas genommen wurde - die Zahl gehört neben
  // den Schnitt, sonst liest man einen niedrigen Schnitt als „ging besser",
  // obwohl er erkauft war.
  const einnahmen = medEintraege()
    .filter(e => new Date(e.recordedAt).getTime() >= grenze).length;
  return el('div', { class: 'vas-verlauf' }, [
    el('div', { class: 'vas-verlauf-kopf' }, [
      el('span', { text: `Verlauf · ${state.painTage} Tage` }),
      einnahmen
        ? el('span', { class: 'vas-einnahmen',
            text: `💊 ${einnahmen}` })
        : null,
      el('span', { class: 'vas-schnitt', text: `⌀ ${String(schnitt).replace('.', ',')}` }),
      el('select', {
        'aria-label': 'Zeitspanne des Verlaufs',
        onchange: event => { state.painTage = Number(event.target.value); render(); },
      }, [7, 14, 30, 90].map(tage => el('option', {
        value: String(tage), selected: state.painTage === tage,
        text: `${tage} Tage`,
      }))),
    ]),
    el('div', { class: 'vas-balken' }, fenster.map(eintrag => {
      const { tag, uhr } = painZeit(eintrag.recordedAt);
      return el('span', {
        class: 'vas-balken-saeule',
        // Auch 0 muss sichtbar bleiben, sonst sieht ein schmerzfreier Tag
        // aus wie ein fehlender Eintrag.
        style: `height:${8 + (Number(eintrag.value) || 0) * 9}%;`
             + `background:${vasFarbe(eintrag.value)}`,
        title: `${tag} ${uhr} — ${eintrag.value} von 10 (${vasWort(eintrag.value)})`
             + (eintrag.place ? ` · ${eintrag.place}` : ''),
      });
    })),
    el('div', { class: 'vas-verlauf-fuss' }, [
      el('span', { text: '0 = kein Schmerz' }),
      el('span', { text: '10 = stärkster' }),
    ]),
  ]);
}

async function painEintragen() {
  const zeit = painZeitAngabe();
  const nutzlast = {
    value: state.painWert,
    place: state.painOrt,
    note: (document.getElementById('vas-notiz') || {}).value || '',
    personId: state.me || '',
    loggedAt: painJetztStempel(),
    ...zeit,
  };
  try {
    await api('/api/pain', 'POST', nutzlast);
    const notiz = document.getElementById('vas-notiz');
    if (notiz) notiz.value = '';
    toast(`Eingetragen: ${nutzlast.value} von 10`
        + (zeit.retro ? ' (nachgetragen).' : '.'));
    await refresh();
  } catch (fehler) {
    toast(fehler.message, true);
  }
}

/* Die Zeile unter der Überschrift: was überhaupt drinsteht. */
function painKopfzeile(messungen, mittel) {
  if (!messungen.length && !mittel.length) {
    return 'Stärke, Mittel, Datum und Uhrzeit — festgehalten für die '
         + 'nächste Sprechstunde.';
  }
  const teile = [];
  if (messungen.length) {
    teile.push(`${messungen.length} ${messungen.length === 1 ? 'Messung' : 'Messungen'}`);
    const schnitt = painSchnitt(messungen);
    if (schnitt !== null) teile.push(`Mittel ${String(schnitt).replace('.', ',')} von 10`);
  }
  if (mittel.length) {
    teile.push(`${mittel.length} ${mittel.length === 1 ? 'Einnahme' : 'Einnahmen'}`);
  }
  // Wie viel davon aus der Erinnerung kommt, gehört in die Übersicht: Es
  // sagt, wie belastbar das Ganze ist.
  const nachgetragen = [...messungen, ...mittel].filter(e => e.retro).length;
  if (nachgetragen) teile.push(`${nachgetragen} nachgetragen`);
  return teile.join(' · ');
}

/* Der Vermerk am Eintrag. Ohne ihn liesse sich ein nachgetragener Wert
   nicht von einem im Moment gemessenen unterscheiden - und genau das ist
   der Unterschied, der zaehlt. */
function nachtragMarke(eintrag) {
  if (!eintrag.retro) return null;
  const notiert = eintrag.loggedAt ? painZeit(eintrag.loggedAt) : null;
  return el('span', {
    class: 'chip nachtrag',
    text: 'nachgetragen',
    title: notiert
      ? `Später eingetragen: ${notiert.tag} um ${notiert.uhr}`
      : 'Nicht im Moment festgehalten, sondern später eingetragen',
  });
}

function wegKnopf(pfad) {
  return el('button', {
    type: 'button', class: 'vas-weg', title: 'Eintrag löschen', text: '×',
    onclick: async () => {
      try {
        await api(pfad, 'DELETE');
        toast('Eintrag gelöscht.');
        await refresh();
      } catch (fehler) { toast(fehler.message, true); }
    },
  });
}

/* Was oben am Tag steht: der Schnitt der Messungen und was genommen wurde.

   Zusammengefasst je Mittel und Einheit - „Ibu 800 mg" heißt dann zwei mal
   400. Unterschiedliche Einheiten werden nicht verrechnet: 500 mg und 20
   Tropfen Novalgin stehen getrennt, weil sie nicht dasselbe sind.

   Das ist eine Tagessumme, keine Beurteilung. Die App nennt keine
   Höchstmengen und warnt nicht - das wäre ein Ratschlag, und den gibt sie
   nicht. */
function tagesBilanz(messungen, mittel) {
  const teile = [];
  const schnitt = painSchnitt(messungen);
  if (schnitt !== null) teile.push(`⌀ ${String(schnitt).replace('.', ',')}`);

  const summen = [];
  for (const eintrag of mittel) {
    const schluessel = `${eintrag.drug}|${eintrag.unit}`;
    let posten = summen.find(s => s.schluessel === schluessel);
    if (!posten) {
      posten = { schluessel, name: eintrag.drug, einheit: eintrag.unit, menge: 0 };
      summen.push(posten);
    }
    posten.menge += Number(eintrag.dose) || 0;
  }
  for (const posten of summen) {
    const kurz = (MEDIKAMENTE.find(m => m.name === posten.name) || {}).kurz
              || posten.name;
    teile.push(posten.menge
      ? `${kurz} ${Number.isInteger(posten.menge) ? posten.menge
          : String(Math.round(posten.menge * 100) / 100).replace('.', ',')} ${posten.einheit}`
      : kurz);
  }
  return teile.join(' · ');
}

/* Der Kasten für die Einnahmen.

   Zwei Tipps: Mittel antippen, Menge antippen - eingetragen. Die Mengen
   erscheinen erst nach dem ersten Tipp, sonst stünden hier zwanzig Knöpfe
   gleichzeitig und man träfe auf dem Telefon den falschen.

   Die Uhrzeit setzt die App. Wer nachträgt, korrigiert sie nicht - dafür
   gibt es das freie Feld unten mit eigener Zeitangabe. */
function medKasten() {
  const zeilen = MEDIKAMENTE.map(mittel => {
    const offen = state.medOffen === mittel.id;
    const kopf = el('button', {
      type: 'button', class: 'med-name' + (offen ? ' an' : ''),
      'aria-expanded': String(offen),
      onclick: () => {
        state.medOffen = offen ? '' : mittel.id;
        render();
      },
    }, [
      el('span', { text: mittel.name }),
      el('span', { class: 'med-pfeil', 'aria-hidden': 'true', text: offen ? '▾' : '›' }),
    ]);

    return el('div', { class: 'med-zeile' }, [
      kopf,
      offen
        ? el('div', { class: 'med-dosen' }, mittel.dosen.map(([menge, einheit]) =>
            el('button', {
              type: 'button', class: 'med-dosis',
              text: `${menge} ${einheit}`,
              onclick: () => medEintragen(mittel.name, menge, einheit),
            })))
        : null,
    ]);
  });

  /* Alles andere - und Nachträge mit eigener Uhrzeit. */
  const andersName = el('input', {
    type: 'text', class: 'med-frei-name', placeholder: 'anderes Mittel',
    maxlength: '60', id: 'med-frei-name',
  });
  const andersMenge = el('input', {
    type: 'text', class: 'med-frei-menge', placeholder: 'Menge',
    maxlength: '10', id: 'med-frei-menge', inputmode: 'decimal',
  });
  const andersEinheit = el('select', { class: 'med-frei-einheit',
    'aria-label': 'Einheit' },
    ['mg', 'Tropfen', 'Tablette', 'ml'].map(e =>
      el('option', { value: e, text: e })));

  // Kein eigenes Zeitfeld mehr: Der Zeitpunkt steht oben und gilt für
  // Schmerz und Mittel gleichermaßen. Zwei Stellen, an denen sich die Zeit
  // einstellen lässt, wären zwei Gelegenheiten, die falsche zu erwischen.
  const eintragen = async () => {
    const name = andersName.value.trim();
    if (!name) { toast('Welches Mittel war es?', true); return; }
    const zeit = painZeitAngabe();
    try {
      await api('/api/meds', 'POST', {
        drug: name,
        dose: Number(andersMenge.value.replace(',', '.')) || 0,
        unit: andersEinheit.value,
        personId: state.me || '',
        loggedAt: painJetztStempel(),
        ...zeit,
      });
      toast(`${name} eingetragen` + (zeit.retro ? ' (nachgetragen).' : '.'));
      await refresh();
    } catch (fehler) { toast(fehler.message, true); }
  };
  andersName.addEventListener('keydown', e => { if (e.key === 'Enter') eintragen(); });
  andersMenge.addEventListener('keydown', e => { if (e.key === 'Enter') eintragen(); });

  return el('section', { class: 'med-box' }, [
    el('div', { class: 'med-kopf' }, [
      el('span', { class: 'med-frage',
        text: state.painNachtrag
          ? '💊 Schmerzmittel — für den Zeitpunkt oben'
          : '💊 Schmerzmittel genommen?' }),
    ]),
    el('div', { class: 'med-liste' }, zeilen),
    el('details', { class: 'med-anders' }, [
      el('summary', { text: 'Anderes Mittel oder nachtragen' }),
      el('div', { class: 'med-frei' }, [
        andersName, andersMenge, andersEinheit,
        el('button', { type: 'button', class: 'btn btn-sm med-frei-knopf',
                       text: 'Eintragen', onclick: eintragen }),
      ]),
      el('p', { class: 'hint',
        text: state.painNachtrag
          ? 'Gilt für den oben eingestellten Zeitpunkt.'
          : 'Gilt für jetzt — zum Nachtragen oben auf „Nachtragen" stellen.' }),
    ]),
    el('p', { class: 'hint',
      text: 'Festgehalten wird, was genommen wurde — die App gibt keine '
          + 'Dosierungshinweise.' }),
  ]);
}

/* Zyklus mitführen - nur, wenn die Person das eingeschaltet hat.

   Standardmäßig aus: Ein Schmerztagebuch gehört nicht jedem, und ein Knopf
   „Periode beginnt" hat in einem fremden Tagebuch nichts zu suchen. Die
   Angabe hängt darum an der Person, nicht am Gerät - wer sich an einem
   anderen Telefon anmeldet, findet sie dort wieder.

   Warum überhaupt: Bei manchen Beschwerden hängt die Stärke am Zyklus, und
   das sieht man erst, wenn beides nebeneinander aufgeschrieben ist. Aus
   Beginn, Ende und Eisprung lassen sich Zyklustag und Phase ableiten; mehr
   braucht der Bericht nicht. */
const ZYKLUS_MARKEN = [
  { id: 'periode', name: 'Periode beginnt', zeichen: '🔴' },
  { id: 'periode_ende', name: 'Periode endet', zeichen: '⚪' },
  { id: 'eisprung', name: 'Eisprung', zeichen: '🥚' },
];

function zyklusEintraege() {
  return (state.cycle || []).filter(e => !state.me || !e.personId
                                         || e.personId === state.me);
}

function michSelbst() {
  return state.people.find(p => p.id === state.me) || null;
}

async function zyklusEintragen(art) {
  const zeit = painZeitAngabe();
  const name = (ZYKLUS_MARKEN.find(m => m.id === art) || {}).name || art;
  try {
    await api('/api/cycle', 'POST', {
      kind: art, personId: state.me || '',
      loggedAt: painJetztStempel(), ...zeit,
    });
    toast(`${name} eingetragen` + (zeit.retro ? ' (nachgetragen).' : '.'));
    await refresh();
  } catch (fehler) { toast(fehler.message, true); }
}

async function zyklusUmschalten(an) {
  const ich = michSelbst();
  if (!ich) { toast('Dafür musst du oben sagen, wer du bist.', true); return; }
  try {
    await api(`/api/people/${ich.id}`, 'PATCH', { cycle: an });
    await refresh();
  } catch (fehler) { toast(fehler.message, true); }
}

function zyklusKasten() {
  const ich = michSelbst();
  if (!ich) return null;

  if (!ich.cycle) {
    // Unauffällig: ein Satz zum Aufklappen, kein Kasten.
    return el('details', { class: 'zyklus-aus' }, [
      el('summary', { text: 'Zyklus mitführen' }),
      el('p', { class: 'hint',
        text: 'Trägt Periode und Eisprung mit ein. Der Bericht zeigt dann, '
            + 'wie der Schmerz über den Zyklus verläuft. Nur für dich — '
            + 'andere sehen diese Knöpfe nicht.' }),
      el('button', {
        type: 'button', class: 'btn btn-sm', text: 'Einschalten',
        onclick: () => zyklusUmschalten(true),
      }),
    ]);
  }

  const letzte = zyklusEintraege();
  const letzterStart = letzte.find(e => e.kind === 'periode');
  let stand = 'noch nichts eingetragen';
  if (letzterStart) {
    const tage = Math.floor(
      (Date.now() - new Date(letzterStart.recordedAt).getTime()) / 86400000);
    stand = `Zyklustag ${tage + 1} · Beginn ${painZeit(letzterStart.recordedAt).tag}`;
  }

  return el('section', { class: 'zyklus-box' }, [
    el('div', { class: 'zyklus-kopf' }, [
      el('span', { class: 'zyklus-frage', text: '🌙 Zyklus' }),
      el('span', { class: 'zyklus-stand', text: stand }),
    ]),
    el('div', { class: 'zyklus-knoepfe' }, ZYKLUS_MARKEN.map(marke =>
      el('button', {
        type: 'button', class: 'zyklus-knopf',
        onclick: () => zyklusEintragen(marke.id),
      }, [
        el('span', { 'aria-hidden': 'true', text: marke.zeichen }),
        el('span', { text: marke.name }),
      ]))),
    el('details', { class: 'zyklus-liste' }, [
      el('summary', { text: `Eingetragene Marken (${letzte.length})` }),
      letzte.length
        ? el('div', {}, letzte.slice(0, 20).map(eintrag => {
            const { tag, uhr } = painZeit(eintrag.recordedAt);
            const marke = ZYKLUS_MARKEN.find(m => m.id === eintrag.kind) || {};
            return el('div', { class: 'zyklus-zeile' }, [
              // Eigene Klasse, nicht die des Tagebuchs: Die Zyklusliste ist
              // eine andere Sache und soll sich getrennt gestalten lassen.
              el('span', { class: 'zyklus-datum', text: tag }),
              el('span', { class: 'zyklus-art',
                text: `${marke.zeichen || ''} ${marke.name || eintrag.kind}` }),
              eintrag.retro ? nachtragMarke(eintrag) : null,
              el('span', { class: 'zyklus-uhr', text: uhr }),
              wegKnopf(`/api/cycle/${eintrag.id}`),
            ]);
          }))
        : el('p', { class: 'hint', text: 'Noch keine Marke eingetragen.' }),
      el('button', {
        type: 'button', class: 'btn btn-sm btn-quiet', text: 'Zyklus nicht mehr mitführen',
        onclick: () => zyklusUmschalten(false),
      }),
    ]),
  ]);
}

/* Das Tagebuch aus der App herausholen.

   Zwei Formate, weil zwei Zwecke: Die CSV-Datei ist der Rohstoff für eine
   Tabellenkalkulation. Das PDF ist das, was man in eine Sprechstunde
   mitnimmt - ausgewertet, mit Verteilungen über Tag und Woche, dem
   Vergleich vor und nach einer Einnahme und, falls eingetragen, dem
   Zyklus.

   Je Person, nicht für alle zusammen: Zwei Menschen in einem Bericht
   ergäben Mittelwerte, die niemandem gehören. */
function exportKasten() {
  const ich = michSelbst();
  const suffix = ich ? `?person=${encodeURIComponent(ich.id)}` : '';
  const wer = ich ? ich.name : 'alle zusammen';

  const link = (pfad, beschriftung, titel) => el('a', {
    class: 'btn btn-sm export-knopf', href: pfad, download: '',
    title: titel, text: beschriftung,
  });

  return el('section', { class: 'export-box' }, [
    el('div', { class: 'export-kopf' }, [
      el('span', { class: 'export-frage', text: '📤 Tagebuch ausgeben' }),
      el('span', { class: 'export-wer', text: wer }),
    ]),
    el('div', { class: 'export-knoepfe' }, [
      link(`/api/pain/report.pdf${suffix}`, '📄 Bericht als PDF',
           'Aufbereitet: Verteilung über Tag und Woche, Wirkung der Mittel, '
           + 'Zyklus und alle Einträge'),
      link(`/api/pain/export.csv${suffix}`, '📊 Rohdaten als CSV',
           'Eine Zeile je Eintrag — für Excel oder LibreOffice'),
    ]),
    el('p', { class: 'hint',
      text: ich
        ? `Enthält die Einträge von ${ich.name}.`
        : 'Oben niemanden gewählt — die Datei enthält alle Einträge.' }),
  ]);
}

function viewPain() {
  const eintraege = painEintraege();
  const crumbs = breadcrumb([
    { label: '🏠 Start', go: goHome },
    { label: 'Schmerztagebuch' },
  ]);

  /* --- Der Schieber --- */
  const anzeige = el('span', { class: 'vas-zahl', text: String(state.painWert) });
  const wort = el('span', { class: 'vas-wort', text: vasWort(state.painWert) });
  const schieber = el('input', {
    type: 'range', min: String(VAS_MIN), max: String(VAS_MAX), step: '1',
    value: String(state.painWert), class: 'vas-schieber', id: 'vas-schieber',
    'aria-label': 'Stärke des Schmerzes von 0 bis 10',
    // Beim Ziehen nur die Anzeige nachführen, nicht neu zeichnen - sonst
    // verliert der Schieber unter dem Finger seinen Fokus.
    oninput: event => {
      state.painWert = Number(event.target.value);
      anzeige.textContent = String(state.painWert);
      anzeige.style.background = vasFarbeTief(state.painWert);
      wort.textContent = vasWort(state.painWert);
    },
  });
  anzeige.style.background = vasFarbeTief(state.painWert);

  const orte = painOrte();

  /* Die Körperstellen schalten nur ihre eigene Hervorhebung um, statt die
     Ansicht neu zu zeichnen.

     Sonst geht eine schon getippte Notiz verloren: render() baut das
     Eingabefeld neu auf und das Getippte ist weg. Derselbe Grund, aus dem
     der Schieber oben nur seine Anzeige nachführt. */
  const ortKnoepfe = orte.map(ort => el('button', {
    type: 'button',
    class: 'vas-ort' + (state.painOrt === ort ? ' an' : ''),
    text: ort,
    onclick: () => {
      // Nochmal tippen wählt ab - sonst klebt eine Stelle fest.
      state.painOrt = state.painOrt === ort ? '' : ort;
      for (const knopf of ortKnoepfe) {
        knopf.classList.toggle('an', knopf.textContent === state.painOrt);
      }
    },
  }));
  const orteZeile = orte.length ? el('div', { class: 'vas-orte' }, ortKnoepfe) : null;

  const formular = el('section', { class: 'vas-box' }, [
    painZeitSchalter(),
    el('div', { class: 'vas-kopf' }, [
      el('span', { class: 'vas-frage', text: 'Wie stark ist es gerade?' }),
      el('span', { class: 'vas-anzeige' }, [anzeige, wort]),
    ]),
    schieber,
    el('div', { class: 'vas-enden' }, [
      el('span', { text: '0 · kein Schmerz' }),
      el('span', { text: '10 · stärkster' }),
    ]),
    orteZeile,
    el('input', {
      type: 'text', id: 'vas-notiz', class: 'vas-notiz', maxlength: '200',
      placeholder: orte.length
        ? 'Stelle oder Notiz (freiwillig)'
        : 'Wo? Was war davor? (freiwillig)',
      // Enter trägt ein - auf dem Telefon der kürzere Weg.
      onkeydown: event => { if (event.key === 'Enter') painEintragen(); },
    }),
    el('button', {
      type: 'button', class: 'btn btn-primary vas-eintragen',
      text: state.painNachtrag ? 'Nachtragen' : 'Jetzt eintragen',
      onclick: painEintragen,
    }),
    el('p', { class: 'hint',
      text: state.painNachtrag
        ? 'Der Eintrag wird als nachgetragen vermerkt.'
        : 'Datum und Uhrzeit setzt die App selbst — du musst nur die Stärke sagen.' }),
  ]);

  /* --- Der Verlauf --- */
  const verlauf = painVerlauf(eintraege);

  /* --- Das Tagebuch: Messungen und Einnahmen in einer Zeitleiste --- */

  /* Beides gehört zusammengelesen, nicht in zwei Listen. „Schmerz 7 um
     19:00, Ibu 400 um 19:10, Schmerz 3 um 20:30" erzählt etwas - zwei
     getrennte Listen, zwischen denen man hin- und herrechnet, nicht. */
  const alles = [
    ...eintraege.map(e => ({ art: 'schmerz', zeit: e.recordedAt, eintrag: e })),
    ...medEintraege().map(e => ({ art: 'mittel', zeit: e.recordedAt, eintrag: e })),
  ].sort((a, b) => String(b.zeit).localeCompare(String(a.zeit)));

  let liste;
  if (!alles.length) {
    liste = el('div', { class: 'empty' }, [
      el('strong', { text: 'Noch kein Eintrag' }),
      'Oben die Stärke einstellen und eintragen. '
      + 'Jeder Eintrag wird mit Datum und Uhrzeit festgehalten.',
    ]);
  } else {
    // Nach Tagen bündeln: so liest man einen Verlauf, nicht als lange Reihe.
    const tage = [];
    for (const posten of alles) {
      const { tag, uhr } = painZeit(posten.zeit);
      let gruppe = tage.find(g => g.tag === tag);
      if (!gruppe) { gruppe = { tag, zeilen: [] }; tage.push(gruppe); }
      gruppe.zeilen.push({ ...posten, uhr });
    }

    const schmerzZeile = (eintrag, uhr) => el('div', { class: 'vas-zeile' }, [
      el('span', { class: 'vas-uhr', text: uhr }),
      // Der Balken liegt in einer Spur fester Breite. Ohne die teilte er
      // sich den Platz mit der Zahl daneben und schrumpfte mit ihr - die
      // Länge gäbe dann nicht mehr den Wert wieder, sondern nur noch, wie
      // breit die Zahl gerade ist.
      el('span', { class: 'vas-messung' }, [
        el('span', { class: 'vas-spur' }, [
          el('span', {
            class: 'vas-strich',
            style: `width:${4 + (Number(eintrag.value) || 0) * 9.6}%;`
                 + `background:${vasFarbe(eintrag.value)}`,
          }),
        ]),
        el('span', { class: 'vas-messwert', text: String(eintrag.value) }),
      ]),
      el('span', { class: 'vas-text' }, [
        el('span', { class: 'vas-oben' }, [
          eintrag.place ? el('span', { class: 'vas-stelle', text: eintrag.place }) : null,
          nachtragMarke(eintrag),
        ]),
        eintrag.note ? el('span', { class: 'vas-notiz-text', text: eintrag.note }) : null,
      ]),
      wegKnopf(`/api/pain/${eintrag.id}`),
    ]);

    const mittelZeile = (eintrag, uhr) => el('div', { class: 'vas-zeile ist-mittel' }, [
      el('span', { class: 'vas-uhr', text: uhr }),
      el('span', { class: 'med-marke' }, [
        el('span', { class: 'med-pille', 'aria-hidden': 'true', text: '💊' }),
        el('span', { class: 'med-menge', text: medMenge(eintrag) }),
      ]),
      el('span', { class: 'vas-text' }, [
        el('span', { class: 'vas-oben' }, [
          el('span', { class: 'vas-stelle', text: eintrag.drug }),
          nachtragMarke(eintrag),
        ]),
        eintrag.note ? el('span', { class: 'vas-notiz-text', text: eintrag.note }) : null,
      ]),
      wegKnopf(`/api/meds/${eintrag.id}`),
    ]);

    liste = el('div', { class: 'vas-tage' }, tage.map(gruppe => {
      const messungen = gruppe.zeilen.filter(z => z.art === 'schmerz')
                                     .map(z => z.eintrag);
      const mittel = gruppe.zeilen.filter(z => z.art === 'mittel').map(z => z.eintrag);
      return el('div', { class: 'vas-tag' }, [
        el('div', { class: 'vas-tag-kopf' }, [
          el('span', { text: gruppe.tag }),
          el('span', { class: 'vas-tag-schnitt',
            text: tagesBilanz(messungen, mittel) }),
        ]),
        ...gruppe.zeilen.map(z => z.art === 'schmerz'
          ? schmerzZeile(z.eintrag, z.uhr)
          : mittelZeile(z.eintrag, z.uhr)),
      ]);
    }));
  }

  return el('div', {}, [
    el('div', { class: 'focus-head' }, [
      crumbs,
      el('h2', { text: '🩹 Schmerztagebuch' }),
      el('p', { class: 'hint', text: painKopfzeile(eintraege, medEintraege()) }),
    ]),
    formular,
    medKasten(),
    zyklusKasten(),
    verlauf,
    liste,
    exportKasten(),
  ]);
}

function viewFocus() {
  const { kind, id } = state.focus;
  let title, hint, todos;

  // Das Tagebuch führt keine Aufgaben - es hat seine eigene Ansicht.
  if (kind === 'pain') return viewPain();

  /* Kategorie-Ebene: zeigt die Listen darin als Kacheln, keine Einträge. */
  if (kind === 'area') {
    const area = allAreas().find(a => a.id === id);
    const lists = areaLists(id);
    const crumbs = breadcrumb([
      { label: '🏠 Start', go: goHome },
      { label: area.name },
    ]);

    if (id === 'appointments') {
      const alle = kindTodos('appointments');
      const offen = alle.filter(t => !t.dueDate);
      const fest = alle.filter(t => t.dueDate)
        .sort((a, b) => (a.dueDate || '').localeCompare(b.dueDate || ''));
      const deployment = state.deployment || {};
      const suffix = deployment.authEnabled && deployment.calendarToken
        ? `?token=${encodeURIComponent(deployment.calendarToken)}` : '';

      return el('div', {}, [
        el('div', { class: 'focus-head' }, [
          crumbs,
          el('h2', { text: `${area.emoji} ${area.name}` }),
        ]),
        quickAdd(lists.length ? lists[0].id : null),
        el('section', { class: 'home-section' }, [
          el('h2', { text: 'Noch zu vereinbaren' }),
          el('p', { class: 'hint',
            text: 'Anrufen, Termin holen — steht noch kein Datum fest.' }),
          offen.length
            ? el('div', {}, offen.map(t => todoCard(t)))
            : el('p', { class: 'hint', text: 'Nichts offen.' }),
        ]),
        el('section', { class: 'home-section' }, [
          el('h2', { text: 'Steht fest' }),
          el('p', { class: 'hint', text: 'Diese Termine stehen im Kalender-Abo.' }),
          fest.length
            ? el('div', {}, fest.map(t => todoCard(t)))
            : el('p', { class: 'hint', text: 'Noch keine festen Termine.' }),
        ]),
        el('section', { class: 'home-section' }, [
          el('h2', { text: 'Kalender abonnieren' }),
          el('p', { class: 'hint',
            text: 'Diese Adresse im Kalender eintragen — feste Termine erscheinen '
                + 'dann automatisch, auch auf dem Handy.' }),
          el('code', { class: 'url', text: `${location.origin}/calendar.ics${suffix}` }),
        ]),
      ]);
    }

    if (id === 'repeating') {
      const todos = repeatingTodos();
      return el('div', {}, [
        el('div', { class: 'focus-head' }, [
          crumbs,
          el('h2', { text: `${area.emoji} ${area.name}` }),
          el('p', { class: 'hint',
            text: 'Nach dem Abhaken entsteht jeweils der nächste Termin.' }),
        ]),
        todos.length
          ? el('div', {}, todos.map(t => todoCard(t)))
          : el('div', { class: 'empty' }, [
              el('strong', { text: 'Noch nichts Regelmäßiges' }),
              'Wirf etwas wie „Müll jeden Dienstag rausstellen" ein.']),
      ]);
    }

    // Eine neue Liste gehört dorthin, wo man die Listen sieht - nicht in die
    // Einstellungen.
    const neueListe = el('input', {
      type: 'text', placeholder: `Neue Liste in ${area.name} …`,
    });
    const neueEmoji = el('input', { type: 'text', placeholder: '📋', maxlength: '4',
                                    class: 'quick-emoji' });
    const anlegen = el('form', {
      class: 'quick-add', onsubmit: async (event) => {
        event.preventDefault();
        const name = neueListe.value.trim();
        if (!name) return;
        try {
          await api('/api/lists', 'POST', {
            name, emoji: neueEmoji.value.trim() || '📋', kind: area.id,
          });
          neueListe.value = ''; neueEmoji.value = '';
          toast('Liste angelegt.');
          await refresh();
        } catch (error) { toast(error.message, true); }
      },
    }, [
      neueEmoji,
      neueListe,
      el('button', { class: 'btn btn-primary btn-sm', type: 'submit', text: '+' }),
    ]);

    return el('div', {}, [
      el('div', { class: 'focus-head' }, [
        crumbs,
        el('h2', { text: `${area.emoji} ${area.name}` }),
        el('p', { class: 'hint', text: area.hint }),
      ]),
      // Nur beim Einkauf: Die Zettel sind nach Anlass sortiert, im Laden
      // stellt sich aber die umgekehrte Frage.
      id === 'shopping' ? ladenSuche() : null,
      el('div', { class: 'big-tiles' }, lists.map(list => {
        const count = openTodos().filter(t => t.listId === list.id);
        return el('button', {
          class: 'big-tile' + (count.length ? '' : ' is-empty'), type: 'button',
          onclick: () => openFocus('list', list.id, id),
        }, [
          el('span', { class: 'big-emoji', text: list.emoji }),
          el('span', { class: 'big-name', text: list.name }),
          el('span', { class: 'big-count',
            text: count.length ? String(count.length) : 'leer' }),
        ]);
      })),
      el('div', { class: 'add-list' }, anlegen),
    ]);
  }

  if (kind === 'person') {
    const person = personById(id);
    title = person ? `${person.emoji} ${person.name}` : 'Person';
    todos = personTodos(id);
    hint = `${todos.length} offen · ${formatEffort(sumMinutes(todos))}`;
  } else if (kind === 'list') {
    const list = listById(id);
    title = list ? `${list.emoji} ${list.name}` : 'Liste';
    hint = list ? list.description : '';
    todos = openTodos().filter(t => t.listId === id);
  } else {
    const spec = FOCUS_VIEWS[kind];
    title = spec.title;
    hint = spec.hint || '';
    todos = spec.get();
  }

  // Der Weg zurück führt über die Kategorie, aus der man kam.
  const parent = state.focus.from ? allAreas().find(a => a.id === state.focus.from) : null;
  const trail = [{ label: '🏠 Start', go: goHome }];
  if (parent) trail.push({ label: parent.name, go: () => openFocus('area', parent.id) });
  trail.push({ label: title.replace(/^\S+\s/, '') });

  let body;
  if (!todos.length) {
    body = el('div', { class: 'empty' }, [
      el('strong', { text: 'Noch nichts hier' }),
      kind === 'list' ? 'Trag oben direkt etwas ein.' : 'Diese Ansicht ist gerade leer.']);
  } else if (kind === 'inbox') {
    body = el('div', {}, todos.map(reviewCard));
  } else if (kind === 'recent') {
    body = el('div', {}, todos.map(doneCard));
  } else if (kind === 'soon' || kind === 'today' || kind === 'overdue') {
    // Diese Ansichten sind schon nach Datum gefiltert.
    body = el('div', {}, todos.map(t => todoCard(t, { overdue: (daysUntil(t.dueDate) ?? 99) < 0 })));
  } else {
    const zeichne = t => todoCard(t, { overdue: (daysUntil(t.dueDate) ?? 99) < 0 });
    const { faellig, spaeter } = splitByDue(todos);
    body = el('div', {}, [
      faellig.length
        ? el('div', {}, faellig.map(zeichne))
        : el('p', { class: 'hint', text: 'Nichts, was in den nächsten Tagen ansteht. 🎉' }),
      laterBlock(spaeter, zeichne),
    ]);
  }

  return el('div', {}, [
    el('div', { class: 'focus-head' }, [
      breadcrumb(trail),
      el('h2', { text: title }),
      hint ? el('p', { class: 'hint', text: hint }) : null,
    ]),
    // Nur in einer konkreten Liste: dort weiß die App, wohin der Eintrag soll.
    kind === 'list' ? quickAdd(id) : null,
    body,
  ]);
}

/* Die Bereiche der obersten Ebene kommen aus der Datenbank - eigene lassen
   sich unter „Mehr" anlegen. „Regelmäßig" ist kein Bereich, sondern eine
   Querschnittsansicht über alle Listen, und wird darum angehängt. */
const REPEATING_AREA = { id: 'repeating', name: 'Regelmäßig', emoji: '↻',
                         hint: 'Was immer wiederkommt' };

function allAreas() {
  return [...(state.areas || []), REPEATING_AREA];
}

function areaTodos(areaId) {
  if (areaId === 'repeating') return repeatingTodos();
  return kindTodos(areaId);
}

function areaLists(areaId) {
  return state.lists.filter(l => l.kind === areaId);
}

/* Wo „überfällig / heute / bald / zu prüfen" hingehört.

   Vorher stand die Leiste über jeder Ansicht. Auf dem Wunschzettel ist das
   falsch: Dort gibt es kein „überfällig", und vier Kacheln mit Zahlen, die
   von woanders stammen, drängeln sich vor den eigentlichen Inhalt.

   Der Maßstab ist nicht eine Liste von Ausnahmen, sondern die Frage, ob in
   diesem Bereich Termine überhaupt etwas bedeuten - und die beantwortet die
   Datenbank schon selbst mit `dated`. Todos und Termine: ja. Wunschzettel,
   Merken, Einkauf, Essensideen: nein. Für später angelegte eigene Bereiche
   gilt die Regel damit ohne weiteres Zutun. */
const AUFGABEN_FOKUS = new Set(['overdue', 'today', 'soon', 'inbox',
                                'person', 'unassigned']);

function istAufgabenBereich(areaId) {
  // „Regelmäßig" ist kein Bereich der Datenbank, sondern eine Querschnitts-
  // ansicht über wiederkehrende Aufgaben - und damit zweifellos terminbehaftet.
  if (areaId === 'repeating') return true;
  const area = (state.areas || []).find(a => a.id === areaId);
  // Unbekanntes gilt als Aufgabe - so hält es der Server in area_is_dated auch.
  return area ? area.dated !== false : true;
}

function zeigeDringlichkeit() {
  const fokus = state.focus;
  if (!fokus) {
    // Ohne Fokus entscheidet der Tab. „Woche" ist die Terminansicht selbst.
    return state.tab === 'start' || state.tab === 'week';
  }
  if (AUFGABEN_FOKUS.has(fokus.kind)) return true;
  if (fokus.kind === 'area') return istAufgabenBereich(fokus.id);
  if (fokus.kind === 'list') {
    const liste = listById(fokus.id);
    return liste ? istAufgabenBereich(liste.kind) : false;
  }
  // „Zuletzt erledigt" und das Schmerztagebuch brauchen sie nicht.
  return false;
}

/* Was drängt: überfällig, heute, bald, zu prüfen. Die Abkürzung zu dem, was
   ansteht - und die taugt nur, wenn sie da ist, wo man gerade ist. Sonst
   klickt man sich erst zurück nach Hause, um zu sehen, was los ist.

   Nicht angeheftet: vier Kacheln plus die feste Leiste unten fräßen am
   Telefon zu viel Bildschirm. Sie stehen oben in der Ansicht, also immer
   einen Wisch nach oben entfernt. */
function urgentBar() {
  const heute = todayTodos();
  const ueberfaellig = overdueTodos().filter(isTask);
  const posteingang = inboxTodos();
  const offen = state.focus ? state.focus.kind : '';

  const knopf = (kind, anzahl, farbe, beschriftung) => el('button', {
    class: 'urgent-item' + (anzahl ? ' ' + farbe : '')
         + (offen === kind ? ' is-current' : ''),
    type: 'button',
    'aria-current': offen === kind ? 'true' : null,
    onclick: () => openFocus(kind),
  }, [
    el('span', { class: 'urgent-count', text: String(anzahl) }),
    el('span', { text: beschriftung }),
  ]);

  return el('div', { class: 'urgent' }, [
    knopf('overdue', ueberfaellig.length, 'alert', 'überfällig'),
    knopf('today', heute.length, 'accent', 'heute'),
    knopf('soon', baldTodos().length, 'soon', 'bald'),
    knopf('inbox', posteingang.length, 'warn', 'zu prüfen'),
  ]);
}

/* Was heute wirklich ansteht - nicht als Zahl, sondern beim Namen.

   Die Kacheln darüber sagen „2 heute". Das ist eine Zahl, kein Plan: Man
   muss erst tippen, um zu erfahren, was gemeint ist. Dieser Streifen nennt
   die Aufgaben direkt und lässt sie an Ort und Stelle abhaken. Er ist
   absichtlich schmal - eine Zeile je Aufgabe, kein Kästchen drumherum.

   Liegengebliebenes steht mit dabei: Was gestern fällig war, ist heute zu
   tun. Die rote Angabe dahinter sagt, wie lange es schon wartet. */
const STREIFEN_MAX = 5;

function heuteStreifen() {
  const nachDatum = (a, b) => (a.dueDate || '').localeCompare(b.dueDate || '');
  const dran = [...overdueTodos().filter(isTask).sort(nachDatum),
                ...todayTodos().sort(nachDatum)];
  if (!dran.length) return null;

  const zeilen = dran.slice(0, STREIFEN_MAX).map(todo => {
    const tage = daysUntil(todo.dueDate);
    const person = personById(todo.assigneeId);
    return el('div', { class: 'heute-zeile' }, [
      hakenKnopf(todo, 'check check-klein'),
      el('button', {
        class: 'heute-titel', type: 'button', title: 'Bearbeiten',
        onclick: () => { state.editing = todo.id; openFocus('today'); },
      }, todo.title),
      person ? el('span', { class: 'heute-wer', text: person.emoji }) : null,
      tage < 0
        ? el('span', { class: 'chip due-over', text: formatDue(todo.dueDate) })
        : null,
    ]);
  });

  if (dran.length > STREIFEN_MAX) {
    zeilen.push(el('button', {
      class: 'heute-mehr', type: 'button',
      text: `+ ${dran.length - STREIFEN_MAX} weitere`,
      onclick: () => openFocus('today'),
    }));
  }

  return el('div', { class: 'heute-streifen' }, [
    el('div', { class: 'heute-kopf' }, [
      el('span', { text: 'Jetzt dran' }),
      el('span', { class: 'count', text: String(dran.length) }),
    ]),
    ...zeilen,
  ]);
}

function areaKachel(area) {
  const todos = areaTodos(area.id);
  const minutes = area.id === 'tasks' ? sumMinutes(todos) : 0;
  return el('button', {
    class: 'big-tile' + (todos.length ? '' : ' is-empty'), type: 'button',
    onclick: () => openFocus('area', area.id),
  }, [
    el('span', { class: 'big-emoji', text: area.emoji }),
    el('span', { class: 'big-name', text: area.name }),
    el('span', { class: 'big-count',
      text: todos.length
        ? (minutes ? `${todos.length} · ${formatEffort(minutes)}` : `${todos.length}`)
        : area.hint }),
  ]);
}

/* Welche Kacheln vorn stehen.

   Die Reihenfolge der Bereiche kommt sonst aus der Datenbank (areas.sort).
   Diese vier sind die, die am häufigsten gebraucht werden, und stehen darum
   unabhängig davon obenan - das Schmerztagebuch mitten darunter, obwohl es
   kein Bereich ist.

   Was hier nicht genannt ist, folgt in der Reihenfolge der Datenbank. Steht
   hier etwas, was es nicht gibt - ein gelöschter Bereich etwa -, wird es
   übersprungen. */
const PAIN_KACHEL = 'schmerztagebuch';
const KACHEL_ORDNUNG = ['tasks', 'shopping', 'wishes', PAIN_KACHEL];

function startKacheln() {
  const uebrig = allAreas().map(area => ({ id: area.id, baue: () => areaKachel(area) }));
  // Das Schmerztagebuch führt keine Aufgaben, sondern Messwerte - es liegt
  // nicht in der Bereichstabelle und bekommt auch keine Listen.
  uebrig.push({ id: PAIN_KACHEL, baue: painKachel });

  const vorne = [];
  for (const id of KACHEL_ORDNUNG) {
    const stelle = uebrig.findIndex(k => k.id === id);
    if (stelle >= 0) vorne.push(...uebrig.splice(stelle, 1));
  }
  return [...vorne, ...uebrig].map(k => k.baue());
}

/* Die Kachel zum Tagebuch. Zeigt den letzten Wert, nicht eine Anzahl:
   Bei einem Tagebuch ist „wie war es zuletzt" die Frage, nicht „wie viele
   Einträge habe ich". */
function painKachel() {
  const eintraege = painEintraege();
  const letzter = eintraege[0];
  const beschriftung = letzter
    ? `${letzter.value} von 10 · ${painZeit(letzter.recordedAt).tag}`
    : 'noch kein Eintrag';

  const kachel = el('button', {
    class: 'big-tile pain-tile' + (letzter ? '' : ' is-empty'), type: 'button',
    onclick: () => {
      // Ein frischer Besuch beginnt immer bei „jetzt". Sonst trägt man beim
      // nächsten Mal unbemerkt auf einen alten Zeitpunkt ein.
      state.painNachtrag = false;
      state.painZeitpunkt = '';
      state.medOffen = '';
      openFocus('pain');
    },
  }, [
    el('span', { class: 'big-emoji', text: '🩹' }),
    el('span', { class: 'big-name', text: 'Schmerztagebuch' }),
    el('span', { class: 'big-count', text: beschriftung }),
  ]);
  // Ein farbiger Rand sagt den letzten Stand auf einen Blick - die Zahl
  // steht daneben, die Farbe trägt also nichts allein.
  if (letzter) kachel.style.setProperty('--vas-ton', vasFarbe(letzter.value));
  return kachel;
}

function viewStart() {
  if (state.focus) return viewFocus();

  const view = el('div', { class: 'home' });

  /* Notizen, die heute dran sind - direkt unter dem, was drängt. */
  const notizen = todayNotes();
  if (notizen.length) {
    view.append(el('section', { class: 'home-section' }, [
      el('h2', { text: 'Notizen für heute' }),
      el('div', { class: 'notes' }, notizen.map(note => {
        const erledigen = el('button', {
          class: 'note-done', type: 'button', title: 'Erledigt',
          text: '✓',
          onclick: async () => {
            erledigen.disabled = true;
            erledigen.blur();
            try {
              await api(`/api/todos/${note.id}`, 'PATCH',
                        { status: 'done', doneBy: state.me });
              toast('Notiz abgehakt.', false, async () => {
                await api(`/api/todos/${note.id}/restore`, 'POST', {});
                await refresh();
              });
              await refresh();
            } catch (error) { toast(error.message, true); erledigen.disabled = false; }
          },
        });
        const person = personById(note.assigneeId);
        return el('div', { class: 'note' }, [
          el('div', { class: 'note-body' }, [
            el('div', { class: 'note-text', text: note.title }),
            el('div', { class: 'note-meta',
              text: `${formatDue(note.dueDate)}${person ? ' · für ' + person.name : ''}` }),
          ]),
          erledigen,
        ]);
      })),
    ]));
  }

  /* Die Bereiche. */
  view.append(el('section', { class: 'home-section' }, [
    el('div', { class: 'big-tiles' }, startKacheln()),
  ]));

  /* Wer macht was. */
  const unassigned = unassignedTodos();
  view.append(el('section', { class: 'home-section' }, [
    el('h2', { text: 'Wer hat was zu tun' }),
    el('div', { class: 'rows' }, [
      ...state.people.map(person => {
        const todos = personTodos(person.id);
        return el('button', {
          class: 'row-link', type: 'button',
          onclick: () => openFocus('person', person.id),
        }, [
          el('span', { class: 'row-emoji', text: person.emoji }),
          el('span', { class: 'row-name', text: person.name }),
          el('span', { class: 'row-meta',
            text: todos.length ? `${todos.length} · ${formatEffort(sumMinutes(todos))}` : '—' }),
          el('span', { class: 'row-arrow', text: '›' }),
        ]);
      }),
      el('button', {
        class: 'row-link free' + (unassigned.length ? ' has' : ''), type: 'button',
        onclick: () => openFocus('unassigned'),
      }, [
        el('span', { class: 'row-emoji', text: '🙋' }),
        el('span', { class: 'row-name', text: 'Frei zu vergeben' }),
        el('span', { class: 'row-meta',
          text: unassigned.length
            ? `${unassigned.length} · ${formatEffort(sumMinutes(unassigned))}`
            : 'alles verteilt' }),
        el('span', { class: 'row-arrow', text: '›' }),
      ]),
    ]),
  ]));

  /* Rückweg nach einem Fehlgriff - dezent, aber auffindbar. */
  const recent = state.recentlyDone || [];
  view.append(el('button', {
    class: 'recent-link', type: 'button', onclick: () => openFocus('recent'),
  }, [
    el('span', { text: '↩ Zuletzt erledigt' }),
    el('span', { class: 'row-meta',
      text: recent.length ? `${recent.length} in 24 h` : 'nichts in 24 h' }),
  ]));

  return view;
}

/* ---------- Woche ----------
   Sieben Tage untereinander statt als Raster: am Telefon ist eine Spalte
   lesbar, ein 7-Spalten-Gitter nicht. Gezeigt werden nur echte Aufgaben -
   Wünsche und Medien haben keinen Termin. */

const WEEKDAYS = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag',
                  'Samstag', 'Sonntag'];
const MONTHS = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli',
                'August', 'September', 'Oktober', 'November', 'Dezember'];

function mondayOf(date) {
  const result = new Date(date);
  const weekday = (result.getDay() + 6) % 7;   // Montag = 0
  result.setDate(result.getDate() - weekday);
  result.setHours(0, 0, 0, 0);
  return result;
}

function isoOf(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-`
       + `${String(date.getDate()).padStart(2, '0')}`;
}

function viewWeek() {
  const start = mondayOf(today());
  start.setDate(start.getDate() + state.weekOffset * 7);

  const days = [...Array(7)].map((_, i) => {
    const date = new Date(start);
    date.setDate(date.getDate() + i);
    return date;
  });

  const open = openTodos().filter(isTask);
  const byDay = new Map(days.map(d => [isoOf(d), []]));
  for (const todo of open) {
    if (byDay.has(todo.dueDate)) byDay.get(todo.dueDate).push(todo);
  }

  // Alles, was vor dieser Woche liegt, würde sonst unsichtbar bleiben.
  const before = state.weekOffset === 0
    ? open.filter(t => t.dueDate && t.dueDate < isoOf(days[0]))
    : [];

  const last = days[6];
  const sameMonth = start.getMonth() === last.getMonth();
  const label = sameMonth
    ? `${start.getDate()}.–${last.getDate()}. ${MONTHS[start.getMonth()]}`
    : `${start.getDate()}. ${MONTHS[start.getMonth()].slice(0, 3)} – `
      + `${last.getDate()}. ${MONTHS[last.getMonth()].slice(0, 3)}`;

  const header = el('div', { class: 'week-head' }, [
    el('button', { class: 'btn btn-sm', type: 'button', text: '‹',
      'aria-label': 'Woche zurück',
      onclick: () => { state.weekOffset -= 1; render(); } }),
    el('div', { class: 'week-label' }, [
      el('div', { text: label }),
      el('div', { class: 'week-sub',
        text: state.weekOffset === 0 ? 'diese Woche'
            : state.weekOffset === 1 ? 'nächste Woche'
            : state.weekOffset === -1 ? 'letzte Woche'
            : `${state.weekOffset > 0 ? '+' : ''}${state.weekOffset} Wochen` }),
    ]),
    el('button', { class: 'btn btn-sm', type: 'button', text: '›',
      'aria-label': 'Woche vor',
      onclick: () => { state.weekOffset += 1; render(); } }),
    state.weekOffset !== 0 ? el('button', {
      class: 'btn btn-ghost btn-sm', type: 'button', text: 'heute',
      onclick: () => { state.weekOffset = 0; render(); },
    }) : null,
  ]);

  const view = el('div', {}, header);

  if (before.length) {
    view.append(el('section', { class: 'week-day overdue-day' }, [
      el('div', { class: 'week-day-head' }, [
        el('span', { class: 'week-day-name', text: 'Liegengeblieben' }),
        el('span', { class: 'week-day-sum',
          text: `${before.length} · ${formatEffort(sumMinutes(before))}` }),
      ]),
      ...before.map(t => todoCard(t, { overdue: true })),
    ]));
  }

  const todayIso = isoOf(today());
  for (const date of days) {
    const iso = isoOf(date);
    const todos = byDay.get(iso) || [];
    const isToday = iso === todayIso;
    view.append(el('section', {
      class: 'week-day' + (isToday ? ' is-today' : '') + (todos.length ? '' : ' empty-day'),
    }, [
      el('div', { class: 'week-day-head' }, [
        el('span', { class: 'week-day-name',
          text: `${WEEKDAYS[(date.getDay() + 6) % 7]}, ${date.getDate()}.` }),
        el('span', { class: 'week-day-sum',
          text: todos.length ? `${todos.length} · ${formatEffort(sumMinutes(todos))}` : '—' }),
      ]),
      ...todos.map(t => todoCard(t)),
    ]));
  }

  return view;
}

/* ---------- Bilanz ----------
   Zwei Maße, die nicht vermischt werden dürfen: Anzahl der Aufgaben und
   aufgewendete Zeit. Beide auf eine Achse zu legen wäre irreführend - wer
   zehn Fünf-Minuten-Sachen erledigt, hat nicht so viel getan wie jemand mit
   zwei Stunden Großputz. Deshalb ein Umschalter statt zweier Skalen.

   Gezählt wird nur, was Arbeit ist (isTask). Ein Einkaufszettel besteht aus
   Posten, nicht aus Aufgaben: Wer Milch, Brot und Butter abhakt, hätte sonst
   drei „erledigte Aufgaben" - und ein Wochenendeinkauf schlüge jeden
   Großputz. Dasselbe gilt für Wünsche, Merkzettel und Ideensammlungen. */

function withinRange(isoTimestamp, days) {
  if (!days) return true;
  if (!isoTimestamp) return false;
  const when = new Date(isoTimestamp);
  if (isNaN(when)) return false;
  return (Date.now() - when.getTime()) <= days * 86400000;
}

function groupStats(todos, keyOf) {
  const groups = new Map();
  for (const todo of todos) {
    const key = keyOf(todo) || '';
    if (!groups.has(key)) groups.set(key, { key, count: 0, minutes: 0, unknown: 0 });
    const group = groups.get(key);
    group.count += 1;
    group.minutes += Number(todo.minutes) || 0;
    if (!todo.minutes) group.unknown += 1;
  }
  return [...groups.values()];
}

/* Ein Balken je Zeile: Länge = das gewählte Maß, Zahlen stehen direkt daneben,
   damit die Grafik auch ohne Farbwahrnehmung lesbar ist. */
function barChart(rows, measure, labelOf) {
  if (!rows.length) {
    return el('p', { class: 'hint', text: 'Noch nichts erfasst.' });
  }
  const valueOf = row => measure === 'time' ? row.minutes : row.count;
  const sorted = [...rows].sort((a, b) => valueOf(b) - valueOf(a));
  const top = Math.max(...sorted.map(valueOf), 1);

  return el('div', { class: 'bars' }, sorted.map(row => {
    const value = valueOf(row);
    const detail = measure === 'time'
      ? `${formatEffort(row.minutes)} · ${row.count} ${row.count === 1 ? 'Aufgabe' : 'Aufgaben'}`
      : `${row.count} ${row.count === 1 ? 'Aufgabe' : 'Aufgaben'} · ${formatEffort(row.minutes)}`;
    const hint = row.unknown
      ? `${row.unknown} davon ohne Zeitangabe` : 'alle mit Zeitangabe';
    return el('div', { class: 'bar-row', title: `${labelOf(row.key)}: ${detail} (${hint})` }, [
      el('div', { class: 'bar-name', text: labelOf(row.key) }),
      el('div', { class: 'bar-track' },
        el('div', {
          class: 'bar-fill',
          style: `width: ${Math.max(2, Math.round(value / top * 100))}%`,
        })),
      el('div', { class: 'bar-value', text: detail }),
    ]);
  }));
}

function viewStats() {
  const people = state.people;
  const nameOfPerson = id => {
    const person = people.find(p => p.id === id);
    return person ? `${person.emoji} ${person.name}` : 'ohne Zuständige';
  };
  const nameOfList = id => {
    const list = listById(id);
    return list ? `${list.emoji} ${list.name}` : 'ohne Liste';
  };

  const done = state.todos.filter(
    t => t.status === 'done' && isTask(t) && withinRange(t.doneAt, state.statsRange));
  const open = state.todos.filter(t => t.status !== 'done' && isTask(t));

  const totalMinutes = done.reduce((sum, t) => sum + (Number(t.minutes) || 0), 0);
  const withTime = done.filter(t => t.minutes > 0).length;
  const average = withTime ? Math.round(totalMinutes / withTime) : 0;

  const view = el('div', {});

  /* Zeitraum und Maß - beide Regler in einer Zeile über den Zahlen. */
  const ranges = [[7, '7 Tage'], [30, '30 Tage'], [0, 'Alles']];
  view.append(el('div', { class: 'filters' }, [
    el('div', { class: 'seg' }, ranges.map(([days, label]) => el('button', {
      type: 'button', 'aria-pressed': String(state.statsRange === days), text: label,
      onclick: () => { state.statsRange = days; render(); },
    }))),
    el('div', { class: 'seg' }, [['time', 'nach Zeit'], ['count', 'nach Anzahl']].map(
      ([mode, label]) => el('button', {
        type: 'button', 'aria-pressed': String(state.statsMeasure === mode), text: label,
        onclick: () => { state.statsMeasure = mode; render(); },
      }))),
  ]));

  view.append(el('div', { class: 'tiles' }, [
    el('div', { class: 'tile' }, [
      el('div', { class: 'tile-value', text: String(done.length) }),
      el('div', { class: 'tile-label', text: 'erledigt' }),
    ]),
    el('div', { class: 'tile' }, [
      el('div', { class: 'tile-value', text: formatEffort(totalMinutes) }),
      el('div', { class: 'tile-label', text: 'aufgewendet' }),
    ]),
    el('div', { class: 'tile' }, [
      el('div', { class: 'tile-value', text: average ? formatEffort(average) : '—' }),
      el('div', { class: 'tile-label', text: 'je Aufgabe' }),
    ]),
  ]));

  if (done.length && withTime < done.length) {
    view.append(el('p', {
      class: 'hint',
      text: `${done.length - withTime} erledigte Aufgaben haben keine Zeitangabe und `
          + 'zählen nur bei der Anzahl mit.',
    }));
  }

  /* Welche Bereiche draußen bleiben, steht da - sonst sucht man den Einkauf
     in der Bilanz und hält die Zahlen für kaputt. Die Liste kommt aus den
     Bereichen selbst, damit sie auch für eigene Bereiche stimmt. */
  const sammlungen = (state.areas || []).filter(a => !a.dated);
  if (sammlungen.length) {
    view.append(el('p', {
      class: 'hint',
      text: 'Nicht gezählt: ' + sammlungen.map(a => a.name).join(', ')
          + ' — das sind Sammlungen, keine Aufgaben.',
    }));
  }

  view.append(el('section', { class: 'section' }, [
    el('h2', { text: 'Geschafft' }),
    el('p', { class: 'hint', text: (state.statsRange
      ? `Erledigt in den letzten ${state.statsRange} Tagen. `
      : 'Erledigt, seit es die App gibt. ')
      + 'Gezählt wird, wer abgehakt hat.' }),
    // Wer abgehakt hat zählt; fehlt die Angabe (älterer Eintrag), gilt die
    // Zuweisung als Näherung.
    barChart(groupStats(done, t => t.doneBy || t.assigneeId),
             state.statsMeasure, nameOfPerson),
  ]));

  view.append(el('section', { class: 'section' }, [
    el('h2', { text: 'Noch offen' }),
    el('p', { class: 'hint', text: 'Was gerade auf wem liegt.' }),
    barChart(groupStats(open, t => t.assigneeId), state.statsMeasure, nameOfPerson),
  ]));

  view.append(el('section', { class: 'section' }, [
    el('h2', { text: 'Wo die Arbeit anfällt' }),
    el('p', { class: 'hint', text: 'Offene Aufgaben nach Bereich.' }),
    barChart(groupStats(open, t => t.listId), state.statsMeasure, nameOfList),
  ]));

  return view;
}

/* ---------- Einstellungen ---------- */

function personEditor(person) {
  const name = el('input', { type: 'text', value: person.name });
  const emoji = el('input', { type: 'text', value: person.emoji, maxlength: '4' });
  const role = el('input', {
    type: 'text', value: person.role || '', maxlength: '60',
    placeholder: 'Rolle, z. B. Mutter · Kind, 8 Jahre · Opa',
  });
  const skills = el('input', {
    type: 'text', value: (person.skills || []).join(', '),
    placeholder: 'Kompetenzen, z. B. Handwerk, Behörden, Kita',
  });
  const save = el('button', {
    class: 'btn btn-sm', text: 'Sichern',
    onclick: async () => {
      try {
        await api(`/api/people/${person.id}`, 'PATCH', {
          name: name.value, emoji: emoji.value, role: role.value,
          skills: skills.value.split(',').map(s => s.trim()).filter(Boolean),
        });
        toast('Gespeichert.');
        await refresh();
      } catch (error) { toast(error.message, true); }
    },
  });
  const remove = el('button', {
    class: 'btn btn-ghost btn-sm', text: 'Löschen',
    onclick: async () => {
      if (!confirm(`${person.name} wirklich entfernen?`)) return;
      await api(`/api/people/${person.id}`, 'DELETE');
      await refresh();
    },
  });
  return el('div', { class: 'card' }, [
    el('div', { class: 'row' }, [
      el('div', { style: 'width:56px' }, emoji),
      el('div', { class: 'grow' }, name),
    ]),
    el('div', { class: 'row' }, [el('div', { class: 'grow' }, role)]),
    el('div', { class: 'row' }, [el('div', { class: 'grow' }, skills)]),
    el('div', { class: 'row' }, [save, el('span', { class: 'spacer', style: 'flex:1' }), remove]),
  ]);
}

function listEditor(list) {
  const name = el('input', { type: 'text', value: list.name });
  const emoji = el('input', { type: 'text', value: list.emoji, maxlength: '4' });
  const description = el('input', {
    type: 'text', value: list.description, placeholder: 'Wofür ist diese Liste?',
  });
  const keywords = el('input', {
    type: 'text', value: (list.keywords || []).join(', '),
    placeholder: 'Stichwörter für die Offline-Einordnung',
  });
  const kindSelect = el('select', {}, Object.entries(state.listKinds || {}).map(
    ([value, label]) => el('option', {
      value, text: label, selected: (list.kind || 'tasks') === value,
    })));
  const overview = el('input', {
    type: 'checkbox', style: 'width:auto', checked: list.inOverview !== false,
  });
  const save = el('button', {
    class: 'btn btn-sm', text: 'Sichern',
    onclick: async () => {
      try {
        await api(`/api/lists/${list.id}`, 'PATCH', {
          name: name.value, emoji: emoji.value, description: description.value,
          kind: kindSelect.value, inOverview: overview.checked,
          keywords: keywords.value.split(',').map(s => s.trim()).filter(Boolean),
        });
        toast('Gespeichert.');
        await refresh();
      } catch (error) { toast(error.message, true); }
    },
  });
  const count = state.todos.filter(t => t.listId === list.id && t.status !== 'done').length;
  const remove = el('button', {
    class: 'btn btn-ghost btn-sm', text: 'Löschen',
    onclick: async () => {
      const warning = count
        ? `„${list.name}“ löschen? ${count} offene Todos landen in „Ohne Liste“.`
        : `„${list.name}“ löschen?`;
      if (!confirm(warning)) return;
      await api(`/api/lists/${list.id}`, 'DELETE');
      await refresh();
    },
  });
  return el('div', { class: 'card' }, [
    el('div', { class: 'row' }, [
      el('div', { style: 'width:56px' }, emoji),
      el('div', { class: 'grow' }, name),
    ]),
    el('div', { class: 'row' }, [el('div', { class: 'grow' }, description)]),
    el('div', { class: 'row' }, [el('div', { class: 'grow' }, keywords)]),
    el('div', { class: 'row' }, [
      el('label', { class: 'field grow' }, [el('span', { text: 'Art' }), kindSelect]),
      el('label', { class: 'field', style: 'flex:0 0 auto' }, [
        el('span', { text: 'im Tab „Listen"' }), overview]),
    ]),
    el('div', { class: 'row' }, [save, el('span', { style: 'flex:1' }), remove]),
  ]);
}

function viewSettings() {
  const settings = state.settings;
  const view = el('div', {});

  /* -- Personen -- */
  const newPersonName = el('input', { type: 'text', placeholder: 'Name' });
  const addPerson = el('button', {
    class: 'btn btn-sm', text: 'Hinzufügen',
    onclick: async () => {
      const name = newPersonName.value.trim();
      if (!name) return;
      await api('/api/people', 'POST', { name, emoji: '🙂', skills: [] });
      newPersonName.value = '';
      await refresh();
    },
  });
  view.append(el('section', { class: 'section' }, [
    el('h2', { text: 'Wer gehört zur Familie?' }),
    el('p', { class: 'hint', text: 'Rolle und Kompetenzen entscheiden, wem die Einordnung '
      + 'eine Aufgabe zuweist. „Kind, 8 Jahre" verhindert, dass Behördengänge dort landen.' }),
    ...state.people.map(personEditor),
    el('div', { class: 'row' }, [el('div', { class: 'grow' }, newPersonName), addPerson]),
  ]));

  /* -- Einordnung -- */
  const providerSelect = el('select', {}, [
    ['auto', 'Automatisch (erst Cloud, dann lokal, dann Regeln)'],
    ['anthropic', 'Claude (Anthropic)'],
    ['mistral', 'Mistral'],
    ['openai', 'ChatGPT (OpenAI)'],
    ['ollama', 'Lokal über Ollama (offline)'],
    ['heuristic', 'Nur Regeln (ohne LLM, offline)'],
  ].map(([value, label]) => el('option', {
    value, text: label, selected: settings.provider === value,
  })));

  const threshold = el('input', {
    type: 'number', min: '0', max: '1', step: '0.05',
    value: settings.confidence_threshold || '0.7',
  });

  const autoAssign = el('input', {
    type: 'checkbox', style: 'width:auto', checked: settings.auto_assign === '1',
  });

  const modelInputs = {
    anthropic_model: el('input', { type: 'text', value: settings.anthropic_model || '' }),
    mistral_model: el('input', { type: 'text', value: settings.mistral_model || '' }),
    openai_model: el('input', { type: 'text', value: settings.openai_model || '' }),
    ollama_model: el('input', { type: 'text', value: settings.ollama_model || '' }),
    ollama_url: el('input', { type: 'text', value: settings.ollama_url || '' }),
  };

  const keyInputs = {};
  const keyRows = [
    ['anthropic_api_key', 'Claude / Anthropic'],
    ['mistral_api_key', 'Mistral'],
    ['openai_api_key', 'OpenAI'],
  ].map(([field, label]) => {
    const status = state.keys[field];
    keyInputs[field] = el('input', {
      type: 'password', autocomplete: 'off',
      placeholder: status === 'env' ? 'aus Umgebungsvariable' :
        status ? '•••••••• (gespeichert)' : 'nicht hinterlegt',
      disabled: status === 'env',
    });
    return el('label', { class: 'field' }, [
      el('span', { text: `${label}${status === 'env' ? ' — kommt aus der Umgebung' : ''}` }),
      keyInputs[field],
    ]);
  });

  const saveSettings = el('button', {
    class: 'btn btn-primary', text: 'Einstellungen speichern',
    onclick: async () => {
      const payload = {
        provider: providerSelect.value,
        confidence_threshold: threshold.value,
        auto_assign: autoAssign.checked ? '1' : '0',
      };
      for (const [key, input] of Object.entries(modelInputs)) payload[key] = input.value.trim();
      for (const [key, input] of Object.entries(keyInputs)) {
        if (!input.disabled && input.value.trim()) payload[key] = input.value.trim();
      }
      try {
        await api('/api/settings', 'PUT', payload);
        toast('Gespeichert.');
        await refresh();
      } catch (error) { toast(error.message, true); }
    },
  });

  view.append(el('section', { class: 'section' }, [
    el('h2', { text: 'Einordnung' }),
    el('p', { class: 'hint', text: `Aktuelle Reihenfolge: ${state.engineChain.join(' → ')}` }),
    state.engineProblem
      ? el('div', { class: 'question', style: 'margin:0 0 12px' },
          `⚠️ Zuletzt hat kein Modell geantwortet: ${state.engineProblem}`)
      : null,
    el('label', { class: 'field' }, [el('span', { text: 'Anbieter' }), providerSelect]),
    el('div', { class: 'fields' }, [
      el('label', { class: 'field' }, [
        el('span', { text: 'Ab welcher Sicherheit automatisch einsortieren?' }), threshold]),
      el('label', { class: 'field' }, [
        el('span', { text: 'Automatisch jemandem zuweisen' }), autoAssign]),
    ]),
    el('div', { class: 'fields' }, [
      el('label', { class: 'field' }, [el('span', { text: 'Claude-Modell' }), modelInputs.anthropic_model]),
      el('label', { class: 'field' }, [el('span', { text: 'Mistral-Modell' }), modelInputs.mistral_model]),
      el('label', { class: 'field' }, [el('span', { text: 'OpenAI-Modell' }), modelInputs.openai_model]),
      el('label', { class: 'field' }, [el('span', { text: 'Ollama-Modell' }), modelInputs.ollama_model]),
      el('label', { class: 'field' }, [el('span', { text: 'Ollama-Adresse' }), modelInputs.ollama_url]),
    ]),
    el('h2', { text: 'API-Schlüssel', style: 'margin-top:18px' }),
    el('p', { class: 'hint', text: 'Bleiben auf diesem Rechner (data/secrets.json, nur für dich lesbar).' }),
    el('div', { class: 'fields' }, keyRows),
    el('div', { class: 'actions' }, [saveSettings]),
  ]));

  /* -- Bereiche -- */
  const areaEditor = (area) => {
    const name = el('input', { type: 'text', value: area.name, maxlength: '40' });
    const emoji = el('input', { type: 'text', value: area.emoji, maxlength: '4' });
    const hint = el('input', { type: 'text', value: area.hint || '',
                               placeholder: 'Kurzer Hinweis unter dem Namen' });
    const dated = el('input', { type: 'checkbox', style: 'width:auto', checked: area.dated });
    const fest = ['tasks', 'appointments', 'shopping', 'wishes', 'media'].includes(area.id);
    const anzahl = state.lists.filter(l => l.kind === area.id).length;
    return el('div', { class: 'card' }, [
      el('div', { class: 'row' }, [
        el('div', { style: 'width:56px' }, emoji),
        el('div', { class: 'grow' }, name),
      ]),
      el('div', { class: 'row' }, [el('div', { class: 'grow' }, hint)]),
      el('div', { class: 'row' }, [
        el('label', { class: 'field grow' }, [
          el('span', { text: 'mit Terminen und Dauer (wie Aufgaben)' }), dated]),
      ]),
      el('div', { class: 'row' }, [
        el('button', {
          class: 'btn btn-sm', text: 'Sichern',
          onclick: async () => {
            try {
              await api(`/api/areas/${area.id}`, 'PATCH', {
                name: name.value, emoji: emoji.value, hint: hint.value,
                dated: dated.checked,
              });
              toast('Gespeichert.');
              await refresh();
            } catch (error) { toast(error.message, true); }
          },
        }),
        el('span', { style: 'flex:1' }),
        el('span', { class: 'row-meta', text: `${anzahl} Listen` }),
        fest ? null : el('button', {
          class: 'btn btn-ghost btn-sm', text: 'Löschen',
          onclick: async () => {
            if (!confirm(`Bereich „${area.name}" löschen? Seine ${anzahl} Listen `
                       + 'wandern zu den Todos.')) return;
            await api(`/api/areas/${area.id}`, 'DELETE');
            await refresh();
          },
        }),
      ]),
    ]);
  };

  const newAreaName = el('input', { type: 'text', placeholder: 'Name, z. B. Unternehmungen' });
  const newAreaEmoji = el('input', { type: 'text', placeholder: '🎡', maxlength: '4',
                                     style: 'width:56px' });
  view.append(el('section', { class: 'section' }, [
    el('h2', { text: 'Bereiche' }),
    el('p', { class: 'hint',
      text: 'Die Kacheln auf der Startseite. Eigene lassen sich hier anlegen — '
          + 'etwa „Unternehmungen" mit Listen für Ausflüge, Restaurants und Kultur.' }),
    ...(state.areas || []).map(areaEditor),
    el('div', { class: 'row' }, [
      el('div', { style: 'width:56px' }, newAreaEmoji),
      el('div', { class: 'grow' }, newAreaName),
      el('button', {
        class: 'btn btn-sm', text: 'Bereich anlegen',
        onclick: async () => {
          const name = newAreaName.value.trim();
          if (!name) return;
          await api('/api/areas', 'POST', {
            name, emoji: newAreaEmoji.value.trim() || '📂', dated: false,
          });
          newAreaName.value = ''; newAreaEmoji.value = '';
          toast('Bereich angelegt. Jetzt Listen darin anlegen.');
          await refresh();
        },
      }),
    ]),
  ]));

  /* -- Listen -- */
  const newListName = el('input', { type: 'text', placeholder: 'Name der Liste' });
  const newListArea = el('select', {}, (state.areas || []).map(a => el('option', {
    value: a.id, text: `${a.emoji} ${a.name}`,
  })));
  const addList = el('button', {
    class: 'btn btn-sm', text: 'Hinzufügen',
    onclick: async () => {
      const name = newListName.value.trim();
      if (!name) return;
      await api('/api/lists', 'POST', {
        name, emoji: '📋', kind: newListArea.value,
      });
      newListName.value = '';
      await refresh();
    },
  });
  view.append(el('section', { class: 'section' }, [
    el('h2', { text: 'Listen' }),
    ...state.lists.map(listEditor),
    el('div', { class: 'row' }, [
      el('div', { class: 'grow' }, newListName),
      el('div', { style: 'flex:0 0 auto' }, newListArea),
      addList,
    ]),
  ]));

  /* -- Kalender -- */
  const deployment = state.deployment || {};
  // Kalender-Abos schicken keine Cookies mit; deshalb hängt der Schlüssel an der Adresse.
  const suffix = deployment.authEnabled && deployment.calendarToken
    ? `?token=${encodeURIComponent(deployment.calendarToken)}` : '';
  view.append(el('section', { class: 'section' }, [
    el('h2', { text: 'Kalender' }),
    el('p', { class: 'hint', text: 'Diese Adresse im Kalender als Abo hinzufügen — fällige Todos erscheinen als ganztägige Termine.' }),
    el('code', { class: 'url', text: `${location.origin}/calendar.ics${suffix}` }),
    ...state.people.map(person => el('code', {
      class: 'url',
      text: `${location.origin}/calendar/${person.id}.ics${suffix}   (nur ${person.name})`,
    })),
    suffix ? el('p', { class: 'hint', text: 'Der Schlüssel in der Adresse ersetzt die Anmeldung — also nur an die Familie weitergeben.' }) : null,
  ]));

  /* -- Sicherung: Export und Import -- */
  const importInput = el('input', {
    type: 'file', accept: 'application/json,.json', style: 'display:none',
    onchange: async event => {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      if (!confirm(`„${file.name}" einspielen? Die jetzigen Todos, Listen und Personen werden dabei ersetzt.`)) {
        importInput.value = '';
        return;
      }
      try {
        const data = JSON.parse(await file.text());
        const result = await api('/api/import', 'POST', { data, replace: true });
        const counts = result.imported;
        toast(`${counts.todos} Todos, ${counts.lists} Listen, ${counts.people} Personen übernommen.`);
        await refresh();
      } catch (error) {
        toast(error.message, true);
      } finally {
        importInput.value = '';
      }
    },
  });

  view.append(el('section', { class: 'section' }, [
    el('h2', { text: 'Sicherung und Umzug' }),
    el('p', { class: 'hint', text: 'Eine Datei mit allen Todos, Listen, Personen und Einstellungen — zum Sichern oder um zwischen der Version zuhause und der im Internet umzuziehen. API-Schlüssel sind nicht enthalten.' }),
    el('div', { class: 'row' }, [
      el('a', { class: 'btn btn-sm', href: '/api/export', download: '', text: '⬇ Alles herunterladen' }),
      el('button', { class: 'btn btn-sm', text: '⬆ Sicherung einspielen',
        onclick: () => importInput.click() }),
      importInput,
    ]),
  ]));

  /* -- Betrieb -- */
  const doneCount = state.todos.filter(t => t.status === 'done').length;
  const backendLabel = deployment.backend === 'postgres'
    ? 'Postgres (online)' : 'SQLite-Datei (lokal)';
  const betrieb = [
    el('h2', { text: 'Betrieb' }),
    el('p', { class: 'hint', text: `Speicher: ${backendLabel} · Anmeldung: ${deployment.authEnabled ? 'aktiv' : 'aus (nur Heimnetz)'} · ${doneCount} erledigte Todos gespeichert.` }),
    el('div', { class: 'row' }, [
      el('button', {
        class: 'btn btn-sm', text: 'Erledigte älter als 30 Tage löschen',
        onclick: async () => {
          const result = await api('/api/maintenance/purge', 'POST', { days: 30 });
          toast(`${result.removed} gelöscht.`);
          await refresh();
        },
      }),
    ]),
  ];
  if (deployment.authEnabled) {
    betrieb.push(el('p', { class: 'hint', style: 'margin-top:14px',
      text: 'Hat sich jemand zu oft vertippt und wird abgewiesen? Hier lässt '
          + 'sich die Sperre sofort aufheben — du bist ja angemeldet.' }));
    betrieb.push(el('div', { class: 'row' }, [
      el('button', {
        class: 'btn btn-sm', text: '🔓 Anmeldesperren aufheben',
        onclick: async () => {
          try {
            await api('/api/maintenance/unlock', 'POST', {});
            toast('Sperren aufgehoben. Jetzt geht es wieder.');
          } catch (error) { toast(error.message, true); }
        },
      }),
      el('span', { style: 'flex:1' }),
      el('button', {
        class: 'btn btn-ghost btn-sm', text: 'Von diesem Gerät abmelden',
        onclick: async () => {
          await api('/api/logout', 'POST', {});
          location.reload();
        },
      }),
    ]));
  }
  view.append(el('section', { class: 'section' }, betrieb));

  return view;
}

/* ---------- Rahmen ---------- */

const TABS = [
  { id: 'start', text: 'Start', short: 'Start', icon: '🏠',
    counter: inboxTodos, tone: 'warn' },
  { id: 'lists', text: 'Listen', short: 'Listen', icon: '🗂',
    counter: () => {
      const sichtbar = new Set(state.lists.filter(l => l.inOverview !== false)
                                          .map(l => l.id));
      return openTodos().filter(t => !t.listId || sichtbar.has(t.listId));
    }, tone: null },
  { id: 'week', text: 'Woche', short: 'Woche', icon: '📅',
    counter: () => overdueTodos().filter(isTask), tone: 'alert' },
  { id: 'stats', text: 'Bilanz', short: 'Bilanz', icon: '📊',
    counter: null, tone: null },
  { id: 'settings', text: 'Einstellungen', short: 'Mehr', icon: '⚙️',
    counter: null, tone: null },
];

const VIEWS = {
  start: viewStart, lists: viewLists, week: viewWeek,
  stats: viewStats, settings: viewSettings,
};

function renderTabs() {
  const nav = document.getElementById('tabs');
  nav.textContent = '';
  for (const tab of TABS) {
    const count = tab.counter ? tab.counter().length : 0;
    nav.append(el('button', {
      role: 'tab',
      // Der Heimweg bleibt immer erkennbar, nicht nur wenn er gerade offen ist.
      class: tab.id === 'start' ? 'home-tab' : '',
      'aria-selected': String(state.tab === tab.id),
      'aria-label': tab.text + (count ? ` (${count})` : ''),
      onclick: () => {
        if (state.tab === tab.id && !state.focus) return;   // schon hier
        state.tab = tab.id;
        state.focus = null;
        pushStep();
        render();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      },
    }, [
      // Welche der beiden Beschriftungen sichtbar ist, entscheidet das CSS.
      el('span', { class: 'tab-icon', 'aria-hidden': 'true', text: tab.icon }),
      el('span', { class: 'tab-text', text: tab.text }),
      el('span', { class: 'tab-label', text: tab.short }),
      count ? el('span', {
        class: 'count' + (tab.tone ? ' ' + tab.tone : ''), text: String(count),
      }) : null,
    ]));
  }
}

function renderHorizons() {
  const container = document.getElementById('horizons');
  if (container.childElementCount) return;   // nur einmal aufbauen
  for (const [key, label] of Object.entries(state.horizons)) {
    container.append(el('button', {
      type: 'button', 'aria-pressed': String(state.horizon === key), 'data-horizon': key,
      text: label,
      onclick: () => {
        state.horizon = key;
        for (const button of container.children) {
          button.setAttribute('aria-pressed', String(button.dataset.horizon === key));
        }
      },
    }));
  }
}

/* Liste und Person von Hand wählen. Leer gelassen entscheidet die Einordnung -
   das bleibt der Normalfall, die Auswahl ist für die Fälle, in denen man es
   ohnehin schon weiß (Wunschzettel, Einkaufsliste). */
/* Die zwei Listen, die im Alltag am häufigsten gemeint sind. Stehen vorn im
   Auswahlfeld, damit man für „Milch" und „Bad putzen" nicht scrollt. Fehlt
   eine davon (umbenannt, gelöscht), fällt sie hier einfach weg. */
const HAEUFIGE_LISTEN = ['einkauf', 'haushalt'];

function renderAssign() {
  const listSelect = document.getElementById('capture-list');
  const personSelect = document.getElementById('capture-person');
  if (!listSelect || !personSelect) return;

  const keepList = listSelect.value;
  const keepPerson = personSelect.value;

  listSelect.textContent = '';
  listSelect.append(el('option', { value: '', text: '📥 Liste: automatisch' }));

  /* Die beiden häufigsten ganz oben: täglicher Bedarf und Haushalt. Sie
     stehen weiter unten in ihrer Gruppe noch einmal - wer die Listen
     durchgeht, soll sie dort nicht vermissen. Zwei Einträge für dieselbe
     Liste sind das kleinere Übel gegenüber einem langen Scrollweg für das,
     was man zehnmal am Tag braucht. */
  const haeufig = HAEUFIGE_LISTEN
    .map(id => state.lists.find(l => l.id === id))
    .filter(Boolean);
  if (haeufig.length) {
    const oben = el('optgroup', { label: 'Häufig' });
    for (const list of haeufig) {
      oben.append(el('option', {
        value: list.id, text: `${list.emoji} ${list.name}`,
        selected: list.id === keepList,
      }));
    }
    listSelect.append(oben);
  }

  // Nach Art gruppiert statt alles in einer langen Reihe - der Browser setzt
  // dabei selbst eine Trennlinie mit Überschrift.
  for (const bereich of (state.areas || [])) {
    const darin = state.lists.filter(l => l.kind === bereich.id);
    const titel = bereich.name;
    if (!darin.length) continue;
    const gruppe = el('optgroup', { label: titel });
    for (const list of darin) {
      gruppe.append(el('option', {
        value: list.id, text: `${list.emoji} ${list.name}`,
        selected: list.id === keepList,
      }));
    }
    listSelect.append(gruppe);
  }

  personSelect.textContent = '';
  personSelect.append(el('option', { value: '', text: '🙋 Wer: automatisch' }));
  for (const person of state.people) {
    personSelect.append(el('option', {
      value: person.id, text: `${person.emoji} ${person.name}`,
      selected: person.id === keepPerson,
    }));
  }
}

/* Wer gerade arbeitet - antippbar zum Wechseln. */
function renderMe() {
  const slot = document.getElementById('me-badge');
  if (!slot) return;
  slot.textContent = '';
  if (!state.people.length) { slot.hidden = true; return; }
  slot.hidden = false;

  const person = personById(state.me);
  slot.append(el('button', {
    class: 'me-badge' + (person ? '' : ' unset'), type: 'button',
    title: person ? `Angemeldet als ${person.name} — tippen zum Wechseln`
                  : 'Wer bist du? Tippen zum Auswählen',
    onclick: chooseMe,
  }, person ? `${person.emoji} ${person.name}` : '🙋 Wer bist du?'));
}

function chooseMe() {
  const view = document.getElementById('view');
  if (!view) return;
  const box = el('div', { class: 'card me-picker' }, [
    el('h2', { text: 'Wer arbeitet an diesem Gerät?', style: 'font-size:16px;margin:0 0 4px' }),
    el('p', { class: 'hint', text: 'Wird nur hier gemerkt und hält fest, wer etwas erledigt.' }),
    el('div', { class: 'rows', style: 'margin-top:12px' },
      state.people.map(person => el('button', {
        class: 'row-link' + (person.id === state.me ? ' free has' : ''), type: 'button',
        onclick: () => { setMe(person.id); render(); toast(`Hallo, ${person.name}.`); },
      }, [
        el('span', { class: 'row-emoji', text: person.emoji }),
        el('span', { class: 'row-name', text: person.name }),
        person.id === state.me ? el('span', { class: 'row-meta', text: 'aktuell' }) : null,
      ]))),
  ]);
  view.textContent = '';
  view.append(box);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function renderBadge() {
  const badge = document.getElementById('engine-badge');
  const engine = state.engineChain[0] || 'heuristic';
  const names = {
    anthropic: 'Claude', mistral: 'Mistral', openai: 'ChatGPT',
    ollama: 'lokal', heuristic: 'Regeln',
  };
  const queued = readQueue().length;

  if (state.stale) {
    badge.textContent = queued ? `${queued} wartet · älterer Stand` : 'älterer Stand';
    badge.className = 'engine-badge offline';
    badge.title = 'Der Server antwortet gerade nicht. Angezeigt wird der zuletzt '
                + 'geladene Stand — Änderungen sind erst wieder möglich, wenn er da ist.';
    return;
  }

  badge.textContent = queued
    ? `${queued} wartet · ${names[engine] || engine}`
    : names[engine] || engine;
  badge.className = 'engine-badge' + (engine === 'heuristic' || queued ? ' offline' : '');
  badge.title = state.engineProblem
    ? `Kein Modell erreichbar: ${state.engineProblem}`
    : `Einordnung: ${state.engineChain.join(' → ')}`;
}

function render() {
  renderTabs();
  renderHorizons();
  renderAssign();
  renderMe();
  renderBadge();
  const view = document.getElementById('view');
  view.textContent = '';
  if (state.stale) {
    view.append(el('div', { class: 'stale-note' }, [
      el('span', { class: 'spin' }),
      ' Server wacht auf — das hier ist der zuletzt geladene Stand. '
      + 'Abhaken und Ändern geht gleich wieder.',
    ]));
  }
  if (zeigeDringlichkeit()) {
    view.append(urgentBar());
    const streifen = heuteStreifen();
    if (streifen) view.append(streifen);
  }
  view.append((VIEWS[state.tab] || viewStart)());
}

/* ---------- Eingabe ---------- */

/* Wie lange auf eine Antwort gewartet wird, bevor der Einwurf als erledigt
   gilt. Ist der Server wach, antwortet er in Sekundenbruchteilen und man
   sieht sofort, wohin der Eintrag gewandert ist. Schläft er, hat Warten
   keinen Wert: der Eintrag liegt längst sicher in der Warteschlange. */
const GEDULD_MS = 2500;

/* Was nach einer erfolgreichen Einordnung zu zeigen ist - als eigene
   Funktion, weil die Antwort auch verspätet eintreffen kann. */
function zeigeEinordnung(result, chosenList) {
  const list = listById(result.todo.listId);
  if (result.autoFiled || chosenList) {
    toast(`→ ${list ? list.emoji + ' ' + list.name : 'einsortiert'}, ${formatDue(result.todo.dueDate)}`);
  } else {
    state.tab = 'start';
    state.focus = { kind: 'inbox' };
    toast('Kurz bestätigen bitte.');
  }
  if (result.problems && result.problems.length) {
    console.warn('Anbieter-Probleme:', result.problems);
  }
  // Ist die Einordnung auf die Stichwortsuche zurückgefallen, soll das
  // auffallen - sonst wundert man sich still über schlechte Treffer.
  if (result.engine === 'heuristic' && result.problems && result.problems.length) {
    state.engineProblem = result.problems[0];
    renderBadge();
    toast('Kein Modell erreichbar — nur Stichwortsuche. Details unter „Mehr".', true);
  } else if (state.engineProblem) {
    state.engineProblem = null;
  }
}

/* Einwerfen soll sich nie wie Warten anfühlen.

   Früher lief hier erst die Anfrage und das Feld wurde danach geleert - bei
   schlafendem Server also bis zu anderthalb Minuten später. Genau das macht
   das schnelle Reinwerfen kaputt, für das die App gedacht ist.

   Jetzt wandert der Eintrag zuerst in die Warteschlange im Browser und das
   Feld ist sofort wieder frei. Die Anfrage läuft parallel: Kommt sie schnell
   zurück, verschwindet der Eintrag wieder aus der Warteschlange und man
   sieht die Einordnung wie gewohnt. Kommt sie nicht, bleibt er liegen und
   wird später nachgereicht - notfalls erst beim nächsten Start. */
async function submitCapture(event, kindHint) {
  if (event) event.preventDefault();
  if (state.busy) return;
  const textarea = document.getElementById('capture-text');
  const text = textarea.value.trim();
  if (!text) return;

  const listSelect = document.getElementById('capture-list');
  const personSelect = document.getElementById('capture-person');
  const payload = {
    text,
    horizon: state.horizon,
    listId: listSelect ? listSelect.value : '',
    assigneeId: personSelect ? personSelect.value : '',
    kind: kindHint || '',
    // Die Kennung verhindert Doppeleinträge: Der Server erkennt daran einen
    // Eintrag wieder, dessen Antwort unterwegs verloren ging.
    clientId: neueKennung(),
  };
  const chosenList = payload.listId;

  // Ab hier ist der Gedanke verwahrt - auch wenn die App gleich zugeht.
  enqueue(payload);
  textarea.value = '';
  if (listSelect) listSelect.value = '';
  if (personSelect) personSelect.value = '';

  const button = document.getElementById('capture-submit');
  const hint = document.getElementById('capture-hint');
  state.busy = true;
  button.disabled = true;
  button.textContent = 'Sortiere…';
  hint.innerHTML = '<span class="spin"></span> Wird eingeordnet…';

  const unterwegs = apiWithPatience('/api/capture', null, 'POST', payload).then(
    result => { dequeue(payload.clientId); return { ok: true, result }; },
    error => ({ ok: false, error }),
  );

  const antwort = await Promise.race([unterwegs, sleep(GEDULD_MS).then(() => null)]);

  if (antwort && antwort.ok) {
    zeigeEinordnung(antwort.result, chosenList);
    await refresh();
  } else if (antwort && antwort.error.status === 401) {
    showLogin();
  } else if (antwort) {
    toast('Offline gemerkt — wird nachgereicht.', true);
  } else {
    // Noch keine Antwort. Nicht länger blockieren, sondern im Hintergrund
    // zu Ende führen.
    toast('📥 Gemerkt — wird gesendet, sobald der Server wach ist.');
    inDenHintergrund(unterwegs).then(spaet => {
      if (spaet.ok) {
        zeigeEinordnung(spaet.result, chosenList);
        refresh();
      }
      renderBadge();
    });
  }
  renderBadge();

  state.busy = false;
  button.disabled = false;
  button.textContent = 'Rein damit';
  zeigeEinordnungsHinweis();
  if (isTouch) {
    // Tastatur schließen und Eingabe zuklappen, sonst verdeckt beides
    // die Rückmeldung und die Liste darunter.
    textarea.blur();
    collapseCapture();
  } else {
    textarea.focus();
  }
}

/* ---------- Eingabe am Telefon auf- und zuklappen ----------
   Ausgeklappt nimmt der Eingabebereich ein Drittel des Bildschirms ein.
   Zusammengeklappt bleibt eine Zeile stehen, und die Listen bekommen den
   Platz. Das Aufklappen passiert beim Antippen, das Zuklappen, sobald das
   Feld leer ist und niemand mehr darin arbeitet. */

function setupCapture() {
  const form = document.getElementById('capture-form');
  const textarea = document.getElementById('capture-text');
  if (!form || !textarea) return;

  // Geteilter Text oder Verknuepfung „Einwerfen": Feld fuellen und oeffnen.
  let shared = '';
  try {
    shared = localStorage.getItem(SHARED_KEY) || '';
    if (shared) localStorage.removeItem(SHARED_KEY);
  } catch { /* egal */ }
  if (shared || window.__openCapture) {
    if (shared) textarea.value = shared;
    form.classList.add('open');
    setTimeout(() => textarea.focus(), 150);
  }

  // Der lange Beispielsatz braucht am Telefon zwei Zeilen und passt damit
  // nicht in die zugeklappte Eingabe.
  if (window.matchMedia('(max-width: 640px)').matches) {
    textarea.placeholder = 'Einfach reinwerfen …';
  }

  const open = () => form.classList.add('open');
  const closeIfEmpty = () => {
    if (!textarea.value.trim() && !form.contains(document.activeElement)) {
      form.classList.remove('open');
    }
  };

  textarea.addEventListener('focus', open);
  form.addEventListener('click', open);
  // Kurz warten: beim Tippen auf „Rein damit" wandert der Fokus erst dorthin.
  textarea.addEventListener('blur', () => setTimeout(closeIfEmpty, 180));
}

function collapseCapture() {
  document.getElementById('capture-form').classList.remove('open');
}

/* ---------- Knopf zum Einwerfen (nur am Telefon sichtbar) ---------- */

function setupFab() {
  const fab = document.getElementById('fab');
  const capture = document.getElementById('capture-form');
  if (!fab || !capture) return;

  fab.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    const textarea = document.getElementById('capture-text');
    // Erst nach dem Scrollen fokussieren, sonst springt die Seite.
    setTimeout(() => textarea.focus(), 220);
  });

  // Solange das Eingabefeld selbst zu sehen ist, wird der Knopf nicht
  // gebraucht - und er würde nur Formularfelder darunter verdecken.
  if ('IntersectionObserver' in window) {
    fab.hidden = true;
    new IntersectionObserver(([entry]) => {
      fab.hidden = entry.isIntersecting;
    }, { threshold: 0.1 }).observe(capture);
  }
}

/* ---------- Start ---------- */

document.getElementById('capture-form').addEventListener('submit', submitCapture);

/* Sichtbar machen, wann ein Modellaufruf anfällt und wann nicht. „Kostet
   nichts" ist die nützlichere Auskunft als „wird einsortiert": Sie sagt,
   warum es sich lohnt, die Liste selbst zu wählen. */
function zeigeEinordnungsHinweis() {
  const hint = document.getElementById('capture-hint');
  const listSelect = document.getElementById('capture-list');
  if (!hint || !listSelect || state.busy) return;
  hint.textContent = listSelect.value
    ? 'Liste steht fest — kostet nichts.'
    : 'Wird automatisch einsortiert.';
}

document.getElementById('capture-list')
  .addEventListener('change', zeigeEinordnungsHinweis);
/* Jeder dieser Knöpfe benennt einen Bereich - und damit steht die Liste
   fest. Kein Knopfdruck kostet mehr einen Modellaufruf. */
for (const [id, kind] of [['capture-todo', 'tasks'], ['capture-shop', 'shopping'],
                          ['capture-wish', 'wishes'], ['capture-media', 'media']]) {
  const button = document.getElementById(id);
  if (button) button.addEventListener('click', () => submitCapture(null, kind));
}

document.getElementById('capture-text').addEventListener('keydown', event => {
  // Enter sendet, Shift+Enter macht einen Zeilenumbruch.
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    document.getElementById('capture-form').requestSubmit();
  }
});

window.addEventListener('online', flushQueue);

/* Alles Zwischengespeicherte wegräumen und neu laden.

   Die Notbremse gegen einen vergifteten Zwischenspeicher: Weil die App-Hülle
   zuerst aus dem Cache kommt, überlebt eine halb geschriebene app.js jeden
   Neustart - die App beginnt dann zu starten und kommt nie zum Ende. Von
   außen ist das nicht zu unterscheiden von einem schlafenden Server, darum
   muss der Ausweg dort stehen, wo man wartet. */
async function zwischenspeicherLeeren() {
  try {
    if ('serviceWorker' in navigator) {
      const dienste = await navigator.serviceWorker.getRegistrations();
      await Promise.all(dienste.map(d => d.unregister()));
    }
  } catch (fehler) { /* weiter - der Cache ist der wichtigere Teil */ }
  try {
    if (window.caches) {
      const namen = await caches.keys();
      await Promise.all(namen.map(name => caches.delete(name)));
    }
  } catch (fehler) { /* dann eben nur neu laden */ }
  // Ohne Parameter liefert der Browser womöglich erneut aus seinem eigenen
  // Zwischenspeicher aus.
  location.replace(location.pathname + '?frisch=' + Date.now());
}

function neuLadenKnopf() {
  return el('button', {
    class: 'btn btn-sm', text: 'Nochmal versuchen',
    onclick: () => location.reload(),
  });
}

function notbremseKnopf() {
  return el('button', {
    class: 'btn btn-sm btn-quiet', text: 'Zwischenspeicher leeren',
    title: 'Räumt die gespeicherte App-Hülle weg und lädt alles neu. '
         + 'Eingeworfenes bleibt erhalten.',
    onclick: zwischenspeicherLeeren,
  });
}

/* Ab wann beim Warten die Notbremse angeboten wird. Ein schlafender Dienst
   beim Hoster braucht bis zu einer Minute - vorher ist Warten das Richtige
   und ein Knopf nur Verunsicherung. */
const NOTBREMSE_AB_MS = 30000;
let wartenSeit = 0;

function showWaking(attempt, left) {
  const view = document.getElementById('view');
  if (!view) return;
  if (!wartenSeit) wartenSeit = Date.now();
  const gewartet = Date.now() - wartenSeit;

  view.textContent = '';
  view.append(el('div', { class: 'empty' }, [
    el('strong', {}, [el('span', { class: 'spin' }), ' Server wacht auf']),
    attempt > 1
      ? `Der Dienst war eingeschlafen. Noch einen Moment … `
        + `(${attempt}. Versuch, noch ${left} s)`
      : 'Einen Moment bitte.',
    // Nach einer halben Minute ist die Frage berechtigt, ob es überhaupt
    // noch weitergeht. Dann gibt es hier etwas zu tun statt nur zu warten.
    gewartet > NOTBREMSE_AB_MS
      ? el('div', { class: 'empty-tat' }, [
          el('p', { class: 'hint',
            text: 'Dauert es ungewöhnlich lange? Dann hängt möglicherweise '
                + 'eine alte gespeicherte Fassung der App.' }),
          notbremseKnopf(),
        ])
      : null,
  ]));
}

/* Der Start ist gescheitert - und das muss man sehen.

   Vorher endete dieser Fall in der Aufwach-Anzeige: ein Kreisel, der sich
   für immer dreht. Lieber eine klare Aussage mit beiden Auswegen. */
function zeigeStartFehler(fehler) {
  const view = document.getElementById('view');
  if (!view) return;
  const text = (fehler && fehler.message) || String(fehler || 'Unbekannt');
  view.textContent = '';
  view.append(el('div', { class: 'empty' }, [
    el('strong', { text: 'Die App kam nicht hoch' }),
    el('p', { class: 'hint', text: text }),
    el('div', { class: 'empty-tat' }, [neuLadenKnopf(), notbremseKnopf()]),
  ]));
}

(async function start() {
  state.me = readMe();
  setupTheme();
  setupHomeLink();
  setupHistory();
  setupCapture();
  setupFab();
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => { /* egal */ });
  }

  try {
    const session = await apiWithPatience('/api/session', showWaking);
    if (session.authEnabled && !session.signedIn) {
      showLogin();
      return;
    }
  } catch (error) {
    if (error.status === 401) { showLogin(); return; }
    // Ohne Netz weiter: Eingeworfenes wird lokal gemerkt und nachgereicht.
  }

  // Erst der gepufferte Stand - die Familie sieht ihre Listen sofort.
  const cached = readCachedState();
  if (cached) {
    Object.assign(state, cached.data);
    state.stale = true;
    state.tab = 'start';
    render();
  }

  try {
    const data = await apiWithPatience('/api/state', cached ? null : showWaking);
    Object.assign(state, data);
    state.stale = false;
    cacheState(data);
    await flushQueue();
    if (!cached) state.tab = 'start';
    render();
    rememberStep();
  } catch (error) {
    if (error.status === 401) { showLogin(); return; }
    if (cached) {
      // Listen bleiben stehen, nur der Hinweis wechselt.
      state.stale = true;
      render();
      return;
    }
    const view = document.getElementById('view');
    if (view) {
      view.textContent = '';
      view.append(el('div', { class: 'empty' }, [
        el('strong', { text: 'Keine Verbindung' }),
        'Die Listen konnten nicht geladen werden. ',
        el('button', {
          class: 'btn btn-sm', text: 'Nochmal versuchen', style: 'margin-top:12px',
          onclick: () => location.reload(),
        }),
      ]));
    }
  }
})();
