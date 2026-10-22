# Third-party software

Agent Blackbox is MIT licensed (see [LICENSE](LICENSE)). It contains no third-party source code, fonts, images or datasets: the code, the test cases, the screenshots and the recorded demo data are original to this project. It depends on the open-source packages below, which are installed from their own registries, not copied into this repository. Their licences apply to them.

## What running the app installs (Python)

All of these were checked from the installed packages' own metadata on 2026-10-22, for the runtime dependency set declared in `pyproject.toml` and everything it pulls in.

| Licence | Packages |
|---|---|
| MIT | fastapi, ollama, pydantic, pydantic-core, anyio, annotated-doc, annotated-types, charset-normalizer, h11, typing-inspection, urllib3 |
| BSD (2- or 3-clause) | httpx, httpcore, uvicorn, starlette, click, idna, colorama, protobuf |
| Apache-2.0 | opentelemetry-api, -sdk, -proto, -semantic-conventions and the OTLP exporters, googleapis-common-protos, grpcio, requests |
| PSF-2.0 | typing-extensions |
| MPL-2.0 | certifi (used unmodified, as a dependency) |

`pytest` and `pillow` (the `dev` extra) and `deepeval` (the `judge` extra) are not installed unless asked for, and nothing at run time imports them.

## What the dashboard ships (JavaScript)

The built site contains React, React DOM and Scheduler, all MIT licensed, copyright Meta Platforms, Inc. and affiliates. The build tools and test libraries (Vite, Vitest, TypeScript, Testing Library and their dependencies, under MIT, Apache-2.0, BSD, ISC and MPL-2.0 licences) are used only on the developer's machine and are not part of the built site. The full list is in `frontend/package-lock.json`.

## Separate programs the project talks to (not bundled)

- **Jaeger** (`jaegertracing/jaeger`, Apache-2.0) runs as its own container and receives traces over the network.
- **Ollama** and the **Qwen2.5 7B** model run on the user's machine. The model's own licence is set by its authors (Qwen2.5 7B is published under Apache-2.0, as I understand it; check the model card on your machine). The recorded demo contains text the model produced on this project's test cases.

## Fonts and icons

The dashboard uses the system font stack and one inline SVG logo drawn for this project. No web font is downloaded.
