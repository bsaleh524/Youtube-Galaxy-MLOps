// Name lookup for questions like "channels like Markiplier". Creator names were removed from the
// embeddings (issue #5), so a named creator is found by title and its own stored vector is used
// as the query. Folding matches web/src/search.ts fold() exactly.
import { type IndexView, type MetaView, readRecord } from "./format";
import { normalize } from "./search";

export const CUES: string[][] = [
  ["like"],
  ["similar", "to"],
  ["such", "as"],
  ["alternatives", "to"],
  ["alternative", "to"],
  ["resembling"],
  ["than"],
];
export const FILLER = new Set(["videos", "video", "content", "channel", "channels", "stuff", "please", "youtube", "on"]);
const MIN_TITLE = 3;

export function foldName(s: string): string {
  return s
    .normalize("NFKD")
    .replace(/\p{M}+/gu, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

/**
 * Folded title → lowest row with that title. Decodes every record once (isolate startup).
 * Titles that are common topic words (index_manifest.json `topic_words`: words in >= 5% of bios,
 * e.g. "minecraft", "music") are left out, so "minecraft" stays a topic search.
 */
export function buildNameIndex(meta: MetaView, topicWords: Set<string> = new Set()): Map<string, number> {
  const titles: string[] = [];
  for (let row = 0; row < meta.n; row++) titles.push(readRecord(meta, row).title);
  return nameIndexFromTitles(titles, topicWords);
}

/** The same index from a plain title list (row = position). Shared fixture: test/fixtures/name_cases.json. */
export function nameIndexFromTitles(titles: string[], topicWords: Set<string> = new Set()): Map<string, number> {
  const out = new Map<string, number>();
  titles.forEach((title, row) => {
    const key = foldName(title);
    if (key.length >= MIN_TITLE && !topicWords.has(key) && !out.has(key)) out.set(key, row);
  });
  return out;
}

function cueEnd(words: string[], i: number): number | null {
  for (const cue of CUES) {
    if (cue.every((w, j) => words[i + j] === w)) return i + cue.length;
  }
  return null;
}

/**
 * The row of the creator a question names, or null. Matches when the whole question is a title,
 * or when the words after a cue ("like", "similar to", …) up to the end are a title. Trailing
 * filler words ("videos", "content") are ignored, so "like mark rober videos" matches.
 */
export function findNamedCreator(question: string, names: Map<string, number>): number | null {
  const words = foldName(question).split(" ").filter(Boolean);
  while (words.length && FILLER.has(words[words.length - 1])) words.pop();
  if (!words.length) return null;
  const whole = names.get(words.join(" "));
  if (whole !== undefined) return whole;
  for (let i = 0; i < words.length; i++) {
    const start = cueEnd(words, i);
    if (start === null || start >= words.length) continue;
    const row = names.get(words.slice(start).join(" "));
    if (row !== undefined) return row;
  }
  return null;
}

/** A creator's stored vector (int8 × row scale), normalised: the query for "similar to" search. */
export function creatorVector(index: IndexView, row: number): Float32Array {
  const { dim, vecs, scales } = index;
  const v = new Float32Array(dim);
  const s = scales[row];
  for (let d = 0; d < dim; d++) v[d] = vecs[row * dim + d] * s;
  const n = normalize(v);
  if (!n) throw new Error(`creator row ${row} has a zero vector`);
  return n;
}
