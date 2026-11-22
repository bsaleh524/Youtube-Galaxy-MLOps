/** Lowercase, strip accents, collapse anything that isn't a letter or digit into one space. */
export function fold(s: string): string {
  return s
    .normalize("NFKD")
    .replace(/\p{M}+/gu, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

/**
 * Title search over positions in `titles`. Rank: exact → prefix → word prefix → substring;
 * ties go to the shorter title, then the lower position.
 */
export function makeSearch(titles: string[]): (query: string, limit?: number) => number[] {
  const folded = titles.map(fold);
  return (query, limit = 10) => {
    const q = fold(query);
    if (!q) return [];
    const hits: [number, number, number][] = []; // rank, length, index
    for (let i = 0; i < folded.length; i++) {
      const t = folded[i];
      const at = t.indexOf(q);
      if (at < 0) continue;
      const rank = t === q ? 0 : at === 0 ? 1 : t.includes(" " + q) ? 2 : 3;
      hits.push([rank, t.length, i]);
    }
    hits.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
    return hits.slice(0, limit).map((h) => h[2]);
  };
}
