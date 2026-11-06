"""Reference-based linear-combination fitting of normalized soft X-ray spectra."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil, isfinite

import numpy as np
from scipy.optimize import minimize, nnls


ELEMENTS = ("Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn")
EDGES = ("L1", "L2", "L3", "L2,3")
MAX_SHIFT_TRIALS = 1001


@dataclass(frozen=True)
class _Settings:
    fit_min: float
    fit_max: float
    max_shift: float
    shift_step: float
    sum_to_one: bool


@dataclass(frozen=True)
class _Spectrum:
    energy: np.ndarray
    signal: np.ndarray


@dataclass(frozen=True)
class _Reference:
    id: str
    label: str
    valence: float | None
    spectrum: _Spectrum


def _number(value, label: str) -> float:
    try:
        if isinstance(value, (bool, np.bool_)):
            raise TypeError
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number.") from exc
    if not isfinite(number):
        raise ValueError(f"{label} must be a finite number.")
    return number


def _identifier(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string.")
    return value.strip()


def _spectrum(data: dict, label: str) -> _Spectrum:
    try:
        energy = np.asarray(data.get("energy"), dtype=float)
        signal = np.asarray(data.get("signal"), dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} contains nonnumeric spectrum data.") from exc
    if energy.ndim != 1 or signal.shape != energy.shape or energy.size < 3:
        raise ValueError(f"{label} needs at least three paired energy and signal values.")
    if not np.all(np.isfinite(energy)) or not np.all(np.isfinite(signal)):
        raise ValueError(f"{label} contains nonfinite spectrum data.")
    order = np.argsort(energy, kind="stable")
    energy, signal = energy[order], signal[order]
    if np.any(energy[1:] <= energy[:-1]):
        raise ValueError(f"{label} contains duplicate energy values.")
    return _Spectrum(energy, signal)


def _settings(data) -> _Settings:
    if not isinstance(data, dict):
        raise ValueError("Fit settings must be an object.")
    lo = _number(data.get("fit_min"), "Fit start")
    hi = _number(data.get("fit_max"), "Fit end")
    if lo >= hi:
        raise ValueError("Fit start must be below fit end.")
    limit = _number(data.get("max_shift", 0), "Maximum energy offset")
    step = _number(data.get("shift_step", 0.02), "Energy offset step")
    if limit < 0 or step <= 0:
        raise ValueError("Use a nonnegative maximum offset and a positive offset step.")
    ratio = limit / step
    if not isfinite(ratio) or 2 * ceil(ratio) + 1 > MAX_SHIFT_TRIALS:
        raise ValueError(f"Choose a coarser offset step (maximum {MAX_SHIFT_TRIALS} trials).")
    constrained = data.get("sum_to_one", True)
    if not isinstance(constrained, bool):
        raise ValueError("Sum-to-one selection must be a boolean.")
    return _Settings(lo, hi, limit, step, constrained)


def _references(data, element: str, edge: str) -> list[_Reference]:
    if not isinstance(data, list):
        raise ValueError("Standards must be a list.")
    references = []
    used_ids = set()
    compatible_edges = {edge, "L2,3"} if edge in {"L2", "L3"} else {edge}
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Each standard must be an object.")
        included = item.get("included", True)
        if not isinstance(included, bool):
            raise ValueError("Standard inclusion must be a boolean.")
        if not included:
            continue
        key = _identifier(item.get("id"), "Standard ID")
        label = _identifier(item.get("label"), "Standard label")
        if key in used_ids:
            raise ValueError(f"Duplicate standard ID: {key}.")
        reference_edge = item.get("edge")
        if (
            item.get("element") != element
            or not isinstance(reference_edge, str)
            or reference_edge not in compatible_edges
        ):
            raise ValueError(f"Standard {label} is incompatible with {element} {edge}.")
        valence = item.get("valence")
        if valence is not None:
            valence = _number(valence, f"Nominal oxidation state of {label}")
        references.append(_Reference(key, label, valence, _spectrum(item, label)))
        used_ids.add(key)
    if not references:
        raise ValueError("Include at least one reference standard.")
    return references


def _shifts(settings: _Settings) -> list[float]:
    """Return zero, both bounds, and intermediate offsets at the requested step."""
    if settings.max_shift == 0:
        return [0.0]
    limit, step = settings.max_shift, settings.shift_step
    positive = [step * index for index in range(1, ceil(limit / step)) if step * index < limit]
    positive.append(limit)
    return [0.0, *(offset for value in positive for offset in (-value, value))]


def _coverage(sample: _Spectrum, references: list[_Reference], limit: float) -> tuple[float, float]:
    lo = max(float(sample.energy[0]), max(float(ref.spectrum.energy[0]) + limit for ref in references))
    hi = min(float(sample.energy[-1]), min(float(ref.spectrum.energy[-1]) - limit for ref in references))
    return lo, hi


def _weights(matrix: np.ndarray, observed: np.ndarray, sum_to_one: bool) -> np.ndarray:
    count = matrix.shape[1]
    if not sum_to_one:
        try:
            return nnls(matrix, observed)[0]
        except RuntimeError as exc:
            raise ValueError("The nonnegative least-squares solver did not converge.") from exc
    if count == 1:
        return np.ones(1)

    def objective(weights):
        difference = matrix @ weights - observed
        return (
            0.5 * float(difference @ difference) / observed.size,
            (matrix.T @ difference) / observed.size,
        )

    solved = minimize(
        objective,
        np.full(count, 1.0 / count),
        method="SLSQP",
        jac=True,
        bounds=[(0.0, 1.0)] * count,
        constraints=[{
            "type": "eq",
            "fun": lambda w: float(w.sum() - 1.0),
            "jac": lambda w: np.ones_like(w),
        }],
        options={"ftol": 1e-13, "maxiter": 200},
    )
    weights = solved.x
    if (
        not solved.success
        or not np.all(np.isfinite(weights))
        or np.min(weights) < -1e-8
        or abs(float(weights.sum()) - 1.0) > 1e-8
    ):
        raise ValueError("The sum-to-one least-squares solver did not converge.")
    # Remove roundoff from the constrained solution without changing its model.
    weights = np.maximum(weights, 0.0)
    return weights / weights.sum()


def _stability_warnings(matrix: np.ndarray) -> list[str]:
    norms = np.linalg.norm(matrix, axis=0)
    if np.any(norms == 0):
        return ["An included standard has zero signal in the fit window. Its weight may be unidentifiable."]
    singular_values = np.linalg.svd(matrix / norms, compute_uv=False)
    if singular_values[-1] < 1e-3 * singular_values[0]:
        return ["Included standards have nearly dependent shapes. Individual weights may be poorly resolved."]
    return []


def _fit_sample(
    sample: _Spectrum,
    references: list[_Reference],
    settings: _Settings,
    shifts: list[float],
    coverage: tuple[float, float],
) -> dict:
    lo, hi = coverage
    if not lo < hi:
        raise ValueError("No shared energy range remains for the requested offset scan.")
    if settings.fit_min < lo - 1e-9 or settings.fit_max > hi + 1e-9:
        raise ValueError(f"The fit window exceeds shared coverage ({lo:.3f} to {hi:.3f} eV).")
    mask = (sample.energy >= settings.fit_min) & (sample.energy <= settings.fit_max)
    energy, observed = sample.energy[mask], sample.signal[mask]
    if energy.size < max(3, len(references) + 1):
        raise ValueError("The fitting window has too few sample points for the selected standards.")

    # One common scale preserves relative intensities and trial ranking. Points
    # outside the fitted range and its offset margin cannot set that scale.
    scan_lo, scan_hi = energy[0] - settings.max_shift, energy[-1] + settings.max_shift
    scale = float(np.max(np.abs(observed)))
    for ref in references:
        reference = ref.spectrum
        start, end = np.searchsorted(reference.energy, [scan_lo, scan_hi])
        endpoints = np.interp([scan_lo, scan_hi], reference.energy, reference.signal)
        scale = max(
            scale,
            float(np.max(np.abs(reference.signal[start:end]), initial=0)),
            float(np.max(np.abs(endpoints))),
        )
    scale = scale or 1.0
    normalized_observed = observed / scale
    best = None
    for shift in shifts:
        matrix = np.column_stack([
            np.interp(energy - shift, ref.spectrum.energy, ref.spectrum.signal)
            for ref in references
        ]) / scale
        try:
            weights = _weights(matrix, normalized_observed, settings.sum_to_one)
        except ValueError:
            continue
        normalized_fit = matrix @ weights
        residual = normalized_observed - normalized_fit
        loss = float(np.mean(residual ** 2))
        if not isfinite(loss):
            continue
        if best is None or loss < best[0] - 1e-14 * max(loss, best[0], 1e-12):
            best = (loss, shift, matrix, weights, normalized_fit, residual)
    if best is None:
        raise ValueError("No energy-offset trial produced a converged finite fit.")

    loss, shift, matrix, weights, normalized_fit, residual = best
    with np.errstate(over="ignore"):
        fitted = normalized_fit * scale
        residual = residual * scale
        rmse = float(np.sqrt(loss) * scale)
    if not np.all(np.isfinite(fitted)) or not np.all(np.isfinite(residual)) or not isfinite(rmse):
        raise ValueError("The fitted signal exceeds the supported numerical range.")
    warnings = _stability_warnings(matrix)
    if settings.max_shift and abs(shift) == settings.max_shift:
        warnings.append("The best energy offset is at the requested limit.")
    terms = [(float(weight), ref.valence) for ref, weight in zip(references, weights) if weight > 1e-8]
    nominal = None
    if settings.sum_to_one and all(valence is not None for _, valence in terms):
        nominal = sum(weight * valence for weight, valence in terms) / sum(weight for weight, _ in terms)
        if not isfinite(nominal):
            nominal = None
    return {
        "energy": energy.tolist(),
        "observed": observed.tolist(),
        "fitted": fitted.tolist(),
        "residual": residual.tolist(),
        "weights": [
            {"id": ref.id, "label": ref.label, "weight": float(weight), "valence": ref.valence}
            for ref, weight in zip(references, weights)
        ],
        "nominal_valence": nominal,
        "energy_shift": shift,
        "rmse": rmse,
        "warnings": warnings,
    }


def fit_batch(payload: dict) -> dict:
    """Fit one or more normalized spectra against the selected reference standards.

    Supply a first-row 3d element, L-edge, fit settings, samples, and standards.
    Each spectrum contains paired energy (eV) and signal arrays.
    Positive offsets move the references to higher energy. Every offset is
    compared over the same measured sample points, without extrapolation.
    Invalid project settings or references raise ValueError. Invalid sample
    spectra and failed fits appear as individual result rows with status "error".
    Fitted weights describe the supplied reference model. A nominal mean
    oxidation state is reported only for a sum-to-one fit with known states for
    its contributing standards.
    """
    if not isinstance(payload, dict):
        raise ValueError("An analysis request must be an object.")
    element, edge = payload.get("element"), payload.get("edge")
    if element not in ELEMENTS:
        raise ValueError("Choose an element from Sc through Zn.")
    if edge not in EDGES:
        raise ValueError("Choose L1, L2, L3, or L2,3.")
    settings = _settings(payload.get("settings"))
    references = _references(payload.get("standards"), element, edge)
    samples = payload.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("Supply at least one sample spectrum.")

    shifts = _shifts(settings)
    results = []
    used_ids = set()
    for index, item in enumerate(samples, start=1):
        fallback = f"Sample {index}"
        result = {"sample_id": f"sample-{index}", "label": fallback}
        try:
            if not isinstance(item, dict):
                raise ValueError("Each sample must be an object.")
            key = _identifier(item.get("id"), "Sample ID")
            result["sample_id"] = key
            result["label"] = _identifier(item.get("label"), "Sample label")
            if key in used_ids:
                raise ValueError(f"Duplicate sample ID: {key}.")
            used_ids.add(key)
            sample = _spectrum(item, result["label"])
            coverage = _coverage(sample, references, settings.max_shift)
            if all(isfinite(value) for value in coverage) and coverage[0] < coverage[1]:
                result["coverage"] = list(coverage)
            result.update(_fit_sample(sample, references, settings, shifts, coverage))
            result["status"] = "ok"
        except (ValueError, np.linalg.LinAlgError) as exc:
            result.update(status="error", error=str(exc))
        results.append(result)
    return {"element": element, "edge": edge, "settings": asdict(settings), "results": results}
