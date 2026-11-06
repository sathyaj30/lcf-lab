"""Numerical and input-contract checks for the L-edge fitter."""

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from lcf_lab import engine
from lcf_lab.engine import fit_batch


@pytest.fixture
def project():
    energy = np.linspace(700.0, 735.0, 351)
    first = 0.11 + np.exp(-0.5 * ((energy - 708.3) / 0.8) ** 2)
    second = 0.13 + 0.8 * np.exp(-0.5 * ((energy - 710.0) / 1.15) ** 2)
    shared = {"element": "Fe", "edge": "L2,3"}
    return {
        "element": "Fe",
        "edge": "L2,3",
        "settings": {"fit_min": 704, "fit_max": 730, "max_shift": 0, "shift_step": 0.02, "sum_to_one": True},
        "samples": [{
            "id": "s1", "label": "Synthetic mixture", "energy": energy.tolist(),
            "signal": (0.37 * first + 0.63 * second).tolist(),
        }],
        "standards": [
            dict(shared, id="a", label="FeO", energy=energy.tolist(), signal=first.tolist(), valence=2),
            dict(shared, id="b", label="Fe₂O₃", energy=energy.tolist(), signal=second.tolist(), valence=3),
        ],
    }


def _fit(project):
    return fit_batch(project)["results"][0]


@pytest.mark.parametrize("element", ("Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn"))
def test_first_row_elements_share_a_fitter(project, element):
    project["element"] = element
    for standard in project["standards"]:
        standard["element"] = element
    result = _fit(project)
    assert result["status"] == "ok"
    np.testing.assert_allclose([item["weight"] for item in result["weights"]], [0.37, 0.63], atol=1e-6)
    assert result["nominal_valence"] == pytest.approx(2.63, abs=1e-6)
    assert result["rmse"] < 1e-7
    assert result["warnings"] == []


def test_constrained_fit_matches_analytic_optimum(project):
    """An amplitude mismatch separates the constrained fit from rescaled NNLS."""
    sample = project["samples"][0]
    observed = np.asarray(sample["signal"]) * 1.55
    sample["signal"] = observed.tolist()
    energy = np.asarray(sample["energy"])
    mask = (energy >= 704) & (energy <= 730)
    first, second = [np.asarray(item["signal"])[mask] for item in project["standards"]]
    difference = first - second
    optimum = np.clip((difference @ (observed[mask] - second)) / (difference @ difference), 0, 1)
    result = _fit(project)
    assert result["weights"][0]["weight"] == pytest.approx(optimum, abs=1e-7)
    np.testing.assert_allclose(result["residual"], observed[mask] - result["fitted"])
    assert result["rmse"] == pytest.approx(np.sqrt(np.mean(np.asarray(result["residual"]) ** 2)))


@pytest.mark.parametrize("offset", (0.12, -0.12, 0.13))
def test_offset_sign_endpoints_and_fixed_grid(project, offset):
    sample = project["samples"][0]
    energy = np.asarray(sample["energy"])
    sample["signal"] = np.interp(energy - offset, energy, sample["signal"]).tolist()
    project["settings"].update(max_shift=0.13, shift_step=0.02)
    result = _fit(project)
    assert result["energy_shift"] == pytest.approx(offset)
    assert result["energy"] == energy[(energy >= 704) & (energy <= 730)].tolist()
    assert result["coverage"] == pytest.approx([700.13, 734.87])
    assert result["rmse"] < 1e-7
    assert bool(result["warnings"]) == (offset == 0.13)


def test_unconstrained_fit_preserves_coefficients(project):
    project["settings"]["sum_to_one"] = False
    project["samples"][0]["signal"] = (1.6 * np.asarray(project["samples"][0]["signal"])).tolist()
    result = _fit(project)
    np.testing.assert_allclose([item["weight"] for item in result["weights"]], [1.6 * 0.37, 1.6 * 0.63])
    assert result["nominal_valence"] is None


def test_optional_valences_and_standard_inclusion(project):
    project["standards"][1]["valence"] = None
    assert _fit(project)["nominal_valence"] is None
    project["standards"][1]["included"] = False
    result = _fit(project)
    assert result["weights"] == [{"id": "a", "label": "FeO", "weight": 1.0, "valence": 2.0}]
    assert result["nominal_valence"] == 2.0


def test_zero_weight_standard_needs_no_valence(project):
    project["standards"][1]["valence"] = None
    project["samples"][0]["signal"] = project["standards"][0]["signal"][:]
    result = _fit(project)
    assert result["weights"][1]["weight"] == pytest.approx(0, abs=1e-8)
    assert result["nominal_valence"] == pytest.approx(2)


def test_ordered_output_from_descending_input(project):
    for spectrum in [*project["standards"], *project["samples"]]:
        spectrum["energy"].reverse()
        spectrum["signal"].reverse()
    result = _fit(project)
    assert result["energy"] == sorted(result["energy"])
    assert result["rmse"] < 1e-7


def test_signal_outside_the_fit_range_does_not_change_fit(project):
    baseline = _fit(project)
    project["standards"][0]["signal"][0] = 1e100
    project["standards"][1]["signal"][-1] = 1e120
    assert _fit(project) == baseline


@pytest.mark.parametrize("edge", ("L1", "L2", "L3"))
def test_single_edge_input(project, edge):
    project["edge"] = edge
    if edge == "L1":
        for standard in project["standards"]:
            standard["edge"] = "L1"
    assert _fit(project)["status"] == "ok"


@pytest.mark.parametrize("edge", ("K", "M"))
def test_scope_excludes_non_l_edges(project, edge):
    project["edge"] = edge
    with pytest.raises(ValueError, match="Choose L1"):
        fit_batch(project)


def test_independent_batch_rows_and_overlap(project):
    sample = project["samples"][0]
    short = {**sample, "id": "s2", "label": "Short", "energy": sample["energy"][90:180], "signal": sample["signal"][90:180]}
    disjoint = {**sample, "id": "s3", "label": "Disjoint", "energy": [1, 2, 3], "signal": [1, 1, 1]}
    project["samples"].extend([short, disjoint, None, {**sample, "label": "Duplicate"}])
    first, second, third, fourth, fifth = fit_batch(project)["results"]
    assert first["status"] == "ok"
    assert second["coverage"] == pytest.approx([709, 717.9])
    assert "exceeds shared coverage" in second["error"]
    assert "No shared energy range" in third["error"]
    assert "must be an object" in fourth["error"]
    assert "Duplicate sample ID" in fifth["error"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"signal": [1]}, "paired energy"),
        ({"signal": "invalid"}, "nonnumeric"),
        ({"energy": [1, 1, 3], "signal": [0, 1, 2]}, "duplicate"),
        ({"energy": [1, 2, 3], "signal": [0, np.nan, 1]}, "nonfinite"),
        ({"label": " "}, "Sample label"),
    ],
)
def test_invalid_samples_are_reported_per_row(project, change, message):
    project["samples"][0].update(change)
    result = _fit(project)
    assert result["status"] == "error"
    assert message in result["error"]


def test_too_few_fit_points(project):
    project["settings"].update(fit_min=709.0, fit_max=709.1)
    assert "too few sample points" in _fit(project)["error"]


def test_coverage_checks_offsets_at_both_bounds(project):
    project["settings"].update(fit_min=700.1, fit_max=734.9, max_shift=0.5)
    result = _fit(project)
    assert result["coverage"] == [700.5, 734.5]
    assert "exceeds shared coverage" in result["error"]


@pytest.mark.parametrize(("blank", "warning"), [(False, "dependent shapes"), (True, "zero signal")])
def test_diagnostics_for_unresolvable_references(project, blank, warning):
    first, second = project["standards"]
    second["signal"] = [0] * len(first["signal"]) if blank else first["signal"][:]
    project["samples"][0]["signal"] = first["signal"][:]
    assert any(warning in item for item in _fit(project)["warnings"])


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"fit_min": None}, "finite"),
        ({"fit_min": True}, "finite"),
        ({"fit_max": np.inf}, "finite"),
        ({"fit_min": 740}, "below fit end"),
        ({"max_shift": -1}, "nonnegative"),
        ({"shift_step": 0}, "positive"),
        ({"max_shift": 30, "shift_step": 0.001}, "coarser"),
        ({"sum_to_one": "yes"}, "boolean"),
    ],
)
def test_invalid_settings_are_project_errors(project, change, message):
    project["settings"].update(change)
    with pytest.raises(ValueError, match=message):
        fit_batch(project)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"id": "a"}, "Duplicate standard ID"),
        ({"element": "Ni"}, "incompatible"),
        ({"edge": "L1"}, "incompatible"),
        ({"edge": []}, "incompatible"),
        ({"included": 1}, "boolean"),
        ({"valence": np.inf}, "finite"),
    ],
)
def test_invalid_included_standards_are_project_errors(project, change, message):
    project["standards"][1].update(change)
    with pytest.raises(ValueError, match=message):
        fit_batch(project)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"element": "Al"}, "Sc through Zn"),
        ({"standards": {}}, "Standards must be a list"),
        ({"standards": [None]}, "Each standard must be an object"),
        ({"standards": []}, "at least one reference"),
        ({"samples": []}, "at least one sample"),
        ({"settings": []}, "Fit settings must be an object"),
    ],
)
def test_invalid_project_structure(project, change, message):
    with pytest.raises(ValueError, match=message):
        fit_batch({**project, **change})


def test_batch_fits_are_deterministic_and_leave_inputs_intact(project):
    original = deepcopy(project)
    assert fit_batch(project) == fit_batch(project)
    assert project == original
    with pytest.raises(ValueError, match="must be an object"):
        fit_batch(None)


def test_failed_solver_returns_a_sample_error(project, monkeypatch):
    monkeypatch.setattr(engine, "minimize", lambda *args, **kwargs: SimpleNamespace(success=False, x=np.zeros(2)))
    result = _fit(project)
    assert result["status"] == "error"
    assert "No energy-offset trial" in result["error"]


def test_incompatible_numerical_range_is_reported(project):
    project["standards"] = project["standards"][:1]
    project["standards"][0]["signal"] = [-1e308] * 351
    project["samples"][0]["signal"] = [1e308] * 351
    result = _fit(project)
    assert result["status"] == "error"
    assert "supported numerical range" in result["error"]
