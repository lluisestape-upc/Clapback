// Minimal service worker: it only exists so Chrome offers "Install app".
// No offline cache on purpose; the app needs the server for every analysis.
self.addEventListener("fetch", () => {});
