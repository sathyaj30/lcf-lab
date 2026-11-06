"""Generate deterministic synthetic spectra for the tutorials."""

import numpy as np

_EXAMPLES = {
    "Fe": (700, 735, 709.1, 13.1, (705, 730), (708, 723),
           ("FeO", "Fe2O3", "Fe3O4"), (2, 3, 8 / 3)),
    "Mn": (632, 665, 642.0, 11.0, (637, 660), (641, 656),
           ("MnO", "MnO2", "Mn3O4"), (2, 4, 8 / 3)),
}


def demo_analysis(element: str = "Fe", edge: str = "L2,3") -> dict:
    """Return a complete fit request with analytic reference and sample spectra.

    The line shapes illustrate the software. They are generated examples and
    should not be used as experimental standards.
    """
    if element not in _EXAMPLES:
        raise ValueError("Synthetic projects are available for Fe and Mn.")
    if edge not in {"L2,3", "L2", "L3"}:
        raise ValueError("Synthetic projects cover L2, L3, and L2,3.")
    lo, hi, center, split, bounds, short, names, valences = _EXAMPLES[element]

    def reference(energy, index):
        l3 = center + (-0.55, 0.65, 0.14)[index]
        l2 = l3 + split

        def peak(position, width):
            return np.exp(-0.5 * ((energy - position) / width) ** 2)

        return (0.045 + 0.13 / (1 + np.exp(-(energy - l3) / 2))
                + (1.05, 0.97, 0.97)[index] * peak(l3, 0.66)
                + (0.22, 0.45, 0.34)[index] * peak(l3 + 1.9, 1.05)
                + 0.43 * peak(l2, 0.92) + 0.16 * peak(l2 + 1.8, 1.25))

    reference_grid = np.linspace(lo, hi, 351)
    standards = [
        {"id": f"ref{index + 1}", "label": label, "element": element, "edge": "L2,3",
         "valence": valence, "included": True, "energy": reference_grid.tolist(),
         "signal": reference(reference_grid, index).tolist(),
         "provenance": "Analytic synthetic example"}
        for index, (label, valence) in enumerate(zip(names, valences, strict=True))
    ]
    if edge == "L3":
        bounds = (bounds[0], round(center + 5, 2))
    if edge == "L2":
        bounds = (round(center + split - 4, 2), bounds[1])
    samples = []
    rows = [
        ("Scan 01", (0.36, 0.64, 0), 0.12, (lo, hi)),
        ("Scan 02", (0.25, 0.69, 0.06), -0.08, (lo, hi)),
        ("Scan 03", (0.12, 0.76, 0.12), 0.04, (lo, hi)),
        ("Short scan", (0.41, 0.59, 0), 0.10, short),
    ]
    for index, (label, weights, offset, interval) in enumerate(rows):
        energy = np.linspace(*interval, 251)
        signal = sum(weight * reference(energy - offset, i) for i, weight in enumerate(weights))
        signal += 0.004 * np.sin(energy * 4.3 + index) + 0.002 * np.sin(energy * 8.1 - index)
        samples.append({"id": f"sample{index + 1}", "label": label, "energy": energy.tolist(),
                        "signal": signal.tolist(), "provenance": "Analytic synthetic example"})
    return {
        "element": element, "edge": edge, "dataset": "Synthetic demonstration",
        "settings": {"fit_min": bounds[0], "fit_max": bounds[1], "max_shift": 0.30,
                     "shift_step": 0.02, "sum_to_one": True},
        "samples": samples, "standards": standards,
    }
