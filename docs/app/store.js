/* What this device remembers: inputs, the open tab, and your sites. Nothing leaves the device.
 * Keys are prefixed because other apps on the same web address share this storage. Storage can be
 * missing (private browsing, previews), so every call quietly falls back. */

const PREFIX = 'event-horizon:';

export function load(key, fallback = null) {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    return raw == null ? fallback : JSON.parse(raw);
  } catch (e) {
    return fallback;
  }
}

export function save(key, value) {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value));
    return true;
  } catch (e) {
    return false;
  }
}

export function remove(key) {
  try { localStorage.removeItem(PREFIX + key); } catch (e) { /* nothing to remove */ }
}
