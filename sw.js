// Minimaal service worker, alleen om "installeren als app" mogelijk te maken.
// Geen offline-caching: de app moet altijd de laatste data.json ophalen
// zolang je op je thuisnetwerk zit.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('fetch', () => {});
