// Memoir's service worker. It makes the app installable and, for now, passes every request
// straight to the network: nothing is cached, so nothing can be stale. Offline support is
// a later, deliberate step.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) =>
  event.waitUntil(self.clients.claim()),
);
self.addEventListener("fetch", () => {
  // Not calling respondWith: the browser fetches as if there were no worker.
});
