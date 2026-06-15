"""CausalConvLSTM anomaly-detection model.

The model consumes windows of log-key indices ``X = <k_{t-w}, ..., k_{t-1}>`` and
produces an anomaly probability (risk score in ``[0, 1]``). A causal 1-D convolution
ensures no future information leaks into a given timestep, and an LSTM aggregates the
temporal context before a linear classifier emits the risk score.
"""

from __future__ import annotations

import torch
import torch.nn as nn


class CausalConv1d(nn.Module):
    """A 1-D convolution with strictly-causal (left-only) receptive field.

    Causality is enforced by padding both sides via ``nn.Conv1d``'s ``padding`` argument
    (avoiding ``F.pad``, which would copy memory) and then slicing off the trailing
    padding so each output position only depends on current and past inputs.

    Left padding amount follows ``P = (k - 1) * d`` where ``k`` is the kernel size and
    ``d`` the dilation.
    """

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int,
        dilation: int = 1,
    ) -> None:
        super().__init__()
        self.padding_size: int = (kernel_size - 1) * dilation
        self.conv = nn.Conv1d(
            in_channels,
            out_channels,
            kernel_size=kernel_size,
            padding=self.padding_size,
            dilation=dilation,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Apply the causal convolution to ``x`` of shape ``(B, C, L)``."""
        x = self.conv(x)
        if self.padding_size != 0:
            # Trim trailing padding so output[t] depends only on input[<= t].
            x = x[:, :, : -self.padding_size]
        return x


class CausalConvLSTM(nn.Module):
    """Embedding -> CausalConv1d -> LSTM -> linear sigmoid risk-score head.

    Args:
        vocab_size: Number of distinct log keys (size of the embedding table).
        embedding_dim: Dimension of log-key embeddings.
        conv_channels: Output channels of the causal convolution.
        kernel_size: Convolution kernel size ``k``.
        dilation: Convolution dilation ``d``.
        lstm_hidden: Hidden size of the LSTM.
        lstm_layers: Number of stacked LSTM layers.
        dropout: Dropout applied before the classifier.
    """

    def __init__(
        self,
        vocab_size: int,
        embedding_dim: int = 32,
        conv_channels: int = 64,
        kernel_size: int = 3,
        dilation: int = 1,
        lstm_hidden: int = 64,
        lstm_layers: int = 1,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embedding_dim)
        self.causal_conv = CausalConv1d(
            in_channels=embedding_dim,
            out_channels=conv_channels,
            kernel_size=kernel_size,
            dilation=dilation,
        )
        self.relu = nn.ReLU()
        self.lstm = nn.LSTM(
            input_size=conv_channels,
            hidden_size=lstm_hidden,
            num_layers=lstm_layers,
            batch_first=True,
        )
        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(lstm_hidden, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Compute risk scores for a batch of log-key windows.

        Args:
            x: Long tensor of shape ``(B, L)`` containing log-key indices.

        Returns:
            Float tensor of shape ``(B,)`` with risk scores in ``[0, 1]``.
        """
        # (B, L) -> (B, L, E)
        emb = self.embedding(x)
        # (B, L, E) -> (B, E, L) for Conv1d which expects channels-first.
        conv_in = emb.transpose(1, 2)
        conv_out = self.relu(self.causal_conv(conv_in))
        # (B, C, L) -> (B, L, C) for the LSTM (batch_first).
        lstm_in = conv_out.transpose(1, 2)
        _, (hidden, _) = self.lstm(lstm_in)
        # Last layer's final hidden state: (num_layers, B, H) -> (B, H).
        last_hidden = hidden[-1]
        logits = self.classifier(self.dropout(last_hidden)).squeeze(-1)
        return torch.sigmoid(logits)
