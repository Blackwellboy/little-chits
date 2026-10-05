# Small local models for Little Chits (October 2026)

A desk survey that comes before anything is downloaded or run. Repo ids were checked against the Hugging Face API (author listings and file trees) and the model cards. File sizes are from those file trees.

**VRAM figures are estimates** (model file, plus the KV cache at 16k, plus about 1 GB of buffers). Nothing here was measured. A model's place in this list says nothing about how it plays: on the decision bench, agreement did not predict in-game results. Only matched runs decide (stage B and C below).

## What the baseline models are

- **JevK5 9B** (`alibiserikbay/JevK5-9B`, GGUF `alibiserikbay/JevK5-GGUF`, file `jevk5-9b-v0.3.3-Q8_0.gguf`, 9.53 GB, Apache-2.0) is Qwen3.5-9B with a merged rank-16 LoRA.
  - It is a **decision model**. It reads a state and a choice question and answers by a next-token letter readout. Free-form JSON planning is not documented.
  - It was trained on inputs of **at most 2,048 tokens**, refuses more than 16,384, and its card launches with `-c 8192`.
  - Little Chits' full plan prompt is 3-5k tokens of JSON-plan instructions. So a full-prompt run of JevK5 (as in the JevK5-vs-Gemma study) tests it outside what it was built for. Its natural role is the one-letter choice layer (choose/cascade, and the typed-decision layer of a two-level mind).
  - There are smaller siblings: a 4B (`jevk5-4b-v0.3-Q8_0.gguf`, 4.48 GB) and a 2B (2.01 GB).
- **Gemma 4 12B** (`google/gemma-4-12B-it`, Apache-2.0, 256K-token context) runs here as Q4_K_M (7.12 GB). A Q8_0 file (12.67 GB) exists, so part of any Gemma result may be the quant, not the model.

## Candidates

| Model | GGUF repo | Params | Licence | Files | VRAM @16k (est.) | Notes |
|---|---|---|---|---|---|---|
| Qwen3.5-9B | `unsloth/Qwen3.5-9B-GGUF` | 9B (DeltaNet hybrid) | Apache-2.0 | Q8_0 9.53 GB, Q6_K 7.46 GB | ~11 GB | JevK5-9B's own base: the cleanest A/B against JevK5. Thinking is on by default, so set `enable_thinking:false` |
| Granite 4.2 8B | `ibm-granite/granite-4.2-8b-GGUF` (official) | 8B dense | Apache-2.0 | Q8_0 9.35 GB, Q6_K 7.22 GB | ~12-13 GB | Documented structured output. Thinking on by default, so set `enable_thinking:false` |
| Gemma 4 12B Q8_0 | `unsloth/gemma-4-12b-it-GGUF`, `ggml-org/gemma-4-12B-it-GGUF` | 12B dense | Apache-2.0 | Q8_0 12.67 GB, Q6_K 9.79 GB | ~13-15 GB | Separates the quant from the model |
| Ministral 3 14B Instruct 2512 | `mistralai/Ministral-3-14B-Instruct-2512-GGUF` (official) | 13.5B | Apache-2.0 | Q5_K_M 9.62 GB, Q8_0 14.36 GB | ~13-18 GB | Native JSON output. Mistral advises temperature below 0.1 |
| Gemma 4 26B-A4B | `unsloth/gemma-4-26B-A4B-it-GGUF` | 25.2B total, 3.8B active | Apache-2.0 | UD-Q4_K_M 16.95 GB, UD-Q5_K_M 21.15 GB | ~19-24 GB | MoE: about a 4B's speed. RTX 5090 |
| Qwen3.6-35B-A3B | `unsloth/Qwen3.6-35B-A3B-GGUF`, `ggml-org/...` | 35B total, 3B active | Apache-2.0 | UD-Q4_K_M 22.13 GB | ~23-28 GB | MoE. RTX 5090 |
| Qwen3.8-27B | `unsloth/Qwen3.8-27B-GGUF`, `ggml-org/...` | 27B dense hybrid | Apache-2.0 | UD-Q4_K_M 16.46 GB, UD-Q5_K_M 19.77 GB | ~18-24 GB | Strongest dense model that fits. Needs llama.cpp ≥ about b10450 on CUDA, or it outputs garbage |
| Gemma 4 31B | `unsloth/gemma-4-31B-it-GGUF` | 30.7B dense | Apache-2.0 | not checked | ~21-23 GB at Q4 (unverified) | Slow dense decode. Last stage only |
| Nemotron 3.5 Lightning 30B-A3B | `ggml-org/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF` | 30B total, 3B active (Mamba-2 hybrid) | OpenMDW-1.1 | Q4_0 18.90 GB | ~20-21 GB | Optional |

**Families that don't exist or don't fit:**
- Gemma 4 has no 1B, 4B or 27B. Its sizes are E2B, E4B, 12B, 26B-A4B and 31B.
- Qwen3.8 has no small sizes.
- Qwen3.5-27B and 35B-A3B are superseded by the 3.6 versions.
- GLM-5.3-Flash, Qwen3.8-Flash-Next and Mistral Small 4 are too big for one RTX 5090.
- Qwen3.5-2B and 4B are fast-fallback candidates only.

**Serving notes:**
- Upgrade llama.cpp before screening: gemma4 needs ≥ b8637, and the Qwen DeltaNet CUDA fix needs ≥ about b10450.
- Qwen 3.5/3.6/3.8 and Nemotron are hybrids. Their KV cache is small, but prompt-prefix reuse in llama-server depends on `--ctx-checkpoints`, so measure throughput as well as quality.
- `top_logprobs` is a generic llama-server feature. Check it on each model with a one-token letter probe.

## Screening funnel

1. **Stage A, cheap screening** (`tools/decbench.py`, prompt checks):
   - valid replies, impossible actions, latency, tokens
   - for letter models: whether urgent needs are recognised
   - whether a failure note is used, once the Lab can run repair as an arm
   - Reject what is plainly unusable. Order: Qwen3.5-9B, Granite 4.2 8B, Gemma 4 12B Q8_0, Ministral 3 14B; then the MoEs (Gemma 4 26B-A4B, Qwen3.6-35B-A3B); then Qwen3.8-27B and Gemma 4 31B.
2. **Stage B, the model in the loop** (`tools/harness/run.py --mind URL`, several seeds):
   - each model in its normal mode, and model-led play
   - The harness sends its own sampling (temperature 0.7, no extra body): it has no per-model sampling options yet. A model whose card asks for something else (Ministral below 0.1; Granite at 1.0, top_p 0.95; Qwen's non-thinking settings) is judged at stage B only after the harness takes those settings, or goes straight to stage C, where each brain's sampling is sealed in the protocol (declare `"sampling": "native"`). A stage B result at the wrong sampling is not a verdict on the model.
   - starvation and stuck loops
   - invented or missing items and malformed actions
   - who drove the world: the provenance categories, added in the provenance PR as docs/PROVENANCE.md
   - Model-only runs (`--model-only`) are a diagnostic of what a model does with no body reflexes and no menu. They are never a screening arm: they force the full prompt, which also takes a letter model such as JevK5 out of its interface.
3. **Stage C, the Lab:** pre-registered, same rules and culture, matched seeds, lockstep, request seeds, matched sampling, blinded, BrainTape, invalid-run handling, and a seed count justified by the measured variance.

Every model is reported on civilisation quality **and** on thinking cost (requests, tokens and seconds per chit-day, VRAM, wall time). No single score hides the parts.

## Sources

- Hugging Face API author listings and `tree/main` file listings for each repo above.
- Model cards:
  - https://huggingface.co/google/gemma-4-12B-it
  - https://huggingface.co/Qwen/Qwen3.5-9B
  - https://huggingface.co/Qwen/Qwen3.6-35B-A3B
  - https://huggingface.co/Qwen/Qwen3.8-27B
  - https://huggingface.co/alibiserikbay/JevK5-GGUF
  - https://huggingface.co/alibiserikbay/JevK5-9B
  - https://huggingface.co/ibm-granite/granite-4.2-8b
  - https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512
  - https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16
- llama.cpp:
  - https://github.com/ggml-org/llama.cpp/pull/21309 (gemma4)
  - https://github.com/ggml-org/llama.cpp/discussions/27164 (the DeltaNet CUDA fix)
  - Issues #24587 and #24714 (hybrid prefix reuse)

**Not verified:** every VRAM figure, the Gemma 4 31B file sizes, the exact minimum llama.cpp builds for Granite 4.2 and Nemotron 3.5, and each model's `top_logprobs` behaviour.
