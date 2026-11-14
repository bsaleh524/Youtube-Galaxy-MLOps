// Query embedding via Workers AI. Must match pipeline/evaluate.py and pipeline/parity_check.py:
// same model, CLS pooling (sentence-transformers' bge default), and the bge v1.5 query prefix.
import { l2normalize } from "./search";

export const EMBED_MODEL = "@cf/baai/bge-small-en-v1.5";
export const QUERY_PREFIX = "Represent this sentence for searching relevant passages: ";

export async function embedQuery(ai: Ai, question: string): Promise<Float32Array> {
  const out = (await ai.run(EMBED_MODEL, {
    text: [QUERY_PREFIX + question],
    pooling: "cls",
  } as never)) as unknown as { data: number[][] };
  return l2normalize(out.data[0]);
}
