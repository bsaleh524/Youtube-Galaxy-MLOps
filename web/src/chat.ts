// Client for the chat Worker (worker/src/handler.ts). The contract is in
// docs/superpowers/plans/2026-11-24-plan-4-chat-search.md; "offline" is added here for network
// errors, timeouts and replies that aren't JSON.
import type { Manifest } from "./data";

export interface ChatHit {
  id: string;
  title: string;
  cluster: unknown;
  score: number;
  url: string;
  snippet: string;
}

export type ChatResult =
  | {
      status: "ok";
      mode: "search";
      kind: "topic" | "similar";
      about: { id: string; title: string } | null;
      results: ChatHit[];
      index_version: string;
    }
  | { status: "bad_request"; error: string }
  | { status: "rate_limited"; retry_after: number }
  | { status: "unavailable" }
  | { status: "resting" }
  | { status: "forbidden" }
  | { status: "error" }
  | { status: "offline" };

/** The Worker endpoint: VITE_CHAT_URL (local dev) wins, then the manifest's chat.url, else null (no chat). */
export function chatUrl(
  manifest: Manifest,
  override: string | undefined = import.meta.env.VITE_CHAT_URL as string | undefined,
): string | null {
  return override || manifest.chat?.url || null;
}

export async function askChat(
  fetchFn: typeof fetch,
  url: string,
  question: string,
  opts: { timeoutMs?: number; forceTopic?: boolean } = {},
): Promise<ChatResult> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 10000);
  try {
    const res = await fetchFn(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(opts.forceTopic ? { question, force_topic: true } : { question }),
      signal: ctrl.signal,
    });
    const body = (await res.json()) as ChatResult;
    return body && typeof body === "object" && "status" in body ? body : { status: "offline" };
  } catch {
    return { status: "offline" };
  } finally {
    clearTimeout(timer);
  }
}
