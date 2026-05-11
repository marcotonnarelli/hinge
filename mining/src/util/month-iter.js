// Yields half-open monthly windows [start, end) covering [from, to).
// Each window is { key: 'YYYY-MM', from: 'YYYY-MM-DD', to: 'YYYY-MM-DD' }.
// `to` is the first day of the next month so callers can use it as exclusive upper bound.

export function monthIter(fromIso, toIso) {
  const from = new Date(fromIso + 'T00:00:00Z');
  const to = new Date(toIso + 'T00:00:00Z');
  const out = [];
  const cur = new Date(Date.UTC(from.getUTCFullYear(), from.getUTCMonth(), 1));
  while (cur < to) {
    const next = new Date(Date.UTC(cur.getUTCFullYear(), cur.getUTCMonth() + 1, 1));
    const yyyy = cur.getUTCFullYear();
    const mm = String(cur.getUTCMonth() + 1).padStart(2, '0');
    out.push({
      key: `${yyyy}-${mm}`,
      from: cur.toISOString().slice(0, 10),
      to: (next < to ? next : to).toISOString().slice(0, 10),
    });
    cur.setUTCMonth(cur.getUTCMonth() + 1);
  }
  return out;
}
