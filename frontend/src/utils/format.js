export function first(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== '') ?? '--';
}

export function arrayFrom(value, keys = []) {
  if (Array.isArray(value)) return value;
  for (const key of keys) {
    if (Array.isArray(value?.[key])) return value[key];
  }
  return [];
}

export function asNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function money(value) {
  const n = asNumber(value);
  return n === null ? '--' : `$${n.toFixed(2)}`;
}

export function pct(value) {
  const n = asNumber(value);
  if (n === null) return '--';
  const normalized = Math.abs(n) <= 1 ? n * 100 : n;
  return `${normalized.toFixed(1)}%`;
}

export function shortText(value, max = 120) {
  const text = String(first(value, '')).replace(/\s+/g, ' ').trim();
  if (!text) return '--';
  return text.length > max ? `${text.slice(0, max - 1)}...` : text;
}

export function compactJson(value, max = 320) {
  if (value === undefined || value === null) return '--';
  let text = '';
  try {
    text = JSON.stringify(value, null, 2);
  } catch (_) {
    text = String(value);
  }
  return text.length > max ? `${text.slice(0, max - 1)}...` : text;
}
