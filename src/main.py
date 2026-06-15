"""SentinelOps end-to-end pipeline orchestrator.

Wires the full flow together:

    log -> Anonymizer -> CausalConvLSTM risk score -> Two-Step Inference
        -> (Stage-2) EnrichLog RAG + local LLM -> HealingOrchestrator (mock K8s)
        -> immutable audit log

The model is trained on a small synthetic dataset derived from the input log's keys so
the demo is self-contained (no external dataset/network needed). All inference is local.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple, cast

# Allow `python src/main.py` to import the top-level `src` package by adding the
# project root to sys.path when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import torch  # noqa: E402
import yaml  # noqa: E402

from src.anonymizer.mask import Anonymizer  # noqa: E402
from src.messaging.bus import MessageBus  # noqa: E402
from src.models.causal_lstm import CausalConvLSTM  # noqa: E402
from src.models.train import (  # noqa: E402
    TrainConfig,
    build_vocab,
    encode_window,
    get_device,
    train_model,
)
from src.orchestrator.audit import AuditStore  # noqa: E402
from src.orchestrator.healing import HealingOrchestrator  # noqa: E402
from src.rag.embeddings import build_embedder  # noqa: E402
from src.rag.enrich_log import EnrichLogService, Verdict  # noqa: E402
from src.rag.llm_client import LLMClient  # noqa: E402
from src.rag.vector_store import VectorStore, load_documents_from_dir  # noqa: E402

_KEY_RE = re.compile(r"key=([A-Z_]+)")

# Keys that indicate an anomaly, used to label the synthetic training data.
_ANOMALY_KEYS = {"MEM_PRESSURE", "OOM_KILL", "PROBE_FAIL", "CRASHLOOP"}


def load_config(path: str | Path) -> Dict[str, Any]:
    """Load the YAML configuration file."""
    return cast(Dict[str, Any], yaml.safe_load(Path(path).read_text()))


def extract_keys(lines: List[str]) -> List[str]:
    """Extract the ``key=...`` log key from each line (or ``<UNK>`` if absent)."""
    keys: List[str] = []
    for line in lines:
        match = _KEY_RE.search(line)
        keys.append(match.group(1) if match else "UNKNOWN_KEY")
    return keys


def build_windows(
    keys: List[str], window_size: int
) -> Tuple[List[List[str]], List[int]]:
    """Build sliding windows of preceding keys and the index of the target line.

    Returns the list of key-windows and the corresponding center line indices so each
    risk score can be attributed back to a specific log line.
    """
    windows: List[List[str]] = []
    targets: List[int] = []
    for i in range(len(keys)):
        start = max(0, i - window_size + 1)
        window = keys[start : i + 1]
        # Left-pad short windows so every window has equal length.
        if len(window) < window_size:
            window = ["UNKNOWN_KEY"] * (window_size - len(window)) + window
        windows.append(window)
        targets.append(i)
    return windows, targets


def make_synthetic_dataset(
    windows: List[List[str]], keys: List[str], vocab: Dict[str, int]
) -> Tuple[List[List[int]], List[float]]:
    """Encode windows and assign synthetic anomaly labels from the target key."""
    encoded = [encode_window(w, vocab) for w in windows]
    labels = [1.0 if keys[i] in _ANOMALY_KEYS else 0.0 for i in range(len(keys))]
    return encoded, labels


def run(input_path: str, config_path: str = "config/config.yaml") -> None:
    """Run the full pipeline over ``input_path`` and print a report."""
    cfg = load_config(config_path)
    model_cfg = cfg["model"]
    train_cfg_raw = cfg["training"]
    rag_cfg = cfg["rag"]
    llm_cfg = cfg["llm"]

    lines = [ln for ln in Path(input_path).read_text().splitlines() if ln.strip()]
    anonymizer = Anonymizer(ip_salt=str(cfg["anonymizer"]["ip_salt"]))
    masked_lines = [anonymizer.mask(ln) for ln in lines]

    keys = extract_keys(lines)
    window_size = int(model_cfg["window_size"])
    windows, _ = build_windows(keys, window_size)
    vocab = build_vocab(windows)
    encoded, labels = make_synthetic_dataset(windows, keys, vocab)

    device = get_device()
    model = CausalConvLSTM(
        vocab_size=len(vocab),
        embedding_dim=int(model_cfg["embedding_dim"]),
        conv_channels=int(model_cfg["conv_channels"]),
        kernel_size=int(model_cfg["kernel_size"]),
        dilation=int(model_cfg["dilation"]),
        lstm_hidden=int(model_cfg["lstm_hidden"]),
        lstm_layers=int(model_cfg["lstm_layers"]),
        dropout=float(model_cfg["dropout"]),
    )
    train_cfg = TrainConfig(
        epochs=int(train_cfg_raw["epochs"]),
        batch_size=int(train_cfg_raw["batch_size"]),
        learning_rate=float(train_cfg_raw["learning_rate"]),
        l2_lambda=float(train_cfg_raw["l2_lambda"]),
        seed=int(train_cfg_raw["seed"]),
    )
    print(f"[train] device={device.type} samples={len(encoded)} vocab={len(vocab)}")
    losses = train_model(model, encoded, labels, train_cfg, device=device)
    print(f"[train] final loss={losses[-1]:.4f}")

    # Compute risk scores.
    model.eval()
    with torch.no_grad():
        scores = model(torch.tensor(encoded, dtype=torch.long, device=device))
    risk_scores = [float(s) for s in scores.cpu().tolist()]

    # Build RAG store.
    embedder = build_embedder(
        mode=str(rag_cfg["embeddings_mode"]),
        hash_dim=int(rag_cfg["embedding_dim"]),
        hf_model_name=str(rag_cfg["hf_model_name"]),
    )
    store = VectorStore(embedder)
    store.add(load_documents_from_dir(str(rag_cfg["error_corpus_dir"]), "error_corpus"))
    store.add(load_documents_from_dir(str(rag_cfg["system_docs_dir"]), "system_docs"))

    llm = LLMClient(
        mode=str(llm_cfg["mode"]),
        base_url=str(llm_cfg["base_url"]),
        model=str(llm_cfg["model"]),
    )
    enricher = EnrichLogService(
        vector_store=store,
        llm_client=llm,
        risk_threshold=float(cfg["inference"]["risk_threshold"]),
        top_k=int(rag_cfg["top_k"]),
    )

    audit = AuditStore(str(cfg["audit"]["db_path"]))
    healer = HealingOrchestrator(audit)
    bus = MessageBus()

    counter = {"idx": 0}

    def handle(message: str) -> None:
        idx = counter["idx"]
        counter["idx"] += 1
        score = risk_scores[idx]
        result = enricher.process(message, score)
        if result.verdict is Verdict.SAFE:
            print(f"[safe ] score={score:.3f} | {message[:70]}")
            audit.append(message, score, result.verdict.value, {"action": "NONE"})
            return
        action = result.action or {"action": "UNKNOWN"}
        outcome = healer.execute(action, message, score, result.verdict.value)
        print(
            f"[ANOM ] score={score:.3f} action={outcome.action.value} "
            f"target={outcome.target} executed={outcome.executed}"
        )
        print(f"        RCA: {result.rca}")
        print(f"        cmd: {outcome.detail}")

    topic = str(cfg["messaging"]["topic"])
    bus.subscribe(topic, handle)
    for masked in masked_lines:
        bus.publish(topic, masked)

    print(
        f"\n[audit] records={audit.count()} chain_intact={audit.verify_chain()} "
        f"ops={healer.controller.operations}"
    )
    audit.close()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="SentinelOps pipeline")
    parser.add_argument("--input", default="data/sample_bgl.log", help="log file path")
    parser.add_argument("--config", default="config/config.yaml", help="config path")
    args = parser.parse_args()
    run(args.input, args.config)


if __name__ == "__main__":
    main()
