"""Compare measured Ni L-edge fits with XrayLarch.

Páez Fajardo et al. published the Ni archive under CC BY 4.0 at
https://doi.org/10.6084/m9.figshare.28915994.v1. The accompanying article is
available at https://doi.org/10.1038/s41565-026-02189-y.
The benchmark compares fitted weights for the same empirical endmembers.
"""

import argparse
import hashlib
import io
import json
from importlib.metadata import version
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from scipy.integrate import trapezoid

from lcf_lab.engine import fit_batch

NI_FOLDER = (
    "Supporting_Data/Fig5/RawData/"
    "Ni_Ledge_Diamond_B07_Jul2023_S33459-1"
)
NI_ARCHIVE_MD5 = "4cb24ee8ad18e63004a2d701008eeb90"
EDGE = "L2,3"


def spectrum(identifier, label, energy, signal):
    return {
        "id": identifier,
        "label": label,
        "energy": energy.tolist(),
        "signal": signal.tolist(),
    }


def standard(identifier, label, energy, signal, element):
    return {
        **spectrum(identifier, label, energy, signal),
        "element": element,
        "edge": EDGE,
        "valence": None,
        "included": True,
    }


def payload(element, samples, standards, window):
    return {
        "element": element,
        "edge": EDGE,
        "settings": {
            "fit_min": window[0],
            "fit_max": window[1],
            "max_shift": 0,
            "shift_step": 0.01,
            "sum_to_one": True,
        },
        "samples": samples,
        "standards": standards,
    }


def measured_ni_scan(archive, scan):
    name = f"{NI_FOLDER}/b07-{scan}TEY.txt"
    raw = archive.read(name).decode()
    if "#Energy\tTEYData_Norm" not in raw:
        raise ValueError(f"Unexpected acquisition columns in {name}.")
    energy, signal = np.loadtxt(io.StringIO(raw), unpack=True)
    if np.any(np.diff(energy) <= 0):
        raise ValueError(f"Unexpected energy order in {name}.")
    # Apply the same baseline and unit-area scaling to every recorded scan.
    pre_edge = (energy >= 846.0) & (energy <= 849.0)
    signal -= np.mean(signal[pre_edge])
    middle = energy[(energy > 850.0) & (energy < 878.0)]
    area_grid = np.concatenate(([850.0], middle, [878.0]))
    area = trapezoid(np.interp(area_grid, energy, signal), area_grid)
    if not np.isfinite(area) or area <= 0:
        raise ValueError(f"Cannot normalize {name} to a positive area.")
    return energy, signal / area


def benchmark_ni(archive_path):
    from larch import Group
    from larch.math.lincombo_fitting import lincombo_fit

    checksum = hashlib.md5(archive_path.read_bytes(), usedforsecurity=False).hexdigest()
    if checksum != NI_ARCHIVE_MD5:
        raise ValueError("The supplied archive does not match Figshare file 58424281.")
    reference_scans = ("48082", "48077")
    target_scans = ("48074", "48075", "48076")
    with ZipFile(archive_path) as archive:
        standards = [
            standard(scan, f"B07 TEY endmember {scan}", *measured_ni_scan(archive, scan), "Ni")
            for scan in reference_scans
        ]
        samples = [
            spectrum(scan, f"B07 TEY scan {scan}", *measured_ni_scan(archive, scan))
            for scan in target_scans
        ]
    analysis = payload("Ni", samples, standards, (850.0, 878.0))
    compared = []
    for result in fit_batch(analysis)["results"]:
        if result["status"] != "ok":
            raise RuntimeError(result["error"])
        # The zero-offset comparison supplies the same interpolated matrix and
        # measured observations to both solvers to isolate weight optimization.
        grid = np.asarray(result["energy"])
        observed = np.asarray(result["observed"])
        groups = [
            Group(
                label=ref["id"],
                energy=grid,
                norm=np.interp(grid, ref["energy"], ref["signal"]),
            )
            for ref in standards
        ]
        larch_fit = lincombo_fit(
            Group(energy=grid, norm=observed),
            groups,
            weights=[0.5, 0.5],
            minvals=[0.0, 0.0],
            maxvals=[1.0, 1.0],
            sum_to_one=True,
        )
        ours = [entry["weight"] for entry in result["weights"]]
        other = [larch_fit.weights[scan] for scan in reference_scans]
        weight_delta = float(np.max(np.abs(np.asarray(ours) - other)))
        curve_delta = float(np.max(np.abs(np.asarray(result["fitted"]) - larch_fit.yfit)))
        if weight_delta > 2e-5 or curve_delta > 2e-6:
            raise AssertionError(f"LCF Lab and XrayLarch disagree on scan {result['sample_id']}.")
        compared.append(
            {
                "target_scan": result["sample_id"],
                "points": len(grid),
                "lcf_lab_weights": ours,
                "xraylarch_weights": other,
                "max_weight_delta": weight_delta,
                "max_fitted_signal_delta": curve_delta,
                "lcf_lab_rmse": result["rmse"],
                "xraylarch_rmse": float(np.sqrt(np.mean((observed - larch_fit.yfit) ** 2))),
            }
        )
    return {
        "source": "https://doi.org/10.6084/m9.figshare.28915994.v1",
        "license": "CC BY 4.0",
        "acquisition": "Diamond B07, Ni L-edge TEY, session SI33459-1",
        "reference_scans": reference_scans,
        "fit_range_eV": [850.0, 878.0],
        "energy_offset_eV": 0.0,
        "preprocessing": "846–849 eV mean subtraction and 850–878 eV unit area",
        "comparator": f"XrayLarch {version('xraylarch')}",
        "targets": compared,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ni-archive", type=Path, required=True, help="Path to Figshare Supporting_Data.zip.")
    parser.add_argument("--output", type=Path, help="Write the metrics to this JSON path.")
    args = parser.parse_args()
    results = {"measured_ni": benchmark_ni(args.ni_archive)}
    report = json.dumps(results, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    print(report, end="")


if __name__ == "__main__":
    main()
