# Day 8 plan: a demo anyone can follow

Status: **approved by the owner on 2026-10-26** (all ten decisions as proposed; the draft words in section 4 accepted as written, to be refined while building). Stage 0 is therefore done. Progress log at the end.

## 1. Goal

The live demo is accurate but written for engineers: it opens on a table of runs and uses words like "trace", "span", "gating check" and "tool output contract". A recruiter, a founder or a senior leader has about a minute and will leave.

The goal: **someone with no technical background can open the link, understand in one minute what Agent Blackbox is, what it found and why it matters, and can go as deep as they like from there.** An engineer must still be able to reach all the detail.

Think of a shop. Today a visitor walks straight into the workshop. They should meet a shop window first, then be able to walk through to the workshop.

## 2. Scope (set by the owner)

- Agent Blackbox is presented as **a standalone project**.
- **Not included, on purpose:** the owner's portfolio, job titles, an "about me" section, other projects, contact details. The only links are the ones the project already has (the source code on GitHub).
- The live app (the one run on a laptop) stays as it is. Only the recorded demo changes.

## 3. The three layers

1. **The shop window (new front page of the demo).** Plain words, big numbers, one screen at a time, works on a phone.
2. **A guided tour.** Four stops through the real pages. Each page carries a small banner that says what to notice, with Back and Next buttons.
3. **The workshop (what exists today).** Runs, evaluations, comparisons, traces. Still there, one click away, and the technical parts are tucked behind "Show technical details" on each page.

At the top of the front page, three ways in:

| Button | For | What it does |
|---|---|---|
| **30 seconds** | someone skimming | jumps to the three results |
| **3 minutes** | someone curious | starts the guided tour |
| **I'm an engineer** | technical reviewers | goes to the evaluations list and the source code |

## 4. The front page, section by section (draft words, please edit)

The voice is first person about the project ("I built", "I found"), plain, specific, no hype, with limits stated. Every number is read from the stored results, as in the README.

**Hero**
> **AI agents can fail without anyone noticing. I built a flight recorder that shows where, and tests whether a fix really works.**
> A small customer-support AI agent, a recorder for everything it does, automatic checks, and honest before-and-after results. Everything on this site is a recording of real runs on a laptop; nothing is live.
> [ Start the 3-minute tour ]  [ Watch the 25-second version ]  [ I'm an engineer ]

**The problem, in one minute**
> When a plane has an accident, the black box tells investigators what happened. AI agents now do real work, like issuing refunds. When one gets it wrong, usually nobody can say why, and nobody can say whether the fix helped. That is the gap this project fills.

**What I built** (four short cards)
1. *The agent:* a support assistant that looks up orders, checks refund rules and issues refunds, running on a small AI model on my own laptop.
2. *The recorder:* writes down every step it takes, with timing and errors, and hides personal data.
3. *The checks:* plain pass-or-fail rules, such as "did it finish the job?" and "did it break a rule?", run on every recording.
4. *The comparison:* puts two versions side by side and counts what got fixed and what got broken.

**What I found** (three cards, numbers from the data)
1. **I could see why it failed.** A tool timed out and the run stopped. The page names the step to look at first.
2. **A fix that worked.** Retrying a failed step: 3 of 4 planted problems stopped mattering, none got worse, at a cost of 3 extra retries.
3. **A fix that did not.** A rewritten set of instructions looked better. On 24 cases it fixed 2 and broke 5. A second attempt was still worse.

**How I made sure the numbers are honest** (five lines, each linking to evidence)
- I wrote down what I expected before each real run.
- I kept 8 extra test cases hidden from myself while tuning.
- I checked the checker: two of my own "failures" were correct answers my rules did not recognise, and I fixed the rules openly, never the test.
- I report what got worse, not only what got better.
- Every version is judged by the same test, and the page refuses to compare things that were tested differently.

**What this cannot tell you**
> One small model, one laptop, 24 test cases plus 8, and problems I planted myself. It shows that the method works, not how any other model behaves.

**Look inside** (links)
The guided tour, all runs, all evaluations, the source code, and "how to run it yourself".

## 5. How the other pages change (demo only)

- **Plain words.** A vocabulary map used only in the demo, with the technical word kept in a hover note. Examples:

| Today | In the demo |
|---|---|
| span / trace | step / timeline |
| gating check | pass-or-fail rule |
| tool output contract | "the tool answered with something the agent cannot use" |
| golden set / held-out | test cases / extra cases I hid from myself |
| localizer / suspect | "where to look first" |
| benchmark / reference / validation | measured run / sanity run / does the checker catch problems? |
| baseline / resilient / guided | original agent / agent that retries / agent with new instructions |

- **Every page starts with "In plain words"**: two or three sentences saying what you are looking at and the one thing to notice.
- **A run page opens with a plain timeline**, for example: "looked up the order, checked the refund policy, the policy check timed out, the run stopped". The current waterfall and span table sit under "Show technical details".
- **Compare and evaluation pages** keep the verdict and the case list on top; the by-check, cost and category tables go under "Show technical details".
- **The run list** shows the failed and real-model runs first, not the 24 scripted reference runs.
- **Link preview.** The page gets a title, a description and a 1200 by 630 preview image, so a link pasted into LinkedIn or a message shows a proper card.

## 6. What I need from the owner during the work

- Approve this plan, and edit the draft words in section 4 until they sound right.
- At the end, show the page to 2 or 3 people outside tech for a minute and ask them to say in their own words what it is. I fix whatever confused them.

## 7. Order of work

Same discipline as Day 6: build in stages, test each, check the real rendered result, update the docs, ask before each commit, push once at the end.

| Stage | What | Done when |
|---|---|---|
| 0 | The words: the owner and I settle section 4 | The owner approves the text |
| 1 | Front page, new route, demo navigation, link preview image and tags | The page renders on desktop and phone, numbers read from data |
| 2 | Guided tour banners (Back / Next) and the three "ways in" | A visitor can go through all four stops without hunting |
| 3 | Plain-words layer, "In plain words" boxes, technical parts collapsed, plain run timeline, run list order | No page in the demo opens on unexplained jargon |
| 4 | Checks and real-person test | Tests below pass; 2 or 3 outsiders can explain it back |
| 5 | README leads with the plain version; screenshots, GIF and preview image regenerated; docs updated | Pushed once; Pages redeploys |

Cut order if short: the plain run timeline, then the run-list order, then tour banners. The front page and the plain-words pass are the core.

## 8. Tests (what keeps this honest)

- **No jargon on the front page or the "In plain words" boxes:** a banned-word list (span, trace, gating, contract, localizer, seed, hash, OpenTelemetry, benchmark and so on) checked against the rendered text.
- **Reading level:** the front-page text must score at or below an agreed reading grade (about grade 9) and keep sentences short. Computed in a test.
- **Numbers from data:** every figure on the front page equals the stored comparison, as the README's do.
- **Tour:** each stop's Next and Back go to the right place, and a page opened without the tour shows no banner.
- **Technical details stay reachable:** every collapsed section is still in the page and opens.
- **Live app untouched:** the existing frontend tests keep passing.
- **Phone width and light and dark themes** checked in screenshots, as before.
- **Link preview:** the tags exist and the image is 1200 by 630.

## 9. Decisions for the owner

| # | Decision | Proposed default |
|---|---|---|
| D1 | Scope | Standalone project; no portfolio, titles, about-me, other projects or contact (as the owner asked) |
| D2 | Where the front page lives | Inside the same demo, as the first page. One site, one link. The link preview tags go in the page that every address already loads |
| D3 | Plain words | A demo-only vocabulary, so the live app and its 167 tests are not disturbed |
| D4 | Technical detail | Present but folded away by default in the demo |
| D5 | Guided tour | Back and Next banners on the four stops |
| D6 | Voice | First person about the project, plain, specific, no hype, limits stated |
| D7 | Measuring "easy enough" | Banned-jargon and reading-level tests, plus 2 or 3 real people at the end |
| D8 | Look | Keep the current clean look (light, dark and system themes), with larger type and more space on the front page |
| D9 | Push | One push at the end of Day 8, as before; the existing workflows deploy it |
| D10 | Video and GIF | Keep the GIF; the owner's video, when recorded, goes at the top of the front page |

## 10. Limits to keep stating

Plain words must not become wrong words. Where a simpler phrase would overstate (for example "tests", "proves"), I keep the careful wording and make it shorter instead. The limits section stays on the front page, and the technical pages still say exactly what was measured.

## 11. Progress log

Stage 0 (the words): approved as drafted in section 4 on 2026-10-26.
