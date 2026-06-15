"""Training utilities for :class:`CausalConvLSTM`.

Implements an L2-regularised Binary Cross-Entropy objective. The L2 term
``(lambda / 2) * sum(theta_j^2)`` is realised via the optimizer's ``weight_decay``,
which is the standard, numerically-stable way to add L2 regularisation in PyTorch.

The device (CPU/GPU) is auto-detected so the code never crashes on CPU-only machines,
and the log-key vocabulary is persisted next to the weights so inference indices match
training exactly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import torch
import torch.nn as nn

from src.models.causal_lstm import CausalConvLSTM

# Reserved index for unknown / out-of-vocabulary log keys at inference time.
UNK_TOKEN = "<UNK>"


def get_device() -> torch.device:
    """Return CUDA if available, otherwise CPU."""
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def build_vocab(sequences: Sequence[Sequence[str]]) -> Dict[str, int]:
    """Build a deterministic log-key -> index vocabulary.

    Index 0 is reserved for :data:`UNK_TOKEN`. Keys are assigned in sorted order so the
    mapping is reproducible across runs.
    """
    keys = sorted({k for seq in sequences for k in seq})
    vocab: Dict[str, int] = {UNK_TOKEN: 0}
    for key in keys:
        vocab[key] = len(vocab)
    return vocab


def encode_window(window: Sequence[str], vocab: Dict[str, int]) -> List[int]:
    """Encode a window of log keys to indices, mapping unknowns to ``<UNK>``."""
    unk = vocab[UNK_TOKEN]
    return [vocab.get(key, unk) for key in window]


@dataclass
class TrainConfig:
    """Hyper-parameters for the training loop."""

    epochs: int = 30
    batch_size: int = 16
    learning_rate: float = 0.005
    l2_lambda: float = 1e-4
    seed: int = 42


def train_model(
    model: CausalConvLSTM,
    windows: List[List[int]],
    labels: List[float],
    config: TrainConfig,
    device: torch.device | None = None,
) -> List[float]:
    """Train ``model`` with L2-regularised BCE and return per-epoch losses.

    Args:
        model: The model to train (moved to ``device`` in-place).
        windows: List of equal-length index windows.
        labels: Binary anomaly labels (0.0 normal, 1.0 anomaly).
        config: Training hyper-parameters.
        device: Target device; auto-detected when ``None``.
    """
    device = device or get_device()
    torch.manual_seed(config.seed)
    model.to(device)
    model.train()

    x = torch.tensor(windows, dtype=torch.long, device=device)
    y = torch.tensor(labels, dtype=torch.float32, device=device)

    criterion = nn.BCELoss()
    # weight_decay = lambda implements the (lambda/2) * sum(theta^2) L2 penalty.
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.l2_lambda,
    )

    n = x.shape[0]
    losses: List[float] = []
    for _ in range(config.epochs):
        perm = torch.randperm(n, device=device)
        epoch_loss = 0.0
        batches = 0
        for start in range(0, n, config.batch_size):
            idx = perm[start : start + config.batch_size]
            optimizer.zero_grad()
            preds = model(x[idx])
            loss = criterion(preds, y[idx])
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.item())
            batches += 1
        losses.append(epoch_loss / max(batches, 1))
    return losses


def save_artifacts(
    model: CausalConvLSTM,
    vocab: Dict[str, int],
    out_dir: str | Path,
) -> Tuple[Path, Path]:
    """Persist model weights and the vocabulary together.

    Returns the paths to ``model.pt`` and ``vocab.json``.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    weights_path = out / "model.pt"
    vocab_path = out / "vocab.json"
    torch.save(model.state_dict(), weights_path)
    vocab_path.write_text(json.dumps(vocab, ensure_ascii=False, indent=2))
    return weights_path, vocab_path


def load_vocab(vocab_path: str | Path) -> Dict[str, int]:
    """Load a vocabulary previously saved by :func:`save_artifacts`."""
    data = json.loads(Path(vocab_path).read_text())
    return {str(k): int(v) for k, v in data.items()}
