import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { vi } from "vitest";
import { createDemoSource } from "../api/demo";

/** The committed demo data folder, read straight from disk. */
export const DEMO_DIR = join(process.cwd(), "public", "demo-data");

export const demoJson = <T>(path: string): T => JSON.parse(readFileSync(join(DEMO_DIR, path), "utf-8")) as T;

export const demoFiles = (folder: string): string[] => readdirSync(join(DEMO_DIR, folder));

/** A data source over the real exported demo data: the same files the website serves, with `fetch` answered from disk. */
export function realDemoSource() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      try {
        return new Response(readFileSync(join(DEMO_DIR, url.replace(/^demo-data\//, "")), "utf-8"), { status: 200 });
      } catch {
        return new Response("not found", { status: 404 });
      }
    }),
  );
  return createDemoSource("demo-data");
}
