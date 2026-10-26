/** The page title and link-preview tags of the recorded demo (what LinkedIn, Slack or a message app shows for the link). */
export const SITE_URL = "https://shubham261299.github.io/agent-blackbox/";
export const SITE_TITLE = "Agent Blackbox: a flight recorder for AI agents";
export const SITE_DESCRIPTION =
  "I built a flight recorder for AI agents. It shows where a run went wrong and tests whether a fix really works. A recorded demo with real results.";
export const PREVIEW_IMAGE = `${SITE_URL}og.png`;
export const PREVIEW_SIZE = { width: 1200, height: 630 };

const esc = (s: string) => s.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;");

export function demoMetaTags(): string {
  const tags: [string, string, string][] = [
    ["name", "description", SITE_DESCRIPTION],
    ["property", "og:type", "website"],
    ["property", "og:site_name", "Agent Blackbox"],
    ["property", "og:title", SITE_TITLE],
    ["property", "og:description", SITE_DESCRIPTION],
    ["property", "og:url", SITE_URL],
    ["property", "og:image", PREVIEW_IMAGE],
    ["property", "og:image:width", String(PREVIEW_SIZE.width)],
    ["property", "og:image:height", String(PREVIEW_SIZE.height)],
    ["property", "og:image:alt", "Agent Blackbox: a flight recorder for AI agents, with three results from the recorded demo."],
    ["name", "twitter:card", "summary_large_image"],
    ["name", "twitter:title", SITE_TITLE],
    ["name", "twitter:description", SITE_DESCRIPTION],
    ["name", "twitter:image", PREVIEW_IMAGE],
  ];
  return tags.map(([attr, key, value]) => `    <meta ${attr}="${key}" content="${esc(value)}" />`).join("\n");
}

/** The demo's index.html with its own title and preview tags. The live app's page is left as it is. */
export function injectDemoMeta(html: string): string {
  return html
    .replace(/<title>[^<]*<\/title>/, `<title>${esc(SITE_TITLE)}</title>`)
    .replace("</head>", `${demoMetaTags()}\n  </head>`);
}
