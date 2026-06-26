// Thin wrapper around the pywebview-injected Python API.
// window.pywebview.api is available only after the `pywebviewready` event.

let _ready;
export function apiReady() {
  if (_ready) return _ready;
  _ready = new Promise((resolve) => {
    if (window.pywebview && window.pywebview.api) return resolve(window.pywebview.api);
    window.addEventListener("pywebviewready", () => resolve(window.pywebview.api), { once: true });
  });
  return _ready;
}

export async function api() {
  return apiReady();
}
