"""Cluster colours: distinct, stable, readable on a dark background.

New colours are picked greedily from a dense OKLCH candidate grid (lightness 0.62-0.82, every
whole-degree hue, chroma at the sRGB gamut limit), each time taking the candidate whose
smallest OKLab distance to every colour already in use is largest. Existing colours are never
changed, and the same inputs always give the same output.
"""

from __future__ import annotations

import numpy as np

LIGHTNESS = np.round(np.arange(0.62, 0.8201, 0.025), 3)
HUES = np.arange(0, 360, 1.0)
_EPS = 1e-6

_LMS_TO_LAB = np.array(
    [
        [0.2104542553, 0.7936177850, -0.0040720468],
        [1.9779984951, -2.4285922050, 0.4505937099],
        [0.0259040371, 0.7827717662, -0.8086757660],
    ]
)
_RGB_TO_LMS = np.array(
    [
        [0.4122214708, 0.5363325363, 0.0514459929],
        [0.2119034982, 0.6806995451, 0.1073969566],
        [0.0883024619, 0.2817188376, 0.6299787005],
    ]
)
_LAB_TO_LMS = np.linalg.inv(_LMS_TO_LAB)
_LMS_TO_RGB = np.linalg.inv(_RGB_TO_LMS)


def _oklab_to_linear(lab: np.ndarray) -> np.ndarray:
    return (lab @ _LAB_TO_LMS.T) ** 3 @ _LMS_TO_RGB.T


def _linear_to_oklab(rgb: np.ndarray) -> np.ndarray:
    return np.cbrt(rgb @ _RGB_TO_LMS.T) @ _LMS_TO_LAB.T


def _encode(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def _decode(x: np.ndarray) -> np.ndarray:
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def _lch_to_lab(L, C, h_deg):
    h = np.radians(h_deg)
    return np.stack([L, C * np.cos(h), C * np.sin(h)], axis=-1)


def _max_chroma(L: np.ndarray, h: np.ndarray, iters: int = 30) -> np.ndarray:
    lo, hi = np.zeros_like(L), np.full_like(L, 0.4)
    for _ in range(iters):
        mid = (lo + hi) / 2
        rgb = _oklab_to_linear(_lch_to_lab(L, mid, h))
        ok = ((rgb >= -_EPS) & (rgb <= 1 + _EPS)).all(axis=-1)
        lo, hi = np.where(ok, mid, lo), np.where(ok, hi, mid)
    return lo


def to_hex(rgb: np.ndarray) -> list[str]:
    return ["#{:02x}{:02x}{:02x}".format(*c) for c in np.round(_encode(rgb) * 255).astype(int)]


def hex_to_oklab(colours: list[str]) -> np.ndarray:
    if not colours:
        return np.zeros((0, 3))
    srgb = np.array([[int(c[i : i + 2], 16) / 255 for i in (1, 3, 5)] for c in colours])
    return _linear_to_oklab(_decode(srgb))


def _candidates() -> tuple[list[str], np.ndarray]:
    L, h = np.meshgrid(LIGHTNESS, HUES, indexing="ij")
    L, h = L.ravel(), h.ravel()
    hexes = to_hex(_oklab_to_linear(_lch_to_lab(L, _max_chroma(L, h), h)))
    unique = list(dict.fromkeys(hexes))  # keep first occurrence, deterministic order
    return unique, hex_to_oklab(unique)


def new_colours(existing: list[str], n_new: int, avoid: list[str] = ()) -> list[str]:
    """n_new colours as far as possible (OKLab) from `existing` and from each other. Colours in
    `avoid` (e.g. retired clusters') are never returned but don't push the others away."""
    if n_new <= 0:
        return []
    hexes, labs = _candidates()
    used = {c.lower() for c in (*existing, *avoid)}
    dist = np.full(len(hexes), np.inf)
    ex = hex_to_oklab(list(existing))
    if len(ex):
        dist = np.linalg.norm(labs[:, None, :] - ex[None, :, :], axis=-1).min(axis=1)
    dist[[i for i, c in enumerate(hexes) if c in used]] = -1
    out = []
    for _ in range(n_new):
        i = int(np.argmax(dist))  # first maximum wins ties
        if dist[i] < 0:
            raise ValueError(f"palette exhausted after {len(out)} new colours")
        out.append(hexes[i])
        dist = np.minimum(dist, np.linalg.norm(labs - labs[i], axis=1))
        dist[i] = -1
    return out


def min_distance(colours: list[str]) -> float:
    """Smallest pairwise OKLab distance (inf for fewer than 2 colours)."""
    lab = hex_to_oklab(colours)
    if len(lab) < 2:
        return float("inf")
    d = np.linalg.norm(lab[:, None, :] - lab[None, :, :], axis=-1)
    d[np.diag_indices(len(lab))] = np.inf
    return float(d.min())
