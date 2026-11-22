// Shareable links: #/creator/<id> and #/cluster/<key>. Ids and keys only, never array positions.
export interface HashState {
  creator?: string;
  cluster?: string;
}

export function parseHash(h: string): HashState {
  const m = /^#\/(creator|cluster)\/(.+)$/.exec(h);
  if (!m) return {};
  let value: string;
  try {
    value = decodeURIComponent(m[2]);
  } catch {
    return {}; // a garbled link (e.g. "%E0") is ignored, not fatal
  }
  return m[1] === "creator" ? { creator: value } : { cluster: value };
}

export function formatHash(s: HashState): string {
  if (s.creator) return `#/creator/${encodeURIComponent(s.creator)}`;
  if (s.cluster) return `#/cluster/${encodeURIComponent(s.cluster)}`;
  return "";
}
