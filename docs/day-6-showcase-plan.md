# Day 6 plan: showcase

Status: **approved 2026-10-21, in progress.** All ten decisions in section 9 were approved as proposed (recorded there). Stage 0 is done; see the progress log at the end.

## 1. Goal

Day 1-5 built something a hiring manager cannot see unless they run it. Day 6 makes it **understandable in about a minute without installing anything**, and **verifiable in ten for a technical reviewer**.

Two audiences, in this order:

1. **Hiring managers and HR (no technical background assumed).** A live link that opens in a browser and tells the story, a README that starts in plain language, one short moving picture.
2. **Technical reviewers.** The architecture, the stack, how to run it, and where every number came from.

The story to tell is the one Day 5 earned, including the part that did not go well:

> An AI agent runs. A tool fails. You click the red span and see why. The score drops. A fix absorbs the same failure, and the before/after page shows **3 faults fixed, 0 broken, at a stated cost**. A second fix, a better prompt, looked like an improvement and **made things worse**; the same tooling caught it, and the project reports it.

Showing a fix that regressed, and the measurement that caught it, is the strongest thing in the project. The README leads with it, not around it.

## 2. What exists today, and what is missing

| Have | Missing |
|---|---|
| `DataSource` interface with `kind: "live" \| "demo"`; the shell already says "Recorded demo data" in demo mode; the start-run and start-evaluation panels are already hidden when a source cannot start them; hash routing (deployable as plain files) | a `DemoSource` that reads baked JSON; the baked JSON; a build mode for it |
| A local database of real results: 343 runs, 1,666 spans, 31 evaluations, 3.8 MB (git-ignored, so a deployed site cannot read it) | a way to export a **curated, safe** subset into the repo |
| Docker Compose with Jaeger only (image tag pinned, no restart policy) | the API and UI as services; one command to start everything |
| Eight docs with the full results | a README, screenshots, a moving picture, a public link |
| A public repo with no licence | a licence decision |

Tooling facts that shape the plan: no `ffmpeg` and no Pillow on this machine, so a GIF cannot be made with what is installed today; Node 24 and Docker 29 are available; the GitHub CLI is logged in as the personal account with the `workflow` scope, so a Pages deployment workflow can be added from here.

## 3. Step 0 (a prerequisite): make the numbers reproducible on another machine

**A real problem found while planning.** A dataset's identity hash is computed from the raw bytes of its file. This machine converts line endings (`core.autocrlf=true`), so `golden-v3` hashes to `7bb5852c6198` here and would hash to `82acd02d8a18` on Linux, on macOS, and inside Docker. The comparison page refuses two evaluations with different dataset hashes, so anyone who clones the repo elsewhere and re-runs a benchmark could not compare it with the numbers in the README. `holdout-v1` happens to have LF endings and `golden-v2`/`v3` have CRLF, so the repo is also inconsistent with itself.

**Fix.** Hash the content with line endings normalised to LF, add a `.gitattributes` so the files are stored consistently, and migrate the hashes already stored in the database (a one-off mapping old hash -> new hash for the three datasets). Evaluation ids do not change; the hash strings quoted in the docs are updated once. A test pins that CRLF and LF versions of the same content hash identically.

This goes first because everything else (the baked demo data, the README's "reproduce this" instructions, Docker) quotes those hashes.

## 4. Deliverables

### A. The static demo (the main deliverable)

**A1. Curated export.** A script (`python -m blackbox.export_demo`) writes JSON into `frontend/public/demo-data/` using the same functions the API uses (the store, `compare`, the localizer), so the demo shows what the API would. It exports a deliberately small set, not the whole database:

| Group | Evaluations (stored ids) | Why |
|---|---|---|
| golden-v3 benchmark (24 cases) | baseline `eval-09d327ad`, resilient `eval-b07a0e6d`, guided v2 `eval-71224f4b`, guided v3 `eval-c45fdf03` | the headline comparison and both guidance attempts |
| held-out benchmark (8 cases) | baseline `eval-286fe069`, resilient `eval-ffb8d521`, guided v3 `eval-dac487a9` | shows the held-out set was used |
| real-model failure lab | baseline `eval-7f1699f1`, resilient `eval-0f9152b9` | the "same fault, absorbed" story |
| reference and validation | one of each | shows how the checks themselves are tested |

The `full` and `full-v3` variants are left out: on the golden set they give the same results as the guided ones, and fewer evaluations make a clearer story. The README says they exist and where to find them. That is about 160 runs and a thousand spans, roughly a megabyte of JSON (a fraction of that compressed). A handful of the scripted example runs from the original scenarios are added so the run list has a few clean examples.

Each bake includes what the pages ask for: runs, spans, evaluations, each run's checks and suspects, the planted-fault ground truth for lab runs, and **precomputed comparisons** for a short list of useful pairs (baseline against each variant, per dataset, plus lab baseline against resilient).

**A2. `DemoSource`.** Implements the existing `DataSource` interface over those files: `kind: "demo"`, cannot start runs or evaluations, no Jaeger links (the trace is already in the page). `compare(a, b)` looks up a precomputed pair and, for a pair that was not baked, shows the same plain-language refusal style: "this demo only includes these comparisons".

**A3. Demo mode in the UI.** A build flag (`npm run build:demo`) selects the demo source, sets a relative base path so the site works under a project URL, and the shell banner already reads "Recorded demo data". Three additions, demo mode only:
- a short **"Start here" card** on the landing page with four stops (see section 5) so a visitor is not dropped into a table of 160 runs;
- an **"About this demo"** line: recorded from real local runs of `qwen2.5:7b` on a stated date, nothing here is live, link to the repository;
- the existing links that need a live API (start a run, copy the API command) are replaced by text saying so.

**A4. Privacy and honesty audit, as code.** The data is baked into a public site, so the export has a test that fails if it finds any of: the machine's user name, folder names from this machine, an email that is not `@example.com`, a drive-letter path, or a token-like string. Planning already found one thing to handle: 17 recorded stack traces contain the project's folder path after the home directory was scrubbed (`<user-home>\Local Folder\Personal\agent-blackbox\backend\...`). The export rewrites those to repository-relative paths (`backend/blackbox/...`) and the audit test then asserts none are left. The stored database is not modified.

### B. README and screenshots

A README with plain language first and technical detail below, in this order:

1. One-sentence description and the **live demo link**.
2. "What is this, for someone who has never debugged an AI agent" (about six sentences, no jargon).
3. **The 60-second story**: three screenshots (a failed run with the red span, the before/after page for the resilient agent, the before/after page for the guidance that regressed), each with one sentence.
4. **Results table**, every number from a stored evaluation with its id, and the sentence that the guidance did not work.
5. "What I learned" (five short points: measure before fixing, write predictions first, a held-out set, check the checker, report regressions).
6. How it works: one diagram (Mermaid, renders on GitHub): agent -> OpenTelemetry -> Jaeger + SQLite -> checks -> dashboard.
7. Stack and why (Ollama locally, OpenTelemetry, Jaeger, FastAPI, React, deterministic checks; zero cost, no hosted model).
8. Run it yourself (Compose, or the manual commands), and how to reproduce a number (`compare`).
9. Limits, stated plainly (one model, small n, simulated faults, prompts tested on one 7B model).
10. Repository map and links to the day-by-day docs.

Screenshots come from the demo build in headless Edge (the same method used for every UI check so far), saved under `docs/images/`, each kept small.

### C. A short moving picture

No video tool is installed. Two ways, not exclusive:

- **Automated animated GIF** built from real screenshots of the demo build (run list -> failed run with the red span -> evaluation -> before/after page -> the regression), with a caption on each frame. Reproducible and committed with the script that makes it. Needs one small development-only dependency (Pillow) installed in the project environment.
- **A recorded video** made by the owner with the Windows screen recorder (Win+G) or any free recorder, following a written 60-second script I provide. Better for sharing on social platforms; not reproducible.

### D. Hosting

GitHub Pages from a GitHub Actions workflow in this repository: build the demo, upload the folder, deploy. Free for a public repository, the URL would be `https://shubham261299.github.io/agent-blackbox/`, and hash routing needs no server rules. Two actions are the owner's: enabling Pages with the Actions source in the repository settings, and the push that adds the workflow.

Optional but cheap, and good for credibility: the same workflow runs the backend tests (Jaeger test skipped) and the frontend tests and build on every push, with a status badge in the README.

### E. Docker Compose for the whole stack

One `docker compose up --build` starting Jaeger (the existing pinned image, now with a restart policy), the API, and the UI (nginx serving the built app and forwarding `/api`). Ollama stays on the host, because the model and its memory belong to the machine, and the API reaches it through `host.docker.internal`. Notes that shape it:

- The runtime image should not carry the whole test and judge toolchain. `pyproject.toml` currently lists pytest and DeepEval (a large dependency used only on Day 7) as ordinary dependencies. Proposed: move them to optional groups (`dev`, `judge`) so the API image installs only what it runs.
- The database lives in a named volume so results survive a restart.
- The README says which parts are Compose-able (everything except the local model) and that a benchmark still takes minutes on CPU.

### F. Housekeeping

Delete the leftover `backend/data/blackbox.db`; add `.gitattributes` and a `LICENSE` (decision below); a short `CONTRIBUTING`-style "how the days are organised" pointer is not needed, the docs already do that.

## 5. The tour: what a visitor is shown

Four stops on the landing card, each one link and one sentence:

1. **A failed run.** A real run where a tool timed out: the red span is selected by default, and "Where to look first" points at it. *"The agent died here, and this is where to look."*
2. **The failure lab.** Four planted faults: three end the run or break a rule, one (malformed output) raises no error at all and only the output-contract check notices it. Trace analysis ranks where to look for each. *"Some failures are loud, one is silent."*
3. **Before and after: the fix that worked.** Baseline against resilient on the lab: 3 faults fixed, 0 broken, with the cost table. *"The agent now absorbs the failure, at a cost of three retries."*
4. **Before and after: the fix that did not.** Baseline against the guided prompt on the 24 cases: 2 fixed, 5 broken. *"A better prompt looked like an improvement and was not. The page shows exactly which cases broke."*

## 6. Rules for a public demo

- Every number on the site and in the README comes from a stored evaluation and names its id. Nothing is typed in by hand.
- The site says the data is recorded, from which model, on which date, and that nothing on it is live.
- No private details: the audit test (A4) enforces this, and the export is regenerated rather than edited by hand.
- The limits are in the README and on the comparison page, not buried.
- Do not name or link the owner's other projects or other machines' services anywhere in the repository.

## 7. Order of work, and what to cut

Each stage ends with tests, a mutation check of anything that makes a decision, a look at the real rendered result, an update of PLAN.md and the day doc, and a request to commit.

| Stage | Work | Done when |
|---|---|---|
| 0 | Reproducible dataset hashes (section 3) | the same hash on LF and CRLF, stored hashes migrated, docs updated |
| 1 | Export script with the privacy audit, and the baked data | the audit passes, the bake loads with the existing models, size reported |
| 2 | `DemoSource`, demo build, "Start here" card, About line | the full app works from static files with the API stopped, checked in the browser |
| 3 | Screenshots and the README | every number in the README traces to an evaluation id |
| 4 | GitHub Pages workflow (and optional CI) | the live URL opens the tour |
| 5 | The GIF (and the recording script) | a captioned GIF in the README |
| 6 | Docker Compose, dependency split, housekeeping | `docker compose up --build` gives a working stack |

If time runs short, cut **from the bottom**: Compose first, then the GIF (a screenshot strip is enough), then CI. Stages 0 to 4 are the showcase.

## 8. Tests

- Hash: CRLF and LF versions of one dataset hash the same; the migration maps old hashes to new ones and leaves other rows alone.
- Export: the privacy audit (each forbidden pattern is planted in a fixture and must fail the export); the output validates against the same models the API uses; every baked comparison names two baked evaluations; no baked run is missing its spans.
- `DemoSource`: behaves like the API for every method the pages call; refuses to start runs; a comparison that was not baked gives the plain-language message.
- UI: the landing card only appears in demo mode; the pages render from the demo source with no network; the start panels are absent.
- Docker: a smoke test script (not part of pytest) that starts the stack, hits `/health`, and fetches one comparison.

## 9. Decisions (all approved by the owner on 2026-10-21 as proposed)

| # | Question | Proposed default |
|---|---|---|
| D1 | Hosting | GitHub Pages from an Actions workflow (free, same repo). Alternative: a static host such as Netlify or Cloudflare Pages |
| D2 | How much to bake | The curated set in A1: 11 evaluations, about 160 runs. More makes the site heavier and the story blurrier |
| D3 | Moving picture | Both: an automated captioned GIF (adds Pillow as a dev-only dependency) and a recording script for the owner's own video. **Approved, built after the core showcase (stages 0-4)** |
| D4 | Hash fix | Normalise line endings before hashing and migrate stored hashes (changes the hash strings quoted in the docs once) |
| D5 | Split dependencies | Move pytest and DeepEval to optional groups so the API image is small |
| D6 | "Start here" card | Yes, in demo mode only, with the four stops in section 5 |
| D7 | Licence | MIT, so the repository can be reused and reviewed freely. **Approved, with a condition:** verify the repository's ownership and any third-party content before adding the file |
| D8 | CI on every push | Yes, tests and build, plus a badge. It is free for a public repository and shows the tests really run |
| D9 | Tone of the README | Plain first, first person for "what I learned", no marketing language, limits stated |
| D10 | Push timing | One push at the end of Day 6, as on Day 5. **Approved, with an exception:** push earlier if a hosting test is needed to catch Pages problems (stage 4) |

## 10. Limits to state in the README

- One model (`qwen2.5:7b`), one machine, 24 + 8 cases, one run per variant: the numbers show that the method works, not how any model in general behaves.
- The lab's faults are simulated, fire once, and are planted in one task.
- The prompt results belong to those two prompts and that model; a different model could move either way.
- The demo is recorded: it cannot run an agent, and the comparison pairs are the ones baked.
- A check can be wrong (one was, and was fixed under a new dataset version with the old results re-judged, never edited).

## 11. Done when

A stranger can open one link, follow four stops, and understand what was built, what worked, what did not, and how the numbers were measured; and a technical reviewer can clone the repository, start it with one command (or the manual steps), reproduce a comparison, and find the evaluation id behind every number in the README.

## 12. Progress log

### Stage 0: reproducible dataset hashes (done, 2026-10-21)

- **The rule.** A dataset's hash is now taken after normalising line endings (`content_hash` in `evals/cases.py`), so the same cases hash the same on Windows, Linux, macOS and in Docker. Pinned by tests: `golden-v2` `c703c519168a`, `golden-v3` `82acd02d8a18`, `holdout-v1` `8c7eb9ea4eb0` (unchanged, it already had LF endings). What Days 3-5 stored on Windows was `e6a742cd5224` and `7bb5852c6198`.
- **The migration.** On every `Store` start, evaluation rows whose dataset version and stored hash both match the old Windows value are rewritten to the new hash; nothing else is touched (a hash the old scheme never produced, or the same string under another dataset, is left alone), and running it again changes nothing. Dry-run on a copy of the real database first: 17 `golden-v2` and 8 `golden-v3` evaluations moved, 6 `holdout-v1` unchanged, 31 evaluations before and after. Then applied to the real database; `compare` still works and now prints the new hash. No evaluation result changed, only the identifier of the dataset content.
- **`.gitattributes`** (`* text=auto eol=lf`, binary types listed) keeps the repository consistent from now on. Checked that it changes no committed file: staging a renormalised tree changed only the two intentionally edited source files.
- **Docs.** No document quoted the old hashes (only one invented example message in a frontend test), so nothing needed rewriting.
- **Tests:** 11 new (`test_dataset_hash.py`), 387 backend in all. Mutation-checked, all caught: hashing raw bytes again, a legacy hash equal to the new one, migration ignoring the version, migration rewriting every row of a version, migration never running, migration writing the wrong value.

### Stage 1: curated export with a privacy audit (done, 2026-10-22)

- **Command.** `python -m blackbox.export_demo` (from the repository root or `backend/`) reads the local database, never writes to it, and replaces `frontend/public/demo-data/`. It refuses to overwrite a folder that is not an earlier export. Exporting twice gives byte-identical files (compact JSON, sorted keys, LF endings), so a re-export shows a diff only when results changed.
- **What it holds.** 173 runs (the 128 benchmark and lab cases of the 9 curated evaluations, 24 reference and 11 validation runs, 2 lab control runs, and 8 scripted example runs from the original scenarios), 883 spans, 11 evaluations (the ids in section 4A), about 2 MB of JSON. Per run: spans, its checks and suspects (taken from the curated evaluation that holds it, not from a later one that is not exported), and the planted faults for lab runs. The headline numbers match the stored evaluations: baseline 19/24, resilient 19, guided v2 16, guided v3 17 on `golden-v3`; 5/8 for each of the three on `holdout-v1`.
- **Comparisons are not a hand-picked list.** Every ordered pair of the 11 evaluations is run through the real `compare`: 20 fair pairs are baked in full, and the other 101 are baked as the exact refusal the API would give ("different cases", "different kinds", "cannot be compared with itself"). So the demo's compare page can answer any pair, with the same plain-language reasons as the live app, and the "only these comparisons" case from the plan does not arise.
- **Layout.** `manifest.json` (format, model, dates the runs were recorded, counts, evaluation ids), `runs.json`, `evals.json`, `evals/<id>.json`, `spans/<run>.json`, `run-evaluations/<run>.json`, `faults.json` (only runs that have planted faults), `scenarios.json`, `comparisons/index.json` (`ok`: pair to file, `refused`: pair to reason) and `comparisons/<a>__<b>.json`.
- **Privacy, as code** (`publish_safety.py`). `publishable` rewrites the machine-specific part of stack-trace paths (`<user-home>\<folders>\agent-blackbox\backend\x.py` becomes `backend/x.py`; paths inside the virtual environment become `site-packages/...`). `audit` is the independent check that runs on the result and stops the export if it finds: the home placeholder, a drive-letter or home-folder path, an email that is not `@example.com`, token-shaped strings (GitHub, API keys, Slack, AWS, bearer, JWT, private keys), or this machine's account name or the folders between the home folder and the repository (looked up at run time, so no personal name is written in the repository). Every reference between files is checked as well (every case points at an exported run, every run has its spans and checks). The same audit runs as a test over the committed data on every test run, so hand-editing or re-exporting on another machine cannot slip something through. The 17 stored stack traces that named this machine's folders are rewritten; the database is untouched.
- **Shared code.** The per-run evaluation the API serves moved to `evals/run_evaluation.py` so the export and the API cannot drift apart; `Store.find_eval_case_for_run` takes an optional `among` to look only inside the exported evaluations.
- **Lab control runs.** Found while building stage 2: a lab report links to its untouched control run, which no case ran, so the first export left those links dead. The export now collects the runs a case's note names, and the link check covers notes and the tour. Also added: a `tour` in the manifest (ids of the failed run, the lab and the two before-and-after pairs, looked up from the data).
- **Tests:** 65 new (`test_demo_export.py`), 452 backend in all. 35 mutations of the rules, all caught after one test was added (an evaluation case pointing at an unexported run was only noticed through the comparison check): paths keeping backslashes, the virtual-environment prefix kept, only the first path rewritten, any or every email allowed, drive-letter and name matching loosened, short and generic names kept, home placeholder or home-path rule dropped, keys or lists not audited, a secret rule dropped, the audit or link checks skipped, evaluations exported without the `among` limit, all scripted runs exported, faults or refusals not recorded, an old export not removed or a stranger's folder overwritten, rewriting skipped, a missing evaluation tolerated, CRLF written. Five more mutations of the committed data (a path, an email, a changed headline number, CRLF endings, a dropped evaluation) are caught by the data tests.

### Stage 2: the demo site (done, 2026-10-22)

- **`DemoSource`** (`frontend/src/api/demo.ts`) implements the existing `DataSource` over the exported files: `kind: "demo"`, cannot start runs or evaluations (the attempt is refused with a plain sentence), no Jaeger link, each file fetched once and a failed fetch not remembered. It answers as the API does: a run or evaluation that is not there is a 404 with the API's wording; a comparison pair is either baked or refused with the API's own reason (422, which the compare page already knows how to show). A server error or no network is "unreachable", and the error card then says the demo data could not be loaded instead of telling a visitor to start a local API.
- **Build.** `npm run build:demo` (`vite build --mode demo`) writes `frontend/dist-demo/` with relative paths, so it works under a project URL, and with `public/demo-data` included (3.4 MB, about 90 kB of JavaScript compressed). The normal `npm run build` is unchanged and does not carry the data (`publicDir` is off outside demo mode). `npm run dev:demo` serves the same thing in development. Checked by serving the build under a subfolder (`/agent-blackbox/`) with a throwaway static server and opening it in headless Edge: landing, a failed run, a before-and-after page and a refused pair all load and link correctly; the page is usable at 520 px wide.
- **"Start here" card** (demo only, top of the landing page): four stops from the manifest's `tour`, each a link and a sentence. The sentences of the two before-and-after stops are built from the stored comparisons (3 of 4 faults with no effect, 0 made worse, 3 extra retries; 24 cases, 2 fixed, 5 broken), not typed in; without the comparison they say what the page shows, with no number. The stop-1 sentence said the failed step is highlighted by default; the page actually opens on the whole run, with the failed step red in the waterfall and named under "Where to look first", so the sentence was changed to say that.
- **"About this demo"** footer (demo only, every page): the model, the dates the runs were recorded (read from the data), the counts, "Nothing is live", and the link to the repository.
- **Demo-mode differences:** no start-a-run form, no run-an-evaluation panel, no polling for new data.
- **Tests:** 39 new frontend tests (`demo.test.ts`, `tour.test.ts`, `Demo.test.tsx`), 167 in all. 28 mutations: 26 caught immediately; one survivor was a real gap (a missing file read as "offline" instead of "not in this demo") and got a test; the last ("tour shown on the live page") is an equivalent mutant, because the live source has no demo information and the card renders nothing without it. The guard stays as a second line. Backend: 10 more mutations of the control-run and tour code, two survivors (control run hidden by being an example run; tour missing from the manifest), both now caught.

### Stage 3: README and screenshots (done, 2026-10-22)

- **`README.md`** (there was none): one-sentence description and the demo link, a plain-words explanation, the 60-second story with three screenshots (a failed run, the fix that worked, the fix that did not) each linking to the same page in the demo, a results table with the evaluation id next to every number, five lessons in first person, a Mermaid diagram, the stack and why, how to run it and reproduce a number, the limits, and a repository map. The demo URL assumes GitHub Pages is enabled for this repository (stage 4); until then those links do not resolve.
- **Screenshots** (`docs/images/`, 60 to 160 kB each, taken from the demo build served under a subfolder in headless Edge): `failed-run.png`, `fix-that-worked.png`, `fix-that-did-not.png`, plus `start-here.png` (the landing card, for the GIF and posts).
- **The README's numbers are tested** (`test_readme_numbers.py`, 6 tests) against the committed demo data: every evaluation id it names exists; each single-evaluation row's pass count is that evaluation's; the held-out row is 5 of 8 for all three; the fixed/broken counts and the lab's cost (3 extra retries, 11 to 13 tool calls) are the baked comparisons'; the three demo links are exactly the tour's three stops and point at runs and pairs that exist; the screenshots exist. 10 mutations of the README (a wrong count, a reversed comparison link, a dead run link, a missing image, ...) all caught after one test was added for the reversed link.
- **Wording kept honest:** the demo holds 11 of the 31 evaluations in my local database; the held-out set is described as not a clean test for the third prompt; no number is in the README without an id or a stored comparison behind it.
- **Still open for the README:** the CI badge (stage 4), the Compose instructions and the licence line (stage 6), and the GIF (stage 5).
