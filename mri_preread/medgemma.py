"""Local Apple Silicon MedGemma inference and a bounded, read-only MCP review.

Only `download` uses the network. Review writes a separate research draft; it
does not interpret model text as tool calls or change existing annotations.
"""
import argparse
import asyncio
import base64
import io
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import sys
import time

MODEL_ID = "mlx-community/medgemma-1.5-4b-it-4bit"
DEFAULT_MODEL = "models/medgemma-1.5-4b-it-4bit"
LIMITATIONS = (
    "Experimental model output, not a diagnosis or a complete scan interpretation. "
    "Sampled montages can miss small findings; sequences are reviewed independently. "
    "Quantization and this workflow have not been clinically validated. "
    "A qualified radiologist must review the original scan."
)
PROMPT = (
    "You are assisting an early, non-diagnostic brain MRI review. Describe only "
    "visible signal patterns and locations that merit a radiologist's attention. "
    "Do not give a diagnosis or declare the scan normal, healthy or clear. "
    "Distinguish observations from uncertainty and possible artifacts. Do not "
    "invent measurements, coordinates, or findings on sequences not shown. "
    "If labels or detail cannot be read, say so. Existing colored markers are "
    "annotations, not imaging findings. Reply briefly in plain text.\n"
)


def positive_int(value):
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return n


def configure_parser(sub):
    p = sub.add_parser("medgemma", help="local MedGemma on Apple Silicon")
    actions = p.add_subparsers(dest="action", required=True)
    for name in ("download", "smoke-test", "review"):
        q = actions.add_parser(name)
        q.add_argument("--model-dir", default=DEFAULT_MODEL)
        if name != "download":
            q.add_argument("--max-tokens", type=positive_int, default=256)
        if name == "review":
            q.add_argument("study", nargs="?")
            q.add_argument("--max-candidates", type=int, default=3,
                           help="number of algorithmic hotspots to inspect; 0 = overview only")
            q.add_argument("--sequences", nargs="+", choices=["t1", "t2", "flair", "swi", "dwi", "adc"])
            q.add_argument("--output", help="new JSON file; default: timestamped file in study/analysis")
            q.add_argument("--workflow", choices=["slices", "montage"], default="slices")
            q.add_argument("--step-mm", type=float, default=10.0, help="axial slice spacing for slices workflow")
            q.add_argument("--max-slices", type=positive_int, help="development only: stop after this many slices")


def offline_environment():
    # Set before importing either transformers or huggingface_hub.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def download(model_dir):
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from huggingface_hub import HfApi, snapshot_download
    revision = HfApi().model_info(MODEL_ID).sha
    path = snapshot_download(
        MODEL_ID, revision=revision, local_dir=model_dir,
        allow_patterns=["*.json", "*.safetensors", "*.model", "*.jinja", "*.txt", "README.md", "LICENSE*"],
    )
    Path(path, "download-provenance.json").write_text(json.dumps({
        "repository": MODEL_ID, "revision": revision,
        "upstream": "google/medgemma-1.5-4b-it",
        "terms": "https://developers.google.com/health-ai-developer-foundations/terms",
    }, indent=2))
    print(f"Model downloaded to {path}")


class LocalModel:
    def __init__(self, model_dir):
        offline_environment()
        path = Path(model_dir).expanduser().resolve()
        if not (path / "config.json").is_file() or not list(path.glob("*.safetensors")):
            raise SystemExit("Local weights missing. Run `mri-preread medgemma download` first.")
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            raise SystemExit("This MLX runner requires an Apple Silicon Mac.")
        try:
            import mlx.core as mx
        except ImportError as exc:
            if "Metal" in str(exc) or "metal" in str(exc):
                raise SystemExit("Metal GPU access is unavailable. Run this command in a local Terminal outside the sandbox.") from exc
            raise
        from mlx_vlm import load
        if not mx.metal.is_available():
            raise SystemExit("Apple Metal GPU is not available in this process.")
        self.config = json.loads((path / "config.json").read_text())
        self.path = str(path)
        provenance = path / "download-provenance.json"
        self.provenance = json.loads(provenance.read_text()) if provenance.exists() else {"local_path": str(path)}
        print(f"Loading local weights: {path}", file=sys.stderr, flush=True)
        self.model, self.processor = load(str(path), trust_remote_code=False)

    def infer(self, prompt, image, max_tokens):
        return self.infer_images(prompt, [image], max_tokens)

    def infer_images(self, prompt, images, max_tokens, decision_mode=False):
        import mlx.core as mx
        from mlx_vlm import generate
        content = [{"type": "image"} for _ in images] + [{"type": "text", "text": prompt}]
        formatted = self.processor.apply_chat_template(
            [{"role": "user", "content": content}], tokenize=False, add_generation_prompt=True)
        extra = {}
        if decision_mode:
            formatted += "Review decision: "
            tokenizer = self.processor.tokenizer
            choices = [tokenizer.encode(s, add_special_tokens=False) for s in ("yes", "no", "uncertain", "\n")]
            if any(len(ids) != 1 for ids in choices):
                raise ValueError("Decision decoder requires single-token yes/no/uncertain/newline labels")
            calls = 0

            def constrain_label(tokens, logits):
                nonlocal calls
                calls += 1
                if calls > 2:
                    return logits
                allowed = [ids[0] for ids in (choices[:3] if calls == 1 else choices[3:])]
                mask = mx.full(logits.shape, -float("inf"))
                mask[..., allowed] = 0
                return logits + mask

            extra["logits_processors"] = [constrain_label]
        started = time.monotonic()
        result = generate(self.model, self.processor, formatted, image=images,
                          max_tokens=max_tokens, temperature=0.0,
                          repetition_penalty=1.1, verbose=False, **extra)
        record = {
            "text": result.text, "seconds": round(time.monotonic() - started, 2),
            "prompt_tokens": result.prompt_tokens, "generated_tokens": result.generation_tokens,
            "generation_tokens_per_second": round(result.generation_tps, 2),
            "peak_mlx_memory_gb": round(result.peak_memory, 3),
            "hit_token_limit": result.generation_tokens >= max_tokens,
        }
        mx.clear_cache()
        return record


def smoke_test(model, max_tokens):
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (448, 448), "white")
    ImageDraw.Draw(image).rectangle((100, 100, 348, 348), fill="red")
    result = model.infer("Describe the color and shape in this synthetic image in one sentence.", image, max_tokens)
    print(json.dumps({"test": "synthetic image; no medical data", **result}, indent=2))


def unpack_result(result):
    from PIL import Image
    if result.isError:
        raise RuntimeError("MCP tool failed: " + " ".join(c.text for c in result.content if c.type == "text"))
    text = "\n".join(c.text for c in result.content if c.type == "text")
    images = [Image.open(io.BytesIO(base64.b64decode(c.data))).convert("RGB")
              for c in result.content if c.type == "image"]
    return text, images


async def review(model, study, args, output):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    # Port 0 lets the OS choose a free loopback port. No existing viewer is touched.
    params = StdioServerParameters(command=sys.executable,
        args=["-m", "mri_preread", "serve", study.root],
        env={**os.environ, "BRAIN_VIEWER_PORT": "0"})
    report = {
        "model_provenance": model.provenance, "model_dir": model.path,
        "backend": "mlx-vlm", "backend_version": version("mlx-vlm"),
        "limitations": LIMITATIONS, "status": "in_progress", "reviews": [],
        "max_tokens_per_image": args.max_tokens,
        "decoding": {"temperature": 0.0, "repetition_penalty": 1.1},
    }

    def save():
        # An interrupted run retains completed observations with in_progress status.
        tmp = output.with_suffix(output.suffix + ".tmp")
        tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        tmp.replace(output)

    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()

            async def call(name, arguments=None):
                return unpack_result(await session.call_tool(name, arguments or {}))

            overview_text, _ = await call("get_study_overview")
            overview = json.loads(overview_text)
            available = list(overview["sequences"])
            sequences = args.sequences or available
            if any(s not in available for s in sequences):
                raise ValueError(f"Requested sequence unavailable; available: {available}")
            candidate_text, _ = await call("list_candidate_regions", {"include_likely_artifacts": False})
            candidates = json.loads(candidate_text)[:args.max_candidates]
            report.update({"sequences": sequences, "grid": overview["grid"],
                           "candidates_available": len(json.loads(candidate_text)),
                           "candidates_selected": len(candidates)})
            save()

            async def inspect(name, arguments, context):
                text, images = await call(name, arguments)
                if not images:
                    raise RuntimeError(f"{name} returned no image: {text}")
                for image in images:
                    print(f"Reviewing {name}: {arguments}", file=sys.stderr, flush=True)
                    result = model.infer(PROMPT + context + "\nImage metadata: " + text,
                                         image, args.max_tokens)
                    report["reviews"].append({"tool": name, "arguments": arguments,
                                              "image_metadata": text, **result})
                    save()

            for sequence in sequences:
                await inspect("view_overview", {"sequence": sequence, "plane": "axial", "slices": 12},
                              f"This is a sampled {sequence.upper()} overview, not the complete volume.")
            for candidate in candidates:
                x, y, z = candidate["pos"]
                for sequence in sequences:
                    await inspect("view_region", {"x": x, "y": y, "z": z, "sequences": [sequence]},
                                  f"Inspect the center of these three {sequence.upper()} views. "
                                  "The location was selected by an unverified statistical algorithm.")
            report["status"] = "complete"
            save()
    print(f"Draft saved to {output}")


def main(args):
    if args.action == "download":
        download(args.model_dir)
        return
    if args.action == "review":
        from .study import resolve
        if args.max_candidates < 0:
            raise SystemExit("--max-candidates must be >= 0")
        if not 1 <= getattr(args, "step_mm", 10) <= 30:
            raise SystemExit("--step-mm must be between 1 and 30")
        study = resolve(args.study)
        if not Path(study.analysis, "viewer_data.npz").is_file():
            raise SystemExit("Study has no viewer data; run `mri-preread analyze` first.")
        output = (Path(args.output).expanduser() if args.output else
                  Path(study.analysis, f"medgemma-review-{time.time_ns()}.json"))
        # Fail before model loading if a report already exists or its folder is absent.
        if output.exists():
            raise SystemExit(f"Output already exists: {output}; choose a new --output.")
        if not output.parent.is_dir():
            raise SystemExit(f"Output directory does not exist: {output.parent}")
    try:
        model = LocalModel(args.model_dir)
    except ImportError as exc:
        raise SystemExit('Install the optional runtime: pip install -e ".[medgemma]"') from exc
    if args.action == "smoke-test":
        smoke_test(model, args.max_tokens)
    else:
        if getattr(args, "workflow", "slices") == "slices":
            from .medgemma_trace import review_slices
            asyncio.run(review_slices(model, study, args, output))
            from .build_viewer import run as build_viewer
            build_viewer(study, medgemma_report=output)
        else:
            asyncio.run(review(model, study, args, output))
