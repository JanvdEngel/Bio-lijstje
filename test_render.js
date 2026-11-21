// Draait de render-functie van template.html echt uit, tegen een minimale DOM.
//
//     node test_render.js
//
// De Python-tests kunnen alleen controleren dát een tekst in het sjabloon
// staat, niet of hij ook op de pagina belandt. Dat verschil was hier geen
// theorie: de verouderingsbalk werd met insertAdjacentElement ingevoegd en
// daarna door content.innerHTML = ... weer weggegooid. De tekst stond in het
// sjabloon en verscheen nooit.

const fs = require('fs');
const path = require('path');

const sjabloon = fs.readFileSync(path.join(__dirname, 'template.html'), 'utf8');
const js = [...sjabloon.matchAll(/<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/g)]
  .map((m) => m[1]).join('\n');

const el = (id) => ({
  id, innerHTML: '', textContent: '', attrs: {}, dataset: {}, style: {},
  setAttribute(k, v) { this.attrs[k] = v },
  getAttribute(k) { return this.attrs[k] },
  insertAdjacentElement() {}, addEventListener() {}, closest() { return null },
  querySelector() { return null }, querySelectorAll() { return [] },
  classList: { add() {}, remove() {}, toggle() {}, contains() { return false } },
});
const nodes = { content: el('content'), updated: el('updated'), themaKnop: el('themaKnop') };
const doods = { classList: { add() {}, remove() {}, toggle() {}, contains() { return false } }, style: {}, dataset: {} };

global.document = {
  documentElement: doods,
  getElementById: (id) => nodes[id] || null,
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
  createElement: () => el('los'),
  title: '',
};
global.window = global;
global.localStorage = { getItem: () => null, setItem() {} };
global.fetch = () => new Promise(() => {});
global.matchMedia = () => ({ matches: false, addEventListener() {} });
global.__nodes = nodes;

let fouten = 0;
global.__keur = (wat, ok, extra) => {
  if (ok) { console.log('  ok    ' + wat); } else {
    fouten++;
    console.log('  FOUT  ' + wat + (extra ? ' — ' + extra : ''));
  }
};
global.__klaar = () => {
  console.log();
  if (fouten) { console.log(fouten + ' controle(s) niet in orde'); process.exit(1); }
  console.log('de render-functie meldt uitval en veroudering ook echt');
};

// Het testdeel moet in dezelfde scope als het sjabloon-script: `let data` is
// block-scoped tot deze eval en is van buitenaf niet toe te wijzen.
const test = `
const it = (n, p, w, s) => ({ naam: n, actieprijs: p, normale_prijs: w, soort: s || 'vers' });
const toon = (tijd, aanb, st) => {
  data = { laatst_bijgewerkt: tijd, aanbiedingen: aanb };
  if (st) { data.winkelstatus = st; }
  __nodes.content.innerHTML = '';
  render();
  return __nodes.content.innerHTML;
};
const nu = () => new Date().toISOString();
const dagenTerug = (n) => new Date(Date.now() - n * 24 * 3600 * 1000).toISOString();

// 1. Drie dagen oud, één winkel onbereikbaar, één half opgehaald, één echt leeg
let h = toon(dagenTerug(3),
  { AH: [it('AH Bio druiven', 1.75, 3.49)], Jumbo: [], Lidl: [it('Bio bananen', 1.49, 2.19)], Plus: [] },
  { AH: 'ok', Jumbo: 'mislukt', Lidl: 'onvolledig', Plus: 'ok' });
__keur('een lijst van drie dagen oud krijgt een balk', h.includes('class="verouderd"'));
__keur('die balk noemt de ouderdom', h.includes('<strong>3 dagen oud</strong>'));
__keur('een onbereikbare winkel zegt "Niet opgehaald"', h.includes('Niet opgehaald'));
__keur('een half opgehaalde winkel zegt dat er acties kunnen missen',
  h.includes('niet volledig opgehaald'));
__keur('een winkel die echt leeg is houdt de oude tekst',
  h.includes('Vandaag geen bio-acties bij Plus'));
__keur('een onbereikbare winkel zegt NIET dat er geen acties zijn',
  !h.includes('Vandaag geen bio-acties bij Jumbo'));
__keur('een onbereikbare winkel toont ? in plaats van 0',
  (h.match(/class="count">\\?</g) || []).length === 1,
  (h.match(/class="count">\\?</g) || []).length + ' van 1');

// 2. Verse lijst, alles gelukt: geen enkele melding
h = toon(nu(), { AH: [it('AH Bio druiven', 1.75, 3.49)], Plus: [] }, { AH: 'ok', Plus: 'ok' });
__keur('een verse lijst krijgt geen verouderingsbalk', !h.includes('class="verouderd"'));
__keur('zonder storing staat er geen uitvalmelding', !h.includes('class="uitval"'));
__keur('een lege winkel meldt gewoon dat er geen acties zijn',
  h.includes('Vandaag geen bio-acties bij Plus'));

// 3. Alle winkels onbereikbaar: dat is een storing, geen rustige week
h = toon(nu(), { AH: [], Jumbo: [] }, { AH: 'mislukt', Jumbo: 'mislukt' });
__keur('alles onbereikbaar geeft een eigen toestand',
  h.includes('De lijst kon niet worden opgehaald'));
__keur('alles onbereikbaar zegt niet "vandaag geen bio-acties"',
  !h.includes('Vandaag geen bio-acties'));

// 4. Een bestand van voor deze wijziging heeft geen winkelstatus
h = toon(nu(), { AH: [], Jumbo: [it('Bio peer', 1.0, 1.5)] }, null);
__keur('zonder winkelstatus gedraagt de pagina zich als voorheen',
  h.includes('Vandaag geen bio-acties bij AH') && !h.includes('class="uitval"'));

// 5. Net onder de drempel: geen balk
h = toon(new Date(Date.now() - 20 * 3600 * 1000).toISOString(),
  { AH: [it('AH Bio druiven', 1.75, 3.49)] }, { AH: 'ok' });
__keur('twintig uur oud is nog geen melding', !h.includes('class="verouderd"'));

__klaar();
`;

eval(js + test);
