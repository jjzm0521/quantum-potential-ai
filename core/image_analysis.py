"""
core.image_analysis — preprocesamiento de imagen fuente con VISIÓN CLÁSICA (sin API).

Cuando el estudiante sube una foto (AFM/SEM/esquema) de un potencial, antes el LLM
partía de cero. Aquí, con numpy + scipy.ndimage, detectamos blobs, contamos regiones y
medimos simetría para SUGERIR un preset + parámetros de arranque. El LLM (el "cerebro")
decide si aplicarlos; esto solo le da un punto de partida y acelera el loop.

Salida: dict JSON-serializable con sugerencia y razonamiento.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy import ndimage


def _load_gray(path: str | Path) -> np.ndarray:
    """Carga imagen → escala de grises normalizada [0,1]. PNG nativo (matplotlib);
    JPG y otros requieren Pillow (fallback con mensaje claro)."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".png":
        import matplotlib.image as mpimg
        img = mpimg.imread(str(p))
    else:
        try:
            from PIL import Image
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                f"Para leer {ext} necesitas Pillow:  pip install Pillow  "
                "(los PNG funcionan sin él)."
            ) from exc
        img = np.asarray(Image.open(p))

    img = np.asarray(img, dtype=float)
    if img.ndim == 3:  # RGB(A) → luminancia
        img = img[..., :3].mean(axis=2)
    # Normaliza a [0,1] sin importar si venía en 0-255 o 0-1.
    lo, hi = float(img.min()), float(img.max())
    return (img - lo) / (hi - lo + 1e-12)


def _otsu_threshold(gray: np.ndarray, nbins: int = 256) -> float:
    """Umbral de Otsu: maximiza varianza entre clases. Solo numpy."""
    hist, edges = np.histogram(gray.ravel(), bins=nbins, range=(0.0, 1.0))
    hist = hist.astype(float)
    total = hist.sum()
    if total == 0:
        return 0.5
    centers = 0.5 * (edges[:-1] + edges[1:])
    w_b = np.cumsum(hist)
    w_f = total - w_b
    sum_total = np.cumsum(hist * centers)
    mean_b = np.divide(sum_total, w_b, out=np.zeros_like(sum_total), where=w_b > 0)
    grand = sum_total[-1]
    mean_f = np.divide(grand - sum_total, w_f, out=np.zeros_like(sum_total), where=w_f > 0)
    between = w_b * w_f * (mean_b - mean_f) ** 2
    return float(centers[int(np.argmax(between))])


def analyze_image(path: str | Path) -> dict:
    """Analiza la imagen y sugiere preset + parámetros iniciales."""
    gray = _load_gray(path)
    H, W = gray.shape

    # Los pozos suelen verse OSCUROS (baja intensidad). Probamos esa hipótesis y la
    # opuesta; nos quedamos con la que da regiones más limpias (menos fragmentadas).
    thr = _otsu_threshold(gray)
    cand_dark = gray < thr
    cand_light = gray > thr
    mask = cand_dark if cand_dark.mean() <= cand_light.mean() else cand_light

    labels, n = ndimage.label(mask)
    # Filtra regiones por área mínima (0.3% del total) para descartar ruido.
    min_area = 0.003 * H * W
    regions = []
    for lab in range(1, n + 1):
        ys, xs = np.where(labels == lab)
        if xs.size < min_area:
            continue
        # Coordenadas normalizadas a [-1,1] con (0,0) al centro de la imagen.
        cx = (xs.mean() / W) * 2 - 1
        cy = (ys.mean() / H) * 2 - 1
        regions.append({
            "centroid": [round(float(cx), 3), round(float(-cy), 3)],  # y arriba+
            "area_frac": round(float(xs.size / (H * W)), 4),
            "bbox_wh": [int(xs.max() - xs.min()), int(ys.max() - ys.min())],
        })

    nreg = len(regions)
    suggestion = _suggest(regions, mask)
    suggestion["n_regions"] = nreg
    suggestion["image_size"] = [int(W), int(H)]
    return suggestion


def _has_central_hole(mask: np.ndarray) -> bool:
    """Un anillo: una sola región grande con un hueco interno (centro NO en la región)."""
    filled = ndimage.binary_fill_holes(mask)
    hole = filled & ~mask
    if not hole.any():
        return False
    H, W = mask.shape
    cy, cx = H // 2, W // 2
    # El hueco rodea el centro de la imagen.
    return bool(hole[cy, cx]) and hole.mean() > 0.01


def _suggest(regions: list[dict], mask: np.ndarray) -> dict:
    """Heurística regiones→preset. Confianza refleja qué tan limpia es la señal."""
    n = len(regions)

    if n == 1 and _has_central_hole(mask):
        return {
            "suggested_preset": "quantum_ring", "suggested_dim": 2,
            "suggested_params": {"depth": 0.2, "r0": 25.0, "width": 8.0},
            "reasoning": "Una región con hueco central → anillo cuántico.",
            "confidence": 0.7,
        }
    if n == 1:
        return {
            "suggested_preset": "quantum_dot", "suggested_dim": 2,
            "suggested_params": {"depth": 0.2, "sigma": 12.0},
            "reasoning": "Un solo blob central → punto cuántico (quantum dot).",
            "confidence": 0.7,
        }
    if n == 2:
        return {
            "suggested_preset": "double_dot", "suggested_dim": 2,
            "suggested_params": {"depth": 0.2, "sigma": 10.0, "separation": 30.0},
            "reasoning": "Dos blobs → doble punto. Si es 1D, considera 'double_well'.",
            "confidence": 0.6,
        }
    if n == 3:
        return {
            "suggested_preset": "triple_dot", "suggested_dim": 2,
            "suggested_params": {"depth": 0.2, "sigma": 9.0, "r_triangle": 25.0},
            "reasoning": "Tres blobs → triple punto (probable disposición triangular).",
            "confidence": 0.55,
        }
    if n >= 4 and _looks_periodic(regions):
        return {
            "suggested_preset": None, "suggested_dim": 1,
            "suggested_params": {},
            "reasoning": f"{n} regiones en patrón periódico → superred / multi-barrera. "
                         "Construye con piezas 'barrier' repetidas (no hay preset directo).",
            "confidence": 0.4,
        }
    return {
        "suggested_preset": None, "suggested_dim": 2,
        "suggested_params": {},
        "reasoning": f"{n} regiones, geometría no estándar. Inspecciona el render y "
                     "construye manualmente con gaussian/mask.",
        "confidence": 0.3,
    }


def _looks_periodic(regions: list[dict], rtol: float = 0.25) -> bool:
    """Centroides ~equiespaciados a lo largo de x → patrón periódico (superred)."""
    xs = sorted(r["centroid"][0] for r in regions)
    if len(xs) < 3:
        return False
    gaps = np.diff(xs)
    return bool(np.std(gaps) / (np.mean(gaps) + 1e-12) < rtol)
