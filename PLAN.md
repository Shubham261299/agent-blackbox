# Agent Blackbox — Weekly Plan

## Resume here (read this first in a new chat)

**Status:** Days 0-5 done. Days 0-4 are pushed (`origin/main` = `10ff969`); Day 5 is committed locally and is pushed at the end of the day when the owner says so. Day 6 (showcase) is next and not started. Push only when the owner says so.

| Day | Topic | Status | Commits (local) |
|---|---|---|---|
| 0 | Spike | done | in scaffold |
| 1 | Instrumented agent | done, pushed | `15252b8`, `b5ce783` |
| 2 | Dashboard | done, pushed | `a64ee26`, `90af84c`, `b251747` |
| 3 | Evaluation | done, pushed | `92d7e3a`, `ba26ea0`, `dc67159` |
| 4 | Failure lab | done, pushed | `1335e6d` backend, `3dc832d` UI, plus the docs commit |
| 5 | Fix and compare | done, not pushed | `ac2d019`, `2c9e27b`, `0554030`, `0035a2f`, `7d88e71`, `1dc1377`, plus the stage 6 UI commit |
| 6 | Showcase | in progress (stage 0 done) | |
| 7 | Buffer / stretch | not started | |

**Standing rules from the owner (do not break):**
- Do not commit or push without a go-ahead. Commits are made locally per stage; the owner pushes (or says "push").
- Personal GitHub account `Shubham261299` (a work account also exists on this machine). Repo: https://github.com/Shubham261299/agent-blackbox.git, **public**: no private details in commits or docs.
- Zero cost, local only: `qwen2.5:7b` via Ollama, no hosted models, no Confident AI, no silent fallback to a hosted model.
- Audience is hiring managers and HR: plain language first, every number from a recorded run, limits stated.
- Plan each day first (a short `docs/day-N-...-plan.md`), then build, then mutation-check the new rules, then update this file, BRIEF.md and the day doc, then ask before committing.
- Use the design/artifact skills for UI. Landing page is the run list.
- Decisions already taken: 24 golden cases (golden-v3 current: golden-v2 with C1/C4 answer patterns widened after triage; v2 stays loadable), option B (only the order id of an address change is verified; keyed digest "option A" is a later extension), judged DeepEval subset of 6 on Day 7, qwen2.5:7b only.

**How to run things (Windows, from the repo root; venv is `.venv`):**
- Tests: `.venv\Scripts\python -m pytest` (467 backend, 1 needs Jaeger) and `cd frontend; npm test` (167), `npx tsc --noEmit`, `npm run build`.
- API: `uvicorn --app-dir backend --factory blackbox.api.main:create_app --port 8000`; UI: `cd frontend; npm run dev` (port 5173). **Ports 8000, 8001 and 8765 are used by other projects on this machine** (check with `Get-NetTCPConnection -LocalPort <p> -State Listen` before starting; never kill a process you did not start). Pick a free port, start the API on it, and point the UI at it: `$env:BLACKBOX_API="http://127.0.0.1:<port>"; npm run dev -- --port 5190 --strictPort`. The Windows venv launcher spawns a child process, so record the listener PID (not just the launcher) to stop it.
- Jaeger: `docker compose up -d` (container `jaeger`, UI 16686; no restart policy, start it again after a Docker restart).
- Evaluations: `python -m blackbox.evals run --mode reference|faults|ollama|faultlab|faultlab-ollama [--variant baseline|resilient|guided|full|guided-v3|full-v3] [--dataset golden-v3|holdout-v1]`; `compare <before> <after>`; `rescore <eval> --dataset golden-v3`. Real-model runs take minutes on CPU.
- Start servers in the background and **record the PID; stop by PID with `taskkill /T`, never by port.** Database: `data/blackbox.db` (git-ignored).
- Tooling quirks: multi-line patch scripts go in the scratchpad via the Write tool (Bash heredoc quoting is fragile); screenshots via headless Edge.

**Where the knowledge lives:** `BRIEF.md` (pitch, constraints, per-day findings), `docs/day-3-evaluation-plan.md`, `docs/day-4-failure-lab-plan.md`, this file (checklists and results).

**Stored real-model results (local DB, git-ignored; rerun if the DB is gone):** benchmark eval-5b8f6d3c (19/24), reference eval-b6676352 (24/24), scripted lab eval-3623c6ad (4/4), real-model lab eval-92639afd (4/4), validation eval-a5479ac6 (11/11), holdout baseline eval-286fe069 (5/8, holdout-v1). Day 5 variants on golden-v2: baseline eval-7410381c 19/24, resilient eval-7caf9bfa 19/24, guided eval-ff0b3df7 15/24, full eval-a37cc205 15/24 (and eval-67a0cc90); holdout: resilient eval-ffb8d521, guided eval-bfaf8088, full eval-26376285 (all 5/8); golden-v3 rescores of the above: baseline eval-09d327ad 19/24, resilient eval-b07a0e6d 19/24, guided eval-71224f4b 16/24, full eval-08ae09b9 16/24, guided-v3 eval-c45fdf03 17/24, full-v3 eval-1f87936d 17/24. v3: guided-v3 eval-212048d0 (golden 15/24) and eval-dac487a9 (holdout 5/8), full-v3 eval-a8e43948 (golden 15/24), eval-7d90c662 (holdout 5/8), lab eval-55a817a2 (4/4); real-model lab: baseline eval-7f1699f1, resilient eval-0f9152b9, guided eval-4ac00a2b, full eval-1f6b2d31.

**Day 6 starting point (not yet planned in detail):** a static demo mode with prebaked real runs (the `DataSource` interface already allows it; add a `compare` entry to the baked data), a short demo video/GIF, README (plain language first, every number from a stored evaluation, limits stated), Docker Compose. The story to tell: the agent runs, a tool fails, click the red span, the score drops; the resilient agent absorbs the same fault, the compare page shows 3 faults fixed and 0 broken at a stated cost; and the honest counter-example, guidance that regressed and the harness that caught it. Day 7 candidates: code-level guards, DeepEval cross-check, judged subset.
---

Rough target, ordered by what the audience sees first. A day is done only when its **Done when** is met. If something overruns, cut from stretch, not from Day 6.

## Day 0 — Spike and brief (gate) — DONE
- [x] Environment check (Python 3.13 system / 3.12 venv, Node 24, Docker 29, Ollama 0.40, CPU-only inference, 16 GB RAM)
- [x] Jaeger up via Docker; nested OTel trace with `run_id` reaches it (Jaeger v2, query API at `/api/v3`)
- [x] Ollama model with tool calling picked — carried to Day 1 and resolved there: `qwen2.5:7b` works as judge (~49 s per judged metric on CPU) and as a tool-calling agent. Alternatives not yet tried: `llama3.1:8b`; fallback `llama3.2:3b`. Exact tokens/sec not measured.
- [x] Trace -> DeepEval case; metrics run on Ollama, telemetry off, zero non-loopback connections
- [x] `run_id` joins trace, eval result, SQLite row (0 orphan spans; stored `trace_id` resolves in Jaeger)
- **Done when** all three spike checks pass or fallback chosen. No Day 1 before this. -> **Met.**
- Findings are recorded in BRIEF.md ("Spike results"). Spike scripts were throwaway and live outside the repo.

## Day 1 — Instrumented agent — DONE
- [x] Model interface: scripted + Ollama implementations
- [x] Hand-rolled agent loop, 4 mock business tools (lookup_order, check_refund_policy, issue_refund, update_shipping_address)
- [x] Spans: run / model call / tool call; `gen_ai.*` attributes; error recording
- [x] Redaction — implemented as a wrapping `RedactingExporter` (OTel processors only see read-only finished spans), applied to both Jaeger and SQLite exports
- [x] Dual export: OTLP -> Jaeger + SQLite spans table
- [x] FastAPI: start run, fetch run, list runs, fetch spans (Pydantic models)
- [x] Tests: 35 pytest tests (34 unit + 1 Jaeger integration); redaction and error-status tests were mutation-checked
- **Done when** one run shows a correct nested trace in Jaeger and the same spans in SQLite. -> **Met** (verified live: 6/6 spans in both, parent links and error statuses match).
- Day 0 carry-over resolved: `qwen2.5:7b` completed the full lookup -> policy check -> refund -> answer sequence via native Ollama tool calling (28.7 s total on CPU; first model call 12.3 s incl. model load, later calls 2.8–3.9 s; real token counts recorded). One run only — not yet a reliability measurement; `llama3.1:8b` not tried.

## Day 2 — Dashboard core — DONE
- [x] Vite + React + TS (exact-pinned deps), typed API client behind a `DataSource` interface (live API now; prebaked demo data on Day 6)
- [x] Run list: status pills (icon + label), summary strip, status filter, start-run panel (scripted scenario or local Ollama). Scores column deliberately omitted until Day 3 produces real scores.
- [x] Trace waterfall (indented span tree + shared time axis), table twin of the waterfall, legend, hover/focus tooltip, arrow-key navigation
- [x] Span inspector: facts, tool args/output, prompt transcript, events/exceptions, all attributes; redacted values shown as chips with a count; opens on the failed span by default
- [x] Light/dark/system theme, phone-width layout, API-down state with start command, running state, empty and not-found states
- [x] Backend additions: `GET /scenarios`, `start_offset_ms` on spans (exact integer math; epoch ns exceed JS safe integers)
- [x] Tests: 44 frontend (vitest + Testing Library) and 39 backend; frontend suite run 6x with no flakes
- **Done when** you can click through a real run and see timing and errors. -> **Met**, checked in rendered screenshots (Edge headless) at desktop and narrow width, light and dark, on a real `qwen2.5:7b` run, a failed-tool run and a failed run.
- Not done: no real-browser interaction test (clicks/keys are covered by Testing Library, not a real browser); Day 6 owns the static demo build.

## Day 3 — Evaluation — DONE (committed locally; detail in [docs/day-3-evaluation-plan.md](docs/day-3-evaluation-plan.md))
- [x] 3.1 Seed orders 46-49; case schema; 24 golden cases (normal 8, ambiguous 4, wrong-tool 4, tool-failure 4, constraint 4); dataset self-consistency tests
- [x] 3.2 Trajectory adapter: stored (redacted) spans become one plain object that every check reads
- [x] 3.3 Seven checks: task completion and policy compliance gate the run; tool correctness, argument correctness, step efficiency, trace completeness and latency are reported. A catalog of 10 planted faults proves each check catches its fault and nothing else (zero false alarms); each rule is mutation-checked
- [x] 3.4 Shared `RunService`; `eval_runs`/`eval_cases`/`eval_results` tables; eval runner, CLI (`python -m blackbox.evals run --mode ollama|reference|faults`) and API
- [x] 3.5 Real benchmark: `qwen2.5:7b`, seed 0, golden-v2: **19 of 24 runs passed both gating checks** (eval-5b8f6d3c, 4 minutes on CPU). Every failure was triaged (see BRIEF.md "Day 3 findings")
- [x] 3.6 UI: evaluations list, report (headline, per-check bars, per-category bars, case x check matrix, failing first), Evaluation card on each run, Findings on the span, validation shown as detection rate and false alarms
- [x] 3.7 Docs updated; committed locally
- [ ] 3.8 *(Day 7)* DeepEval adapter, tool-correctness cross-check, judged subset of 6 labelled as estimates
- [ ] 3.9 *(later, only if needed)* keyed digest of sensitive args so address values can be verified from a redacted trace
- **Done when** `pytest` passes with the exact fault-catalog matrix, a stored real-model evaluation exists, and the UI shows it per case and metric with a path to the failing span. -> **Met.**
- Numbers: 192 backend tests (incl. 1 Jaeger integration) and 69 frontend tests; frontend suite repeated 3x with no flakes.
- Limits: n=24, one run per case, one model. Address values are not verified (option B). No judge-model metrics yet.

## Day 4 — Failure lab — DONE (committed locally; detail in [docs/day-4-failure-lab-plan.md](docs/day-4-failure-lab-plan.md))
- [x] Four injected faults, planted through wrappers so agent code is untouched: tool timeout, malformed tool output, wrong tool choice, model failure. Ground truth (the span a fault was planted in) is recorded outside the trace; nothing in the trace says a fault was planted
- [x] Failure localization: ranked suspects from the stored trace and the checks alone (never the injected fault, never stack traces). Scored per fault as hit@1 / hit@3
- [x] New check, `tool_output_contract`: per-tool contracts for successful outputs. It is the only thing that notices the silent fault, and it joins the planted-fault catalog (now 11 faults, each caught by exactly the expected checks)
- [x] Control vs faulted comparison for every fault (same task, same model), with the effect stated in words
- [x] Lab runs on the scripted model (instant, in pytest and a UI button) and on the real model (`--mode faultlab-ollama`)
- [x] UI: failure-lab report (one card per fault), a "fault planted" callout and badge on the run, "Where to look first" on every run's Evaluation card
- [x] Tests: 250 backend and 82 frontend; localizer, contracts, injector and contract check mutation-checked
- **Done when** each fault is reproducible and localized. -> **Met**, with the limits below.
- Results (scripted and `qwen2.5:7b`, seed 0): all four faults located at rank 1. Effects: timeout and model failure end the run; malformed output is silent (gating checks pass; the real model quietly retried the lookup and finished correctly); wrong tool fails the policy check but the real model recovered afterwards.
- Limits: four faults on one task is a demonstration, not a benchmark of localization. The localizer is a heuristic tuned while building the lab (the first version ranked the run span above the real culprit; fixed and tested). Scripted runs cannot adapt after a fault.

## Day 5 — Fix and compare — DONE (committed locally; detail and every number in [docs/day-5-fix-and-compare-plan.md](docs/day-5-fix-and-compare-plan.md))
- [x] Held-out set `holdout-v1` (8 cases) written before any tuning; baseline 5/8
- [x] `AgentConfig` presets `baseline`, `resilient`, `guided`, `full`, `guided-v3`, `full-v3`; the baseline is byte-identical to the Day 1-4 agent. Resilience: retry with a limit (2 retries) for tool timeouts and model errors, runtime enforcement of the tool output contracts, retries recorded as events on the one span. Guidance: v1 (frozen), v2 and v3 prompts and tool descriptions (each pinned by a test)
- [x] `variant` on runs and evaluations (with a DB migration), `--variant`, `compare` (logic, `GET /evals/compare`, CLI) that refuses an unfair comparison and says why, `rescore` (re-judge stored runs against another dataset version, no model run), localizer tier 4 "retried"
- [x] Real-model runs: 4 + 2 variants on golden, 5 on the held-out set, 6 failure-lab runs, noise-floor repeats (0 of 24 flipped twice). golden-v3 (C1/C4 answer patterns widened after triaging every failing answer) is now the default dataset
- [x] UI: comparison page (`#/compare/<before>/<after>`: what changed, case by case with broken first, by check, cost, how to read it), compare picker on the evaluation report, agent chip on runs and evaluations, "retried" badge and inspector note on spans
- [x] Tests: 376 backend (1 needs Jaeger) and 128 frontend; every new rule mutation-checked
- **Done when** a measured before/after table exists, stored from real runs. -> **Met.**
- **Results (qwen2.5:7b, seed 0, golden-v3, 24 cases):** baseline 19; resilient 19 (0 fixed, 0 broken, no cost on clean runs); guided v2 16 (2 fixed, 5 broken); guided v3 17 (1 fixed, 3 broken). On the real-model failure lab, resilient turned timeout, model failure and malformed output from harmful to harmless (3 fixed, 0 broken; cost 3 retries, +15% median time). Guidance removed every policy violation but cost task completion (22 -> 16/17 of 24). **Recommended agent: resilient.**
- Limits: one model, n = 24 + 8, one run per variant; the held-out set was not clean for v3 (v2's results were read first). Invented amounts and the cannot-cancel case are not fixed by prompt wording: a code-level guard (lookup-first enforcement, grounding every tool argument in the customer's message) is a Day 7 option.

## Day 6 — Showcase (in progress; plan and decisions in [docs/day-6-showcase-plan.md](docs/day-6-showcase-plan.md))
- [x] Stage 0: dataset hashes ignore line endings (reproducible on any OS), stored hashes migrated, `.gitattributes`; 387 backend tests
- [x] Stage 1: `python -m blackbox.export_demo` bakes 173 runs, 11 evaluations and every pair of them through the real `compare` (20 fair, 101 refused with the API's reasons) into `frontend/public/demo-data/` (~2 MB), with a path rewrite and an independent privacy audit that also runs as a test over the committed data; 452 backend tests
- [x] Stage 2: `DemoSource` over the baked files, `npm run build:demo` (relative paths, checked under a subfolder in headless Edge), a four-stop "Start here" card whose numbers come from the stored comparisons, an "About this demo" footer; 167 frontend tests
- [x] Stage 3: README (plain language first, ids beside every number), three screenshots in `docs/images/`, and a test that checks the README's numbers and links against the demo data; 458 backend tests
- [x] Stage 4: `ci.yml` (backend and frontend tests and builds) and `pages.yml` (deploy the demo), CI badge in the README; rehearsed on Linux in containers, not yet run on GitHub; 467 backend tests. Owner: enable Pages (Source: GitHub Actions) and push
- [ ] Static demo mode with prebaked real runs (DataSource interface already allows it), deployed on free hosting
- [ ] Demo video/GIF (agent runs -> tool fails -> click red span -> score drops -> fix -> improves)
- [ ] Screenshots, README (plain-language top, technical below), Docker Compose for the whole stack
- [ ] Optional: restart policy for the Jaeger container; delete leftover `backend/data/blackbox.db`

## Day 7 — Buffer / stretch
- [ ] DeepEval adapter; ToolCorrectnessMetric cross-check against our own check
- [ ] Judged subset of 6 cases (task completion, argument correctness, step efficiency) with the local judge, labelled as estimates; judge agreement vs hand labels
- [ ] Optional keyed digest of sensitive args ("option A")
- [ ] Possible policy check: agent echoing the customer record (email) in its answer
- [ ] Slipped items from earlier days

## Rules
- Every README number comes from a recorded run.
- One model loaded at a time (16 GB RAM); cap WSL memory.
- Bulk runs use the scripted model; real Ollama for showcase runs and live-path validation.
