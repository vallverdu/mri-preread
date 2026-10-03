# Contributing

mri-preread combines a browser viewer, local brain MRI preparation, MCP tools and an experimental
medical-model runner. Improvements to interoperability, image geometry, accessibility and reproducible
evaluation are welcome.

## Start locally

Follow [README.md](README.md) for installation. The optional MLX inference dependency is not needed
for development of the viewer, preprocessing, MCP tests or synthetic demonstration.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests
node --test tests/test_*.cjs
.venv/bin/python examples/build_synthetic_demo.py
python3 -m http.server 8080 --bind 127.0.0.1 --directory site
```

Open `http://127.0.0.1:8080/`. The website demo uses the approved CC0 OpenNeuro study and has no model
predictions. The synthetic builder writes a separate ignored regression fixture. Public examples must
use synthetic data or the reviewed dataset derivatives documented in [open-demo.md](docs/open-demo.md).
Website photography requires the separate source/license review in [website-photos.md](docs/website-photos.md).
Never substitute a private scan or assume an openly downloadable dataset permits redistribution. See
[the knowledge base](docs/KNOWLEDGE.md) for the architecture and coordinate conventions.

## Make a change

Keep clinician notes, algorithmic candidates and AI outputs distinguishable. Do not let model output
set clinical urgency. Changes to preprocessing, windows, prompts, model revisions or quantization need
new evaluation outputs; preserve earlier frozen predictions and reports. Use a small synthetic regression
case for a geometry bug. Check the standalone viewer after changing embedded HTML or JavaScript.

Before a pull request, run the tests and `python3 scripts/release_audit.py`. Explain the user-visible
behavior, verification and remaining limits. Never include private patient data, raw scans, private scan descriptions,
model weights, absolute personal paths, credentials or local `.mcp.json` files. Dependencies retain their
own licenses; the application code is MIT, and MedGemma weights have separate HAI-DEF terms.
