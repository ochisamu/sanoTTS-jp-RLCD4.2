"""Local feasibility test; no firmware generation or device writes."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("HF_HOME", str(ROOT / ".cache/hf"))
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
MODEL = "moonshine-ai/moonshine-tiny-ja"
REV = "02ca41b3d9e73db07df9a13f316f2b7497a368e2"
DATASET = "UsefulSensors/multilingual_examples"
DATA_REV = "badcb6e16db6bc982b48e2befb30c771f2ebb511"


def fetch():
    from huggingface_hub import hf_hub_download
    paths = []
    for name in ("config.json", "generation_config.json", "preprocessor_config.json",
                 "tokenizer.json", "model.safetensors", "LICENSE.txt", "README.md"):
        print("Fetching", name, flush=True)
        paths.append(Path(hf_hub_download(MODEL, name, revision=REV, token=False,
                                         local_dir=ROOT / ".cache/model")))
    for name in ("README.md", "data/ja-00000-of-00001.parquet"):
        paths.append(Path(hf_hub_download(DATASET, name, revision=DATA_REV, repo_type="dataset",
                                         token=False, local_dir=ROOT / ".cache/dataset")))
    return [{"file": str(p.relative_to(ROOT)), "bytes": p.stat().st_size,
             "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]


def edit_distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        next_row = [i]
        for j, y in enumerate(b, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1, row[j-1] + (x != y)))
        row = next_row
    return row[-1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    manifest_path = ROOT / ".cache/manifest.json"
    if args.download:
        manifest = fetch()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    else:
        manifest = json.loads(manifest_path.read_text())
    for item in manifest:
        if hashlib.sha256((ROOT / item["file"]).read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError("Downloaded file changed: " + item["file"])
    import pyarrow.parquet as pq
    import soundfile as sf
    import torch
    import transformers
    from transformers import AutoProcessor, MoonshineForConditionalGeneration
    torch.manual_seed(42)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA required for this training feasibility test")
    row = pq.read_table(ROOT / ".cache/dataset/data/ja-00000-of-00001.parquet").to_pylist()[0]
    audio, sr = sf.read(io.BytesIO(row["audio"]["bytes"]), dtype="float32")
    if audio.ndim != 1 or sr != 16000:
        raise ValueError("Expected mono 16kHz audio")
    reference = row["text"]
    processor = AutoProcessor.from_pretrained(ROOT / ".cache/model", local_files_only=True)
    model = MoonshineForConditionalGeneration.from_pretrained(
        ROOT / ".cache/model", local_files_only=True).to("cuda")
    inputs = processor(audio, sampling_rate=sr, return_tensors="pt").to("cuda")
    duration = len(audio) / sr
    report = {"model": MODEL, "revision": REV, "dataset": DATASET, "dataset_revision": DATA_REV,
              "sample_count": 1, "audio_seconds": duration, "seed": 42,
              "gpu": torch.cuda.get_device_name(), "torch": torch.__version__,
              "transformers": transformers.__version__, "manifest": manifest,
              "warning": "One clip smoke test, not an accuracy evaluation. GPU timings are not ESP32 timings.",
              "variants": []}

    def run(name, candidate):
        candidate.eval()
        count = sum(p.numel() for p in candidate.parameters())
        groups = {}
        for key, param in candidate.named_parameters():
            group = ".".join(key.split(".")[:3])
            groups[group] = groups.get(group, 0) + param.numel()
        def generate():
            with torch.inference_mode():
                return candidate.generate(**inputs, max_new_tokens=256, do_sample=False)
        generate()  # Warm up separately.
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        start = time.perf_counter()
        ids = generate()
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - start
        text = processor.batch_decode(ids, skip_special_tokens=True)[0]
        result = {"variant": name, "unique_parameters": count, "parameter_groups": groups,
                  "int8_weights_only_MiB_lower_bound": count / 2**20,
                  "int4_weights_only_MiB_lower_bound": count / 2 / 2**20,
                  "gpu_generation_seconds": elapsed, "gpu_rtf": elapsed / duration,
                  "gpu_peak_allocated_MiB": torch.cuda.max_memory_allocated() / 2**20,
                  "raw_character_error_rate": edit_distance(reference, text) / max(1, len(reference)),
                  "output_characters": len(text), "hit_generation_limit": ids.shape[-1] >= 257}
        report["variants"].append(result)
        # Text stays in local ignored cache: dataset license is not specified in its card.
        (ROOT / ".cache" / (name + "-text.json")).write_text(
            json.dumps({"reference": reference, "prediction": text}, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False), flush=True)

    run("baseline_fp32", model)
    # Round+dequantize: a numerical sensitivity test, NOT a packed int8 runtime.
    with torch.no_grad():
        for p in model.parameters():
            if p.ndim >= 2:
                scale = p.abs().amax(dim=tuple(range(1, p.ndim)), keepdim=True).clamp_min(1e-8) / 127
                p.copy_((p / scale).round().clamp(-127, 127) * scale)
    run("fake_int8_fp32_compute", model)
    del model
    torch.cuda.empty_cache()
    model = MoonshineForConditionalGeneration.from_pretrained(
        ROOT / ".cache/model", local_files_only=True).to("cuda")
    # Keep alternate pretrained blocks. No recovery training before evaluation.
    for kind in ("encoder", "decoder"):
        module = getattr(model.model, kind)
        module.layers = torch.nn.ModuleList([module.layers[i] for i in (0, 2, 4)])
        for index, layer in enumerate(module.layers):
            for child in layer.modules():
                if hasattr(child, "layer_idx"):
                    child.layer_idx = index
        setattr(model.config, kind + "_num_hidden_layers", 3)
    run("alternate_half_layers_untrained", model)
    # Three teacher-forcing steps test trainability and memory only, NOT quality.
    model.train()
    model.config.use_cache = False
    labels = processor.tokenizer(reference, return_tensors="pt").input_ids.to("cuda")
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-5)
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()
    start = time.perf_counter()
    losses = []
    for _ in range(3):
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            output = model(**inputs, labels=labels, use_cache=False)
            loss = output.loss
        if not torch.isfinite(loss):
            raise RuntimeError("Non-finite training loss")
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach()))
    torch.cuda.synchronize()
    report["training_smoke_test"] = {"variant": "alternate_half_layers", "steps": 3,
        "batch_size": 1, "precision": "bf16 autocast; fp32 parameters/AdamW",
        "seconds": time.perf_counter() - start, "losses": losses,
        "peak_allocated_MiB": torch.cuda.max_memory_allocated() / 2**20,
        "warning": "Same clip used for evaluation/training; no generalization claim; no weights saved."}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results/feasibility.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["training_smoke_test"]), flush=True)


if __name__ == "__main__":
    main()
