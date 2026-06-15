"""Tests for CausalConvLSTM: causality, padding formula, and the L2-BCE training loop."""

from __future__ import annotations

import torch

from src.models.causal_lstm import CausalConv1d, CausalConvLSTM
from src.models.train import (
    TrainConfig,
    build_vocab,
    encode_window,
    get_device,
    train_model,
)


def test_causal_conv_padding_formula() -> None:
    k, d = 3, 2
    conv = CausalConv1d(in_channels=4, out_channels=8, kernel_size=k, dilation=d)
    assert conv.padding_size == (k - 1) * d


def test_causal_conv_preserves_length() -> None:
    conv = CausalConv1d(in_channels=4, out_channels=8, kernel_size=3, dilation=1)
    x = torch.randn(2, 4, 10)
    out = conv(x)
    assert out.shape == (2, 8, 10)


def test_convolution_is_causal() -> None:
    """Changing a future timestep must not affect earlier outputs."""
    torch.manual_seed(0)
    conv = CausalConv1d(in_channels=2, out_channels=3, kernel_size=3, dilation=1)
    conv.eval()
    x = torch.randn(1, 2, 8)
    with torch.no_grad():
        base = conv(x)
        x_mod = x.clone()
        x_mod[:, :, -1] += 100.0  # perturb only the last timestep
        modified = conv(x_mod)
    # All outputs except the final position must be unchanged.
    assert torch.allclose(base[:, :, :-1], modified[:, :, :-1], atol=1e-5)
    assert not torch.allclose(base[:, :, -1], modified[:, :, -1])


def test_model_output_in_unit_range() -> None:
    model = CausalConvLSTM(vocab_size=10, embedding_dim=8, conv_channels=8, lstm_hidden=8)
    model.eval()
    x = torch.randint(0, 10, (4, 6))
    with torch.no_grad():
        out = model(x)
    assert out.shape == (4,)
    assert torch.all(out >= 0.0) and torch.all(out <= 1.0)


def test_training_loop_reduces_loss() -> None:
    normal = ["A", "B", "C"]
    anomaly = ["X", "Y", "Z"]
    windows = [normal, anomaly] * 8
    vocab = build_vocab(windows)
    encoded = [encode_window(w, vocab) for w in windows]
    labels = [0.0, 1.0] * 8

    model = CausalConvLSTM(
        vocab_size=len(vocab), embedding_dim=8, conv_channels=8, lstm_hidden=8
    )
    cfg = TrainConfig(epochs=40, batch_size=4, learning_rate=0.01, l2_lambda=1e-5)
    losses = train_model(model, encoded, labels, cfg, device=get_device())
    assert losses[-1] < losses[0]
    assert losses[-1] < 0.3  # learns to separate the two classes


def test_separates_normal_from_anomaly_after_training() -> None:
    normal = ["A", "B", "C"]
    anomaly = ["X", "Y", "Z"]
    windows = [normal, anomaly] * 8
    vocab = build_vocab(windows)
    encoded = [encode_window(w, vocab) for w in windows]
    labels = [0.0, 1.0] * 8
    model = CausalConvLSTM(
        vocab_size=len(vocab), embedding_dim=8, conv_channels=8, lstm_hidden=8
    )
    cfg = TrainConfig(epochs=60, batch_size=4, learning_rate=0.01, l2_lambda=1e-5)
    train_model(model, encoded, labels, cfg, device=get_device())
    model.eval()
    with torch.no_grad():
        normal_score = float(
            model(torch.tensor([encode_window(normal, vocab)], dtype=torch.long))[0]
        )
        anomaly_score = float(
            model(torch.tensor([encode_window(anomaly, vocab)], dtype=torch.long))[0]
        )
    assert normal_score < 0.35 <= anomaly_score
