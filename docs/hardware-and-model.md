# Model runtimes and hardware

## MCP is independent of the inference device

The browser viewer, preparation tools and MCP stdio server are separate from model inference.
A compatible MCP client or agent can use an NVIDIA-hosted vision model, a supported llama.cpp
multimodal model on a local computer, or another approved provider. The client must route tool calls
and image results; a plain inference endpoint does not provide MCP routing. A text-only model cannot
inspect the image pixels.

The [llama.cpp multimodal documentation](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md)
describes supported models and their matching vision projectors (`--mmproj`). CPU/GPU support, memory,
image encoding and model-format compatibility must all be checked. These external MCP model-host paths
are distinct from the bundled fixed MedGemma review command and automatic worklist backend.

Raspberry Pi 5 can host compatible runtimes subject to RAM and latency. The original AI HAT+ is a
vision accelerator; [AI HAT+ 2](https://www.raspberrypi.com/documentation/accessories/ai-hat-plus.html)
has generative support for selected compiled models. **MedGemma 4B on that HAT is unverified here**;
check the [Hailo generative-model list](https://github.com/hailo-ai/hailo_model_zoo_genai/blob/main/docs/MODELS.rst),
including vision support. Parameter count alone does not establish compatibility or useful throughput.


## Tested configuration

Local inference was exercised on a **MacBook Air M5 with 16 GB unified memory**, using its integrated
Metal GPU. No separate NVIDIA device was needed for that demonstration. The tested software environment
was Python 3.14, MLX 0.32.2 and MLX-VLM 0.4.4. The package pins MLX-VLM 0.4.4; other transitive packages
are not frozen, so record your resolved environment and verify a new installation with the smoke test.

Default weights: `mlx-community/medgemma-1.5-4b-it-4bit`, roughly 3.4 GB. This is a community quantization
of Google's MedGemma 1.5 4B instruction-tuned multimodal model, not an official Google MLX conversion.
The download resolves and records the actual upstream repository revision. Preserve
`download-provenance.json` with your environment record. Application code is MIT; model weights retain
[Health AI Developer Foundations terms](https://developers.google.com/health-ai-developer-foundations/terms).
Review those terms before downloading or deploying; no weights are redistributed in the source release.

Development checks with three sequence images measured roughly 4–5 seconds per sampled plane and
4.7 GB peak MLX allocation. These are local observations, not end-to-end clinical SLAs or total process
memory. Image size, sequence count, output length, preprocessing, available memory and concurrent workloads
change latency. Reserve additional disk space for original DICOM, reference/registered NIfTIs, reports and
exact input PNGs. There is no established minimum-memory specification or validated throughput target.

## What the model actually sees

The default review samples the brain-mask extent at 10 mm axial spacing. Each selected sequence is a
separate 896×896 image at the same aligned plane, with fixed volume windows and preserved physical aspect.
The runner invokes read-only MCP image tools and sends the images together. This is not full 3D inference,
continuous slice coverage or a model that reads a DICOM folder directly. The browser displays saved results.

Google's [model card](https://huggingface.co/google/medgemma-1.5-4b-it) describes MedGemma 1.5 as an
open medical image/text model with added volumetric imaging capabilities. That upstream capability does
not validate this sampling workflow, quantization or prompt. The initial six-case project pilot flagged
all 91 planes, including all 29 control planes. It failed to distinguish normal from lesion-bearing planes.
MedGemma therefore remains an inspectable research component; no automatic urgency is assigned.

## Supported execution paths

| Task | Current implementation |
|---|---|
| Open a prepared viewer | Modern browser on macOS/Windows/Linux; verify WebGL2 and decompression in managed environments |
| Prepare images / build HTML | Python scientific stack; exercised on macOS; included synthetic CI targets Linux |
| MCP with another model | Compatible client/agent plus a chosen vision endpoint; hardware belongs to its runtime |
| Included local MedGemma inference | macOS + Apple Silicon + Metal + MLX-VLM |
| Integrated worklist | Local Apple Silicon pipeline, serial jobs and `fcntl` workspace lock |
| External CUDA / CPU model host through MCP | Possible via a compatible client and supported vision runtime; model-specific evaluation required |
| Bundled MedGemma review / worklist on CUDA or CPU | No adapter implemented in this repository |

For the automatic review worker on a hospital GPU server, a new inference adapter must implement the image/prompt interface,
retain provenance and input traces, and undergo a new independent evaluation. Do not document it as
working merely because the upstream model supports a different runtime. Likewise, fitting on a laptop
says nothing about reliability or sustained multi-user load.

## Reproducibility record

After installation and model download, record these locally with your pilot artifacts:

```bash
.venv/bin/python -m pip freeze > data/pilot-environment.txt
.venv/bin/mri-preread medgemma smoke-test --model-dir models/medgemma-1.5-4b-it-4bit
git rev-parse HEAD
```

Keep model revision, source commit, hardware, available sequences, preparation settings, sampling step,
input hashes, prompt/decoding parameters, token limits, runtime failures and human corrections together.
A runtime smoke test and deterministic output formatting do not establish medical correctness.

Sources checked 2026-10-02: [Google MedGemma](https://developers.google.com/health-ai-developer-foundations/medgemma),
[community weights](https://huggingface.co/mlx-community/medgemma-1.5-4b-it-4bit),
[MLX-VLM](https://github.com/Blaizzy/mlx-vlm), [MLX](https://ml-explore.github.io/mlx/build/html/index.html).
