# Agent Blackbox — Project Brief

Tagline: **Agent Flight Recorder** — local-first observability and evaluation workbench for AI agents.

## Pitch
Run an agent, record every important operation, inspect the trace, evaluate the execution, inject a failure, and compare the original run with the repaired run — from one dashboard.

The differentiator is connecting three things:
1. **Observability** — what happened, in what order, how long, where it failed.
2. **Evaluation** — did the agent finish the task, use the right tools, obey constraints, avoid wasted steps.
3. **Debugging** — which span caused the failure, and did the fix measurably improve the next run.

## Audience
Hiring managers and HR first (must work without being run: static demo, video, plain-language README), technical reviewers second (architecture, stack, measured results).

## Constraints
- Zero cost: Ollama locally, Jaeger in Docker, DeepEval locally. No hosted models, no Confident AI / hosted eval platform, DeepEval telemetry off.
- Never silently fall back to a hosted model.
- Machine: 16 GB RAM, Docker allowed. Never load agent model and judge model at the same time.
- No custom tracing protocol; no full observability platform. Jaeger is the real OTLP backend and validation target.

## Architecture boundaries
- Agent executes tasks (model behind an interface: scripted/replay for tests, Ollama for showcase).
- OpenTelemetry records execution (nested spans, attributes, events, status, redaction processor).
- Jaeger stores/displays exported traces.
- SQLite holds app-level run metadata, a copy of spans for the UI, eval results and comparisons.
- DeepEval + deterministic checks evaluate outputs and trajectories. Preferred design: **evaluate from the recorded OTel trace** via an adapter (to be confirmed by spike).
- UI (Vite + React + TS) joins everything on a shared `run_id`.

## Key design decisions
- Dual export: OTLP -> Jaeger, plus a SQLite span copy (Jaeger's query API is not a stable contract; default storage is in-memory).
- Redaction in an OTel SpanProcessor, before export.
- Model-call spans use OTel GenAI semantic conventions (`gen_ai.*`).
- "Repaired run" = a code/config fix toggle (retry+timeout, tool-output schema validation, better tool description), compared over N runs. Not automated self-repair.
- LLM judge is optional; deterministic checks are the backbone. Judge validated against a hand-labeled subset.

## Metrics
Task completion, tool correctness, argument correctness, step efficiency, failure localization, trace completeness, latency (total + per span), regression rate. Every published number comes from a recorded run.

## Out of scope (v1)
Custom tracing DB/protocol, auth/multi-user, hosted deployment of the backend, automated self-repair, OTel metrics/logs pipelines, auto-instrumentation libraries.

## Spike (gate before building) — PASSED
1. Nested OTel trace reaches Jaeger with a `run_id` attribute.
2. A trace converts to a DeepEval case; one metric runs against Ollama with no network calls.
3. `run_id` joins trace, eval result and a SQLite row.
Fallback if (2) fails: deterministic-only evals; local judge becomes a separate milestone (not needed).

## Spike results (what was actually verified)
- **Jaeger**: `jaegertracing/jaeger` is v2. Old `/api/traces` and `/api/services` return 404; use `/api/v3/...` (OTLP-shaped JSON, nanosecond timestamps). **Pin the image tag in Docker Compose** (spike used `latest`). In-memory storage: traces vanish on restart.
- **Trace in Jaeger**: parent links, durations, `run_id` on every span, exception event and ERROR status all round-trip correctly.
- **Evaluate-from-trace works (design B)**: spans fetched from Jaeger were adapted into an `LLMTestCase` plus DeepEval's `_trace_dict`. `_trace_dict` is a *private* attribute and agentic metrics (e.g. `TaskCompletionMetric`, `requires_trace=True`) read it, so **pin the DeepEval version** and add an adapter test that fails loudly on format change.
- **Metrics tried**: `ToolCorrectnessMetric` (deterministic, 1.0, instant) and `TaskCompletionMetric` with `qwen2.5:7b` judge (0.95, ~49 s on CPU). Not yet tried: step-efficiency, plan/trajectory metrics, failing runs.
- **Hosted-model trap**: metrics default to a hosted OpenAI client when no `model` is passed (spike only failed closed because no key was set). **Rule: always pass an explicit local model, via one factory function.**
- **Telemetry**: `DEEPEVAL_TELEMETRY_OPT_OUT=YES`; socket guard recorded zero non-loopback connections. Keep the guard in the test setup. Telemetry-on was not tested.
- **Extra dependency**: DeepEval's `OllamaModel` needs the `ollama` Python package.
- **Cost**: judged metrics are slow on CPU (~49 s each), so bulk evals use deterministic checks and the scripted model; judged metrics run on a small subset.
- **SQLite join**: one `run_id` joins runs, spans (0 orphans) and eval results; stored `trace_id` resolves in Jaeger.

## Day 1 findings
- **Windows clock**: `time.time_ns()` ticks ~1 ms here, so microsecond spans collide (identical timestamps, 0 ms durations, ambiguous order). `telemetry/tracing.py` anchors wall time once and advances it with `perf_counter_ns()`, with explicit span start/end times.
- **Observer effect**: exporting to SQLite synchronously inflated the parent span (6.2 ms vs ~0.6 ms of child work). SQLite export now runs on a batch (background) thread.
- **Jaeger must not gate a run**: the app marks a run finished after the SQLite copy is flushed (`flush_store`); OTLP export is best-effort. Test covers Jaeger-down. `agent.run` duration is measured before any export.
- **DeepEval pytest plugin sends analytics unless opted out** (PostHog). Disabled with `-p no:deepeval` in pytest config, and `DEEPEVAL_TELEMETRY_OPT_OUT=YES` is hard-set in `blackbox/__init__.py` before deepeval can be imported; `test_privacy.py` guards both. One pytest session ran before this fix (its plugin skips the event when no DeepEval work happened, which was the case, so likely nothing was sent — not proven).
- **Redaction limits**: key-based (known field names in JSON, including JSON nested inside JSON strings) plus patterns (emails, card-like numbers, local user-home paths). Free-text PII such as an address in prose is not caught. Local home paths are scrubbed because stack traces would otherwise leak the Windows username into spans.
- **Ops lesson**: never stop processes by port number; record the PID you started. A port-based kill matched 3 PIDs, and Docker Desktop restarted shortly afterwards (causal link unproven). The Jaeger container does not survive a Docker restart (no restart policy yet).

## Environment
Venv `.venv` (Python 3.12.14 via uv). Installed: opentelemetry-sdk/exporter-otlp 1.45.1, deepeval 4.2.8, fastapi 0.143.0, pytest 9.1.1, ollama 0.6.3. Ollama models present: qwen2.5:7b, llama3.1:8b, llama3.2:3b, qwen2.5:14b (too heavy with Docker on 16 GB). Jaeger container name `jaeger`, ports 16686/4317/4318.
