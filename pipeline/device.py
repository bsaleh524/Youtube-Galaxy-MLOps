"""Pick the fastest available torch device: CUDA, then Apple MPS, then CPU."""

from __future__ import annotations


def best_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"
