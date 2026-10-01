"""List the model servers on this machine and whether they're set up well for Little Chits.

    make gpus        (or: .venv/bin/python scripts/gpus.py)
"""
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from chits.brain.llm import scan_local  # noqa: E402


def main() -> None:
    if shutil.which("nvidia-smi"):
        print("GPUs:")
        out = subprocess.run(["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
                              "--format=csv,noheader"], capture_output=True, text=True).stdout
        for line in out.strip().splitlines():
            print("  " + line)
    else:
        print("(nvidia-smi not found, so GPU memory can't be shown)")
    print("\nScanning for model servers…")
    found = asyncio.run(scan_local())
    if not found:
        print("  none found. Start one with scripts/gpu-server.sh (see docs/GPU_SETUP.md)")
        return
    for f in found:
        slots = f.get("slots")
        tip = ""
        if slots in (None, 0):
            tip = "  (slots unknown: fine for Ollama/vLLM; for llama-server this may be an old build)"
        elif slots < 4:
            tip = f"  ← only {slots} slot(s): chits queue up. Restart with --slots 8 (docs/GPU_SETUP.md)"
        print(f"  {f['base_url']}  model={f['models'][0]}  slots={slots}{tip}")


if __name__ == "__main__":
    main()
