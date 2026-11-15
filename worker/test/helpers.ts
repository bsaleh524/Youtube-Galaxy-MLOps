import { env } from "cloudflare:workers";

export async function fixtureBuffer(name: string): Promise<ArrayBuffer> {
  const res = await (env as unknown as { ASSETS: Fetcher }).ASSETS.fetch(`https://assets.local/${name}`);
  if (!res.ok) throw new Error(`fixture ${name}: ${res.status}`);
  return res.arrayBuffer();
}

export async function fixtureJson<T>(name: string): Promise<T> {
  return JSON.parse(new TextDecoder().decode(await fixtureBuffer(name))) as T;
}
