# CLAUDE.md — Project Rules & Conventions

## Commands

```bash
# Create isolated environment (PyTorch lacks stable Python 3.14 wheels; use 3.12)
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest

# Check typing
mypy src/

# Lint (PEP-8)
flake8 src/ tests/

# Run the system (end-to-end smoke run). Both forms work:
python src/main.py --input data/sample_bgl.log
python -m src.main --input data/sample_bgl.log
```

## Style & Patterns

- Use **strict type hints** on all functions (mypy strict).
- Follow **PEP-8** code styling (enforced by flake8, max line length 100).
- Always use **parameterized queries** for SQLite (never string interpolation).
- Handle `CausalConv1d` padding **programmatically without `F.pad`** to avoid memory
  copying: use the `padding` arg of `nn.Conv1d`, then slice off the trailing padding
  (`x = x[:, :, :-self.padding_size]`) to enforce causality.
- PyTorch device must be auto-detected:
  `device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')`. Send model
  and all tensors to this device so the code never crashes on CPU-only machines.
- Persist the log-key→int vocabulary (`vocab.json`) alongside model weights (`model.pt`)
  so inference indices match training exactly.

## Security / Compliance (FORBIDDEN ACTIONS)

- **Never** send raw IPs, IBANs, customer names, emails, or card numbers to the LLM.
  Mask everything via `src/anonymizer/mask.py` first.
- IP pseudonymization is **deterministic** (salted SHA-256) so temporal correlation of
  attacks from the same IP is preserved. Timestamps are never altered.
- **Never** call external cloud APIs (OpenAI/Anthropic). All LLM inference goes through a
  local OpenAI-compatible `/v1/chat/completions` endpoint (mock or local Ollama).
- **Zero hallucination**: if no document/history reference matches a log, the LLM returns
  `{"action": "UNKNOWN", "reason": "Kök neden bilinmiyor"}` — it never invents a fix.

## Architecture

`log → Anonymizer → CausalConvLSTM risk score → Two-Step Inference
 (Stage-1 threshold filter < 0.35 → "Safe") → (Stage-2 EnrichLog RAG + local LLM → RCA)
 → HealingOrchestrator (mock Docker/K8s) → immutable SQLite audit (hash-chained)`
