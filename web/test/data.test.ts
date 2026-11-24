import { describe, expect, it } from "vitest";
import { createLoader, DataError, loadGalaxy, loadManifest, paths, toGalaxy } from "../src/data";
import { CLUSTERS, fakeFetch, NODES } from "./helpers";

describe("paths", () => {
  it("puts data under data/<version>/ and the manifest at the base", () => {
    const p = paths("/galaxy/", "v1");
    expect(p.nodes).toBe("/galaxy/data/v1/nodes.json");
    expect(p.clusters).toBe("/galaxy/data/v1/clusters.json");
    expect(p.neighbors).toBe("/galaxy/data/v1/neighbors.json");
    expect(p.details("c071")).toBe("/galaxy/data/v1/details/cluster_c071.json");
    expect(p.manifest).toBe("/galaxy/manifest.json");
  });
});

describe("loadManifest", () => {
  it("asks for an uncached manifest", async () => {
    const { fn, calls } = fakeFetch({ "/galaxy/manifest.json": { version: "v1" } });
    const m = await loadManifest(fn, "/galaxy/");
    expect(m.version).toBe("v1");
    expect(calls[0].init?.cache).toBe("no-store");
  });

  it("rejects with a DataError naming the file on 404", async () => {
    const { fn } = fakeFetch({});
    await expect(loadManifest(fn, "/galaxy/")).rejects.toThrow(DataError);
    await expect(loadManifest(fn, "/galaxy/")).rejects.toThrow(/manifest\.json/);
  });
});

describe("toGalaxy", () => {
  it("packs columns into typed arrays and indexes ids", () => {
    const g = toGalaxy("v1", NODES, CLUSTERS);
    expect(g.pos2).toBeInstanceOf(Float32Array);
    expect(Array.from(g.pos2)).toEqual([0, 10, 1, 11, 2, 12]);
    expect(Array.from(g.pos3)).toEqual([0, 3, 6, 1, 4, 7, 2, 5, 8]);
    expect(g.cluster).toBeInstanceOf(Uint16Array);
    expect(Array.from(g.cluster)).toEqual([0, 1, 1]);
    expect(g.index.get("fandom_2")).toBe(1);
    expect(g.titles[2]).toBe("Gamma");
    expect(g.version).toBe("v1");
  });

  it("throws when a column has a different length", () => {
    expect(() => toGalaxy("v1", { ...NODES, y2: [1, 2] }, CLUSTERS)).toThrow(DataError);
  });

  it("throws when a cluster index is out of range", () => {
    expect(() => toGalaxy("v1", { ...NODES, cluster: [0, 1, 2] }, CLUSTERS)).toThrow(DataError);
  });
});

describe("loadGalaxy", () => {
  it("loads nodes and clusters from the manifest's version", async () => {
    const { fn, calls } = fakeFetch({ "/g/data/v1/nodes.json": NODES, "/g/data/v1/clusters.json": CLUSTERS });
    const g = await loadGalaxy(fn, "/g/", { version: "v1" } as never);
    expect(g.ids).toEqual(NODES.id);
    expect(calls.map((c) => c.url).sort()).toEqual(["/g/data/v1/clusters.json", "/g/data/v1/nodes.json"]);
  });
});

describe("createLoader", () => {
  it("fetches a cluster's details once", async () => {
    const { fn, calls } = fakeFetch({ "/g/data/v1/details/cluster_c001.json": { fandom_1: { bio: "hi" } } });
    const loader = createLoader(fn, "/g/", "v1");
    const a = await loader.details("c001");
    const b = await loader.details("c001");
    expect(a).toBe(b);
    expect(calls.length).toBe(1);
  });

  it("refetches after a failure", async () => {
    const routes: Record<string, unknown> = {};
    const { fn, calls } = fakeFetch(routes);
    const loader = createLoader(fn, "/g/", "v1");
    await expect(loader.neighbors()).rejects.toThrow(DataError);
    routes["/g/data/v1/neighbors.json"] = { fandom_1: ["fandom_2"] };
    expect(await loader.neighbors()).toEqual({ fandom_1: ["fandom_2"] });
    expect(calls.length).toBe(2);
  });

  it("turns a network error into a DataError", async () => {
    const { fn } = fakeFetch({ "/g/data/v1/neighbors.json": new TypeError("offline") });
    await expect(createLoader(fn, "/g/", "v1").neighbors()).rejects.toThrow(DataError);
  });
});
