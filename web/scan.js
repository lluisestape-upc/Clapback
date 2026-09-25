// Guided AR scan (WebXR hit-test, Chrome on ARCore Android, HTTPS only).
//
// Flow the user sees:
//   "Point at a floor corner and tap"  → repeat → "tap the first corner to close"
//   "Point at the ceiling above any corner and tap"   (or type the height)
//   then, per surface: "What is this wall made of?"   (free text → intake agent)
//
// Output: the same Room JSON as the typed-dimensions form (see clapback/room.py).
//
// Timebox: 10-18 → 10-21. If it isn't working by then, ship with typed
// dimensions; nothing else depends on this file.

export async function arSupported() {
  if (!("xr" in navigator)) return false;
  try {
    return await navigator.xr.isSessionSupported("immersive-ar");
  } catch {
    return false;
  }
}

export async function startScan() {
  // TODO
  // 1. navigator.xr.requestSession("immersive-ar", {
  //      requiredFeatures: ["hit-test", "local-floor"],
  //      optionalFeatures: ["dom-overlay"], domOverlay: { root: <overlay el> } })
  // 2. viewer-space hit-test source → reticle on the floor each frame
  // 3. on "select": push reticle position (x, z of the floor plane) as a corner;
  //    close the polygon when the tap lands near corner 0
  // 4. ceiling: hit-test won't find a ceiling reliably, so either raycast
  //    against a vertical plane through a corner or ask the user to type it
  // 5. map XR coords (y-up) to Room coords (z-up): Room.x = xr.x, Room.y = -xr.z
  throw new Error("AR scan not implemented yet");
}
