"""Write analysis inputs and results as a reproducible ZIP archive."""

import csv
import io
import json
import re
from zipfile import ZIP_DEFLATED, ZipFile

from . import __version__


def _json(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def _csv(headers, rows) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue()


def _label(value: object) -> str:
    """Keep a label as text when the CSV is opened in a spreadsheet."""
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def build_export(analysis: dict, result: dict) -> bytes:
    """Bundle the exact fit request, structured results, and plot data.

    The original input labels and data are preserved in JSON. The CSV files
    are convenient views of the same results.
    """
    if not isinstance(analysis, dict) or not isinstance(result, dict) or not isinstance(result.get("results"), list):
        raise ValueError("Export requires an analysis request and its fit results.")

    rows = []
    weights = []
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("analysis.json", _json(analysis))
        archive.writestr("results.json", _json({"format_version": 1, "software_version": __version__, **result}))
        for index, sample in enumerate(result["results"], 1):
            label = str(sample["label"])
            sample_id = str(sample["sample_id"])
            rows.append((
                _label(sample_id), _label(label), sample["status"], sample.get("nominal_valence"),
                sample.get("energy_shift"), sample.get("rmse"), _label(sample.get("error", "")),
                _label(" | ".join(sample.get("warnings", []))),
            ))
            if sample["status"] != "ok":
                continue
            for ref in sample["weights"]:
                weights.append((_label(sample_id), _label(ref["id"]), _label(ref["label"]),
                                ref["weight"], ref["valence"]))
            slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("._-")[:70] or "sample"
            curves = zip(sample["energy"], sample["observed"], sample["fitted"],
                         sample["residual"], strict=True)
            archive.writestr(f"curves/{index:03d}_{slug}.csv",
                             _csv(("energy_eV", "observed", "fitted", "residual"), curves))
        archive.writestr("summary.csv", _csv(
            ("sample_id", "sample", "status", "nominal_mean_oxidation_state",
             "energy_shift_eV", "rmse", "error", "warnings"), rows,
        ))
        archive.writestr("reference_weights.csv", _csv(
            ("sample_id", "reference_id", "reference", "weight", "nominal_oxidation_state"), weights,
        ))
    return buffer.getvalue()
