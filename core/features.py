"""
core.features — extracción de features físicas cuantitativas de un potencial.

El loop Designer→Verify→Refiner usa al LLM como "cerebro". Antes, para juzgar si el
potencial coincide con el objetivo, el LLM tenía que MIRAR el PNG y adivinar. Aquí
extraemos números medibles (nº de pozos, posiciones, profundidades, simetría) para que
el Refiner converja con datos, no con adivinanza. Solo numpy/scipy: sin API de pago.

Entrada: el `field` dict de session.evaluate_potential
    1D: {"dim": 1, "x_nm": x, "V_eV": V, ...}
    2D: {"dim": 2, "x_nm": x, "y_nm": y, "V_eV": V[iy, ix], ...}
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage
from scipy.signal import find_peaks


def extract_features(field: dict) -> dict:
    """Devuelve features cuantitativas del potencial (JSON-serializable)."""
    if field["dim"] == 1:
        return _features_1d(field)
    return _features_2d(field)


# ---------------------------------------------------------------------------
# 1D
# ---------------------------------------------------------------------------

def _features_1d(field: dict) -> dict:
    x = np.asarray(field["x_nm"], dtype=float)
    V = np.asarray(field["V_eV"], dtype=float) * 1000.0  # meV

    finite = V[np.isfinite(V)]
    if finite.size == 0:
        return {"error": "potencial sin valores finitos"}
    v_min, v_max = float(finite.min()), float(finite.max())

    # Clip robusto: paredes repulsivas (Morse, triangular, r^4) inflan v_max y
    # aplastarían la prominencia. Mismo criterio que render._clip_range: si hay pozo
    # (v_min<0), el techo útil es ~media profundidad por encima de cero.
    if v_min < -1e-6:
        hi = min(float(np.percentile(finite, 90)), abs(v_min) * 0.5)
        if hi <= v_min:
            hi = v_min + abs(v_min) * 0.5 + 1.0
    else:
        # Sin pozo (barrera/step): p99 conserva la estructura positiva sin las
        # paredes infinitas del dominio.
        hi = float(np.percentile(finite, 99))
    Vc = np.clip(np.where(np.isfinite(V), V, v_max), v_min, hi)
    span = hi - v_min

    # Prominencia mínima ~5% del rango (clipeado) para ignorar ruido numérico.
    prom = max(1e-6, 0.05 * span)

    # Pozos = mínimos de V = picos de -V. distance evita duplicados pegados.
    min_dist = max(1, len(x) // 50)
    well_idx, _ = find_peaks(-Vc, prominence=prom, distance=min_dist)
    # Barreras = máximos locales (interiores, no las paredes del dominio).
    barr_idx, _ = find_peaks(Vc, prominence=prom, distance=min_dist)

    # Profundidad física: respecto a 0 si el pozo es negativo, si no al techo clipeado.
    def _depth(i: int) -> float:
        ref = 0.0 if V[i] < 0 else hi
        return round(float(ref - V[i]), 2)

    well_pos = [round(float(x[i]), 2) for i in well_idx]
    well_depth = [_depth(i) for i in well_idx]
    barr_pos = [round(float(x[i]), 2) for i in barr_idx]
    barr_h = [round(float(V[i] - v_min), 2) for i in barr_idx]

    feats: dict = {
        "n_wells": int(len(well_idx)),
        "well_positions_nm": well_pos,
        "well_depths_meV": well_depth,
        "n_barriers": int(len(barr_idx)),
        "barrier_positions_nm": barr_pos,
        "barrier_heights_meV": barr_h,
        "symmetric": _is_symmetric_1d(V),
        "v_min_meV": round(v_min, 2),
        "v_max_meV": round(v_max, 2),
    }
    if len(well_pos) >= 2:
        seps = np.diff(sorted(well_pos))
        feats["well_separation_nm"] = round(float(np.mean(seps)), 2)
    return feats


def _is_symmetric_1d(V: np.ndarray, rtol: float = 0.05) -> bool:
    """V(x) ≈ V(-x): compara contra el reverso del array (grilla simétrica en 0)."""
    finite = np.where(np.isfinite(V), V, 0.0)
    diff = np.abs(finite - finite[::-1])
    scale = np.abs(finite).max() + 1e-12
    return bool(np.mean(diff) / scale < rtol)


# ---------------------------------------------------------------------------
# 2D
# ---------------------------------------------------------------------------

def _features_2d(field: dict) -> dict:
    x = np.asarray(field["x_nm"], dtype=float)
    y = np.asarray(field["y_nm"], dtype=float)
    V = np.asarray(field["V_eV"], dtype=float) * 1000.0  # meV, shape [iy, ix]

    finite = V[np.isfinite(V)]
    if finite.size == 0:
        return {"error": "potencial sin valores finitos"}
    v_min, v_max = float(finite.min()), float(finite.max())

    # En anillos/barreras el potencial crece como r^4 hacia los bordes y aplasta el
    # pozo. Clip robusto por percentiles para que el análisis enfoque el pozo, igual
    # que hace el render (core.render._clip_range).
    hi = float(np.percentile(finite, 90))
    Vf = np.clip(np.where(np.isfinite(V), V, v_max), v_min, hi)
    span = hi - v_min

    # Pozos = regiones por debajo de un umbral cercano al mínimo.
    thr = v_min + 0.30 * span if span > 1e-9 else v_min
    mask = Vf < thr
    labels, n = ndimage.label(mask)

    centroids: list[list[float]] = []
    depths: list[float] = []
    for lab in range(1, n + 1):
        ys, xs = np.where(labels == lab)
        if xs.size < 3:  # descarta motas de ruido
            continue
        cx = float(np.mean(x[xs]))
        cy = float(np.mean(y[ys]))
        centroids.append([round(cx, 2), round(cy, 2)])
        # Profundidad física: respecto a 0 si el pozo es negativo, si no respecto
        # al techo clipeado (evita el blowup r^4 de las esquinas que infla v_max).
        wmin = float(V[ys, xs].min())
        ref = 0.0 if wmin < 0 else hi
        depths.append(round(ref - wmin, 2))

    # Centro de análisis radial = centroide de la región de bajo potencial (para un
    # anillo es el centro geométrico; para un dot es el propio pozo).
    if mask.any():
        ys, xs = np.where(mask)
        cx0, cy0 = float(np.mean(x[xs])), float(np.mean(y[ys]))
    else:
        cx0 = cy0 = 0.0

    feats: dict = {
        "n_wells": int(len(centroids)),
        "well_centroids_nm": centroids,
        "well_depths_meV": depths,
        "v_min_meV": round(v_min, 2),
        "v_max_meV": round(v_max, 2),
        "ring_like": _is_ring_like(x, y, Vf, cx0, cy0),
        "radial_symmetry": _is_radially_symmetric(x, y, Vf, cx0, cy0),
    }
    return feats


def harmonic_benchmark(field: dict, m_eff: float, energies_meV: list[float]) -> dict:
    """Contraste analítico: aproximación armónica del fondo del pozo.

    Para cualquier pozo suave, cerca del mínimo V ≈ V0 + ½ m ω² q² y el espaciado
    E1−E0 debe acercarse a ħω = ħ√(V''/m). La desviación mide la anarmonicidad —
    criterio de investigador clásico para validar el numérico contra la teoría.
    Devuelve dict JSON-serializable; {"applicable": False, ...} si no hay pozo suave.
    """
    HBAR = 1.054571817e-34  # J·s
    M_E = 9.10938e-31       # kg
    EV = 1.60218e-19        # J/eV
    NM = 1e-9               # m/nm

    if len(energies_meV) < 2:
        return {"applicable": False, "reason": "menos de 2 estados resueltos"}

    m = m_eff * M_E
    if field["dim"] == 1:
        x = np.asarray(field["x_nm"], dtype=float)
        V = np.asarray(field["V_eV"], dtype=float)
        i0 = int(np.nanargmin(np.where(np.isfinite(V), V, np.inf)))
        if i0 <= 1 or i0 >= len(x) - 2:
            return {"applicable": False, "reason": "mínimo en el borde del dominio"}

        # Dos modelos candidatos — caja (fondo plano) y armónico (fondo curvo) — y
        # reportamos el que MEJOR ajusta E1−E0. Clasificar por forma es frágil
        # (paredes enormes distorsionan las escalas); dejar que compitan es robusto.
        dx_nm = x[1] - x[0]
        E10 = round(float(energies_meV[1] - energies_meV[0]), 3)
        finite = V[np.isfinite(V)]
        v_min = float(finite.min())
        depth = abs(v_min) if v_min < -1e-9 else float(np.percentile(finite, 99)) - v_min
        depth = max(depth, 1e-9)

        # Fondo: tramo contiguo alrededor del mínimo dentro del 1% de la profundidad.
        flat = np.abs(V - V[i0]) < 0.01 * depth
        l = r = i0
        while l > 0 and flat[l - 1]:
            l -= 1
        while r < len(x) - 1 and flat[r + 1]:
            r += 1
        w_pts = r - l + 1

        candidates: list[dict] = []
        if w_pts >= 5:  # caja: E_n ∝ n²/w² con w = ancho del fondo plano
            w = w_pts * dx_nm * NM
            gap_box = 3 * (HBAR**2 * np.pi**2) / (2 * m * w**2) / EV * 1000  # meV
            candidates.append({
                "model": "particle_in_box",
                "well_width_nm": round(w / NM, 2),
                "predicted_gap_meV": round(float(gap_box), 3),
                "deviation_pct": round(abs(E10 - gap_box) / (abs(gap_box) + 1e-12) * 100, 1),
            })
        # Armónico: curvatura en el CENTRO del fondo (no en el borde de una mask).
        mid = (l + r) // 2
        k = min(3, mid, len(x) - 1 - mid)
        if k >= 1:
            d2V = (V[mid + k] - 2 * V[mid] + V[mid - k]) * EV / (k * dx_nm * NM) ** 2
            if d2V > 0:
                hw = float(HBAR * np.sqrt(d2V / m) / EV * 1000)  # ħω en meV
                candidates.append({
                    "model": "harmonic_bottom",
                    "hbar_omega_meV": round(hw, 3),
                    "predicted_gap_meV": round(hw, 3),
                    "deviation_pct": round(abs(E10 - hw) / (abs(hw) + 1e-12) * 100, 1),
                })
        if not candidates:
            return {"applicable": False, "reason": "sin fondo plano ni curvatura positiva"}

        best = min(candidates, key=lambda c: c["deviation_pct"])
        dev = best["deviation_pct"]
        interpretation = (
            f"E1−E0 numérico coincide con el modelo '{best['model']}' (desv. {dev}%): "
            "el solver reproduce la teoría." if dev < 15 else
            f"E1−E0 se desvía {dev}% del mejor modelo analítico ({best['model']}): "
            "esperable en pozos finitos (penetración de ψ), dobles pozos (splitting "
            "túnel) o potenciales muy anarmónicos. Verifica que sea tu caso."
        )
        return {"applicable": True, **best, "E1_minus_E0_meV": E10,
                "models_tested": [c["model"] for c in candidates],
                "interpretation": interpretation}
    else:
        x = np.asarray(field["x_nm"], dtype=float)
        y = np.asarray(field["y_nm"], dtype=float)
        V = np.asarray(field["V_eV"], dtype=float)
        Vf = np.where(np.isfinite(V), V, np.inf)
        iy, ix = np.unravel_index(int(np.nanargmin(Vf)), V.shape)
        if not (1 < ix < len(x) - 2 and 1 < iy < len(y) - 2):
            return {"applicable": False, "reason": "mínimo en el borde del dominio"}
        dx = (x[1] - x[0]) * NM
        dy = (y[1] - y[0]) * NM
        d2Vx = (V[iy, ix + 1] - 2 * V[iy, ix] + V[iy, ix - 1]) * EV / dx**2
        d2Vy = (V[iy + 1, ix] - 2 * V[iy, ix] + V[iy - 1, ix]) * EV / dy**2
        if d2Vx <= 0 or d2Vy <= 0:
            return {"applicable": False, "reason": "curvatura no positiva en el mínimo"}
        omegas = [np.sqrt(d2Vx / m), np.sqrt(d2Vy / m)]

    hbar_omega_meV = [round(float(HBAR * w / EV * 1000), 3) for w in omegas]
    E10 = round(float(energies_meV[1] - energies_meV[0]), 3)
    # En 2D el primer espaciado corresponde al ω menor (modo blando).
    ref = min(hbar_omega_meV)
    dev = round(abs(E10 - ref) / (abs(ref) + 1e-12) * 100, 1)
    return {
        "applicable": True,
        "hbar_omega_meV": hbar_omega_meV,
        "E1_minus_E0_meV": E10,
        "deviation_pct": dev,
        "interpretation": (
            "E1−E0 ≈ ħω → pozo casi armónico cerca del fondo."
            if dev < 10 else
            "Desviación >10% → anarmonicidad apreciable o estados que exploran "
            "más allá del fondo del pozo (normal en pozos finitos/anchos)."
        ),
    }


def _radial_profile(x: np.ndarray, y: np.ndarray, V: np.ndarray,
                    cx: float, cy: float):
    """Perfil radial promedio de V alrededor de (cx, cy)."""
    X, Y = np.meshgrid(x, y)
    R = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    r_max = float(R.max()) * 0.7  # ignora esquinas donde el potencial explota
    nbins = 40
    bins = np.linspace(0, r_max, nbins + 1)
    idx = np.digitize(R.ravel(), bins) - 1
    Vr = V.ravel()
    prof = np.full(nbins, np.nan)
    for b in range(nbins):
        sel = idx == b
        if sel.any():
            prof[b] = np.mean(Vr[sel])
    centers = 0.5 * (bins[:-1] + bins[1:])
    return centers, prof


def _is_ring_like(x: np.ndarray, y: np.ndarray, V: np.ndarray,
                  cx: float, cy: float, rtol: float = 0.10) -> bool:
    """Anillo: el mínimo del perfil radial cae en r>0, no en el centro."""
    centers, prof = _radial_profile(x, y, V, cx, cy)
    valid = np.isfinite(prof)
    if valid.sum() < 5:
        return False
    centers, prof = centers[valid], prof[valid]
    i_min = int(np.argmin(prof))
    # mínimo claramente fuera del centro y más bajo que el valor central
    return bool(centers[i_min] > rtol * centers[-1] and prof[i_min] < prof[0])


def _is_radially_symmetric(x: np.ndarray, y: np.ndarray, V: np.ndarray,
                           cx: float, cy: float, rtol: float = 0.08) -> bool:
    """Simetría radial: baja varianza angular de V dentro de cada anillo."""
    X, Y = np.meshgrid(x, y)
    R = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    r_max = float(R.max()) * 0.6
    span = float(np.nanmax(V) - np.nanmin(V)) + 1e-12
    bins = np.linspace(0.05 * r_max, r_max, 12)
    idx = np.digitize(R.ravel(), bins) - 1
    Vr = V.ravel()
    rel_stds = []
    for b in range(len(bins) - 1):
        sel = (idx == b) & np.isfinite(Vr)
        if sel.sum() > 8:
            rel_stds.append(np.std(Vr[sel]) / span)
    if not rel_stds:
        return False
    return bool(np.mean(rel_stds) < rtol)
