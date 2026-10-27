# Agent Blackbox: notes for Claude

A local-first "flight recorder" for AI agents: a small customer-support agent on a local model (`qwen2.5:7b` via Ollama), recorded as OpenTelemetry spans, judged by deterministic checks, with a before/after comparison of agent versions. Public repo, personal GitHub `Shubham261299`. The live recorded demo is https://shubham261299.github.io/agent-blackbox/ (GitHub Pages, deployed by a workflow on every push to `main`).

Audience: hiring managers, HR, founders first (plain language, every number from a stored evaluation, limits stated); technical reviewers second.

## Where things stand

Days 0-6 and 8 are built and pushed. Day 7 is optional (code-level guards: lookup-first, argument grounding; DeepEval cross-check; judged subset of 6) and not started. **Waiting on the owner:** the test with 2-3 people outside tech, `docs/plain-demo-test.md`. What they trip on is the next work: change those words, and the checks that guard them.

## Read in this order

1. `PLAN.md`, "Resume here": status, commands, stored evaluation ids, per-day checklists.
2. `docs/day-8-plain-demo-plan.md` (latest work; progress log at the end), then `docs/day-6-showcase-plan.md`.
3. `BRIEF.md`: design decisions and the findings of each day (Day 5 explains why the results are what they are).
4. `README.md`: what a stranger sees. Its numbers are tested against the demo data.

## Rules (from the owner; do not break)

- **Do not commit or push without a go-ahead.** Commit locally per stage only when asked or already approved; the owner pushes.
- Plan a day first (`docs/day-N-...-plan.md`), get approval, build in numbered stages, **mutation-check every new rule** (break the code on purpose, confirm a test fails), update PLAN.md / BRIEF.md / the day doc, then ask before committing.
- Write predictions before real-model runs; freeze prompt versions before their first run; **never edit a dataset to flatter a variant** (new version, widening only, then `rescore`).
- Zero cost, local only: no hosted models, no silent fallback to one. Public repo: no private details.
- Scope of this repo (owner's decision): a standalone project. Do **not** add the owner's portfolio, job titles, an about-me, contact details or other projects, and do not name other projects or machines' services anywhere.
- Plain words first, first person for lessons learned, no marketing language, limits stated. The demo's numbers come from stored results, never typed.
- Ports 8000, 8001 and 8765 belong to the owner's other projects: use a free port (the UI proxy takes `BLACKBOX_API`). Start servers in the background, record the PID, stop by PID, **never by port**, and never kill a process you did not start. The `jaeger` container on this machine is the owner's; test Compose under another project name (`-p`), other ports and `BLACKBOX_JAEGER_NAME`.

## Commands (Windows, repo root, venv `.venv`)

- Backend tests: `.venv\Scripts\python -m pytest` (511; one needs Jaeger, `-m "not integration"` skips it). `pip install -e ".[dev]"` for tests and Pillow; `".[judge]"` adds DeepEval (unused so far).
- Frontend (in `frontend/`): `npx tsc --noEmit`, `npm test` (339), `npm run build` (live app), `npm run build:demo` (static demo to `dist-demo/`), `npm run dev` / `npm run dev:demo`.
- Live app: `uvicorn --app-dir backend --factory blackbox.api.main:create_app --port <free>`; whole stack: `docker compose up --build`.
- Evaluations: `python -m blackbox.evals run --mode reference|faults|ollama|faultlab|faultlab-ollama [--variant ...] [--dataset golden-v3|holdout-v1]`, `compare <before> <after>`, `rescore <eval> --dataset golden-v3`.
- **Rebuild the demo after any change to results, wording or pages:** `python -m blackbox.export_demo` (reads `data/blackbox.db`, writes `frontend/public/demo-data/`, fails on anything private), then `npm run build:demo`; `python scripts/make_demo_gif.py` and `python scripts/make_og_image.py` regenerate the GIF and the link-preview card (need a browser and Pillow). Re-exporting changes numbers the README and tests pin; the tests say what to update.

## How it is built

- `backend/blackbox/`: `agent/` (loop, tools, variants, guidance v1-v3), `telemetry/` (spans, redaction, SQLite copy), `evals/` (datasets, checks, localizer, `compare`, `rescore`, failure lab), `faults/`, `api/` (FastAPI), `export_demo.py` + `publish_safety.py` (the demo bake and its privacy audit), `store/db.py` (SQLite, migrations).
- `frontend/src/`: `api/` (a `DataSource` interface: the live API or `demo.ts` over the baked JSON), `pages/`, `components/`, `content/` (front-page words `story.ts`, plain-language text `plain.ts`), `lib/`.
- **Two modes, one codebase.** The recorded demo calls `setPlainWords(true)` at start-up (`lib/plain.ts`): everyday names (`metricLabel`, `kindLabel`, `variantLabel`...), "In plain words" boxes, technical parts folded behind `<Technical>`, a run told step by step, the front page at `#/` and the guided tour (`?tour=N`). The live app keeps the technical words and opens on the run list. New wording must exist in both vocabularies.
- Evaluations are judged by deterministic checks only. Two gate pass/fail (task completion, policy compliance); the others are reported.

## Tests that guard the public face (do not weaken them)

`test_demo_export.py` (privacy audit and file consistency), `test_readme_numbers.py` (README numbers and links vs the demo data), `test_dataset_hash.py` (hashes ignore line endings), `pages/DemoAudit.test.tsx` (no jargon on any real demo page), `content/readability.test.ts` (reading grade about 4, no long sentences), `test_workflows.py` / `test_compose.py` (the CI, Pages and Docker files, checked as text).

## Environment gotchas

- Edit with the Edit/Write tools; Bash heredoc quoting of multi-line patches is fragile (backslashes, quotes). Put patch scripts in the scratchpad.
- Headless Edge: give it a private `--user-data-dir` (an already-open Edge takes the request over and writes nothing), write screenshots into an ordinary folder (not `tempfile.mkdtemp()`), and verify narrow layouts at 520 px.
- `rm -rf "$VAR"/*` is blocked: use `"${VAR:?}"`. `tar -C` / `-f` with a `C:` path is read as a host; `cd` first. `pip install` needs PyPI, which was unreachable for about 20 minutes once: retry.
- `.gitattributes` forces LF; the working tree on Windows may show CRLF warnings, which are harmless.
- The working database `data/blackbox.db` is git-ignored; the demo data in `frontend/public/demo-data/` is committed and is what CI and the tests use.
