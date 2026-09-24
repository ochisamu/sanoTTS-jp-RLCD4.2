"""Architecture sizing only, not a trained recognizer."""
import json
from pathlib import Path


def estimate(groups, output_symbols=129):
    encoder = sum(v for k, v in groups.items() if k.startswith("model.encoder."))
    head = (288 + 1) * output_symbols
    return {"symbols_including_blank": output_symbols,
            "parameters": encoder + head, "ideal_int8_weights_MiB": (encoder + head) / 2**20,
            "warning": "Estimate only. New CTC head requires training; no MCU runtime/accuracy evidence."}


if __name__ == "__main__":
    report = json.loads((Path(__file__).parent / "results/feasibility.json").read_text())
    for v in report["variants"]:
        if v["variant"] != "fake_int8_fp32_compute":
            print(json.dumps({"source": v["variant"], **estimate(v["parameter_groups"])}))
