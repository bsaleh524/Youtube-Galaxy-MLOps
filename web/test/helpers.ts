// Test helpers: a fake fetch serving an in-memory URL → JSON map, and a tiny galaxy fixture.
import type { ClusterInfo } from "../src/data";

export function fakeFetch(routes: Record<string, unknown>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fn = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (!(url in routes)) return new Response("not found", { status: 404 });
    const body = routes[url];
    if (body instanceof Error) throw body;
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  return { fn, calls };
}

export function cluster(key: string, name: string, colour: string, size = 1): ClusterInfo {
  return { key, name, colour, size, leader_id: null, cx2: 0, cy2: 0, cx3: 0, cy3: 0, cz3: 0 };
}

export const NODES = {
  id: ["fandom_1", "fandom_2", "fandom_3"],
  title: ["Alpha", "Beta", "Gamma"],
  cluster: [0, 1, 1],
  x2: [0, 1, 2],
  y2: [10, 11, 12],
  x3: [0, 1, 2],
  y3: [3, 4, 5],
  z3: [6, 7, 8],
};

export const CLUSTERS = [cluster("c001", "Gaming", "#ff0000", 1), cluster("c002", "Music", "#00ff00", 2)];
