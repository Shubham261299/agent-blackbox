import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PREVIEW_IMAGE, PREVIEW_SIZE, SITE_DESCRIPTION, SITE_TITLE, SITE_URL, demoMetaTags, injectDemoMeta } from "./demoMeta";

const PAGE = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Agent Blackbox</title>
  </head>
  <body></body>
</html>`;

describe("link preview", () => {
  it("gives the demo a title and description a stranger can understand", () => {
    expect(SITE_TITLE).toBe("Agent Blackbox: a flight recorder for AI agents");
    expect(SITE_DESCRIPTION.length).toBeGreaterThan(80);
    expect(SITE_DESCRIPTION.length).toBeLessThanOrEqual(160);
  });

  it("uses absolute addresses, because a preview is fetched by a service that does not know where the page is", () => {
    expect(SITE_URL).toMatch(/^https:\/\/.+\/$/);
    expect(PREVIEW_IMAGE).toBe(`${SITE_URL}og.png`);
    const tags = demoMetaTags();
    expect(tags).toContain(`<meta property="og:image" content="${PREVIEW_IMAGE}" />`);
    expect(tags).toContain(`<meta property="og:url" content="${SITE_URL}" />`);
    expect(tags).toContain(`<meta name="twitter:image" content="${PREVIEW_IMAGE}" />`);
  });

  it("declares the image size a large preview card needs", () => {
    expect(PREVIEW_SIZE).toEqual({ width: 1200, height: 630 });
    expect(demoMetaTags()).toContain('content="1200"');
    expect(demoMetaTags()).toContain('content="630"');
    expect(demoMetaTags()).toContain('<meta name="twitter:card" content="summary_large_image" />');
  });

  it("describes the image for people who cannot see it", () => {
    expect(demoMetaTags()).toMatch(/og:image:alt" content="[^"]{20,}"/);
  });

  it("sets the title and adds the tags inside the head, once each", () => {
    const html = injectDemoMeta(PAGE);
    expect(html).toContain(`<title>${SITE_TITLE}</title>`);
    expect(html.indexOf('property="og:title"')).toBeLessThan(html.indexOf("</head>"));
    expect(html.match(/og:title/g)).toHaveLength(1);
    expect(html.match(/<title>/g)).toHaveLength(1);
    expect(html).toContain('<meta charset="UTF-8" />');
  });

  it("never lets text break out of an attribute", () => {
    const tags = demoMetaTags();
    for (const value of tags.matchAll(/content="([^"]*)"/g)) expect(value[1]).not.toMatch(/[<>]/);
  });

  it("is applied to the recorded demo's page only, never to the live app's", () => {
    const config = readFileSync(join(process.cwd(), "vite.config.ts"), "utf-8");
    expect(config).toContain('transformIndexHtml: (html: string) => (mode === "demo" ? injectDemoMeta(html) : html)');
  });
});
