// Minimaal service worker, alleen om "installeren als app" mogelijk te
// maken. Geen offline-caching en geen onderschepping: de lijst verandert
// elke ochtend, dus een bezoeker hoort altijd de laatste versie te zien.
//
// Hier stond ook een lege fetch-luisteraar. Die ving elk verzoek op om er
// vervolgens niets mee te doen, wat Chrome terecht als overbodig aanmerkt.
self.addEventListener('install', () => self.skipWaiting());
