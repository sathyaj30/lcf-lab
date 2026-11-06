"""Convert the Villalobos, Páez Fajardo and NIMS reference traces."""

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from zipfile import ZipFile


CC_BY = "https://creativecommons.org/licenses/by/4.0/"
VILLALOBOS = {
    "citation": "Villalobos et al. (2022), Stabilization of a Mn-Co oxide during oxygen evolution in alkaline media.",
    "dataset_doi": "10.6084/m9.figshare.18415520.v1",
    "paper_doi": "10.1002/celc.202200482",
    "license": "CC-BY-4.0",
    "license_url": CC_BY,
}
PAEZ = {
    "citation": "Páez Fajardo et al. (2026), Direct evidence of metal-ligand redox in Li-ion battery cathodes.",
    "dataset_doi": "10.6084/m9.figshare.28915994.v1",
    "paper_doi": "10.1038/s41565-026-02189-y",
    "license": "CC-BY-4.0",
    "license_url": CC_BY,
}

# Reference labels and zero-based energy-column indexes in the source tables.
MN_TRACES = (
    ("Mn3O4", "Mn3O4", 5, None, [2, 3], 174),
    ("MnO2", "MnO2", 7, 4, None, 173),
    ("Mn2O3", "Mn2O3", 9, 3, None, 398),
    ("MnSO4-hydrate", "MnSO4", 11, 2, None, 399),
)
CO_TRACES = (
    ("LiCoO2", "LiCoO2", 9, 3, None, 348),
    ("CoNO3-hexahydrate", "Co(NO3)2", 11, 2, None, 349),
    ("CoO", "CoO", 13, 2, None, 347),
    ("Co3O4", "Co3O4", 15, None, [2, 3], 348),
)
NI_TRACES = (
    ("LaNiO2", 1),
    ("NiO", 2),
    ("LiNiO2", 3),
    ("Li2NiO3", 4),
)
FORMULA = {
    "CoNO3-hexahydrate": "Co(NO3)2·6H2O",
    "MnSO4-hydrate": "MnSO4·xH2O",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_villalobos(path, element, figure, url, traces):
    raw = path.read_bytes()
    rows = list(csv.reader(io.StringIO(raw.decode("cp1252")), delimiter=";"))
    for slug, label, column, valence, mixed_valences, expected_points in traces:
        if rows[5][column + 1] != label or rows[6][column:column + 2] != ["Energy", "Normalized intensity"]:
            raise ValueError(f"Unexpected Figure {figure} header for {label}")
        points = []
        for row in rows[8:]:
            if not row or not any(row[column:column + 2]):
                continue
            energy, signal = row[column:column + 2]
            points.append((energy.strip(), signal.strip()))
        source = {
            **VILLALOBOS,
            "download_url": url,
            "source_file_sha256": sha256(raw),
            "source_file": f"Figure {figure}.csv",
            "figure": figure,
            "trace": label,
            "energy_column_1_based": column + 1,
            "signal_column_1_based": column + 2,
            "facility": "BESSY II (Helmholtz-Zentrum Berlin)",
        }
        if element == "Mn":
            source["beamline_note"] = "LiXEdrom at UE56/2 PGM-2 or U49-2 PGM-1. Per-trace beamline unspecified."
            source["energy_calibration"] = "MnSO4 L3 peak assigned to 641 eV."
        yield element, slug, valence, mixed_valences, expected_points, points, source


def read_paez(path):
    raw = path.read_bytes()
    with ZipFile(io.BytesIO(raw)) as archive:
        for formula, valence in NI_TRACES:
            member = f"Supporting_Data/Fig3/a_ExpNiLedge_{formula}_Ni{valence}.txt"
            contents = archive.read(member)
            header, *lines = contents.decode("utf-8-sig").strip().splitlines()
            if len(header.split()) != 2 or not header.startswith("Energy") or "Data_Norm" not in header:
                raise ValueError(f"Unexpected Figure 3a header for {formula}")
            points = [line.split() for line in lines if line.strip()]
            source = {
                **PAEZ,
                "download_url": "https://ndownloader.figshare.com/files/58424281",
                "archive_sha256": sha256(raw),
                "source_file": member,
                "source_file_sha256": sha256(contents),
                "figure": "3a",
                "trace": f"{formula}, formal Ni({valence}+)",
                "energy_column_1_based": 1,
                "signal_column_1_based": 2,
            }
            yield "Ni", formula, valence, None, 351, points, source


def stage_trace(trace):
    element, slug, valence, mixed_valences, expected_points, points, source = trace
    pairs = [(float(energy), float(signal)) for energy, signal in points]
    if len(pairs) != expected_points or not all(math.isfinite(value) for pair in pairs for value in pair):
        raise ValueError(f"Unexpected point count or non-finite values for {slug}")
    processing = "Source energy and intensity columns extracted."
    sorted_pairs = sorted(pairs)
    if pairs != sorted_pairs:
        processing += " Paired values sorted by increasing energy."
    processing += " No rescaling, interpolation or alignment."
    energies = [energy for energy, _ in sorted_pairs]
    if any(after <= before for before, after in zip(energies, energies[1:])):
        raise ValueError(f"Energy grid is not strictly increasing for {slug}")
    label = FORMULA.get(slug, slug)
    return {
        "id": f"{element.lower()}-{slug.lower()}",
        "label": label,
        "element": element,
        "edge": "L2,3",
        "formula": label,
        "kind": "measured_reference",
        "detection_mode": "TEY",
        "valence": valence,
        "mixed_nominal_valences": mixed_valences,
        "energy": energies,
        "signal": [signal for _, signal in sorted_pairs],
        "signal_type": "Author-normalized total electron yield",
        "processing": processing,
        "points": len(pairs),
        "energy_min_ev": energies[0],
        "energy_max_ev": energies[-1],
        "source_file": source["source_file"],
        "provenance": (
            f'{source["citation"]} Figure {source["figure"]}, trace {source["trace"]}. '
            f'Dataset DOI {source["dataset_doi"]}.'
        ),
        "source_url": f'https://doi.org/{source["dataset_doi"]}',
        "license": source["license"],
        "source": source,
    }


def read_nims_cuo(tey_path, metadata_path):
    raw = tey_path.read_bytes()
    raw_metadata = metadata_path.read_bytes()
    metadata = json.loads(raw_metadata)
    calibration, = metadata["measurement"]["energy_calibration"]
    data_format = next(item for item in metadata["file"]["processed_data_format"] if item["extension"] == "tey")
    energy_column, signal_column = data_format["columns"]
    if metadata["sample"]["chemical_formula"] != "CuO" or energy_column["unit"] != "eV":
        raise ValueError("Expected CuO and photon energies in eV")
    if signal_column["name"] != "Normalized Ie/I0 (TEY)" or calibration["energy"] != 931.1:
        raise ValueError("Unexpected TEY signal or energy calibration")

    points = [line.split() for line in raw.decode("ascii").splitlines() if line.strip()]
    if not 910 < float(points[0][0]) < 911 or not 1004 < float(points[-1][0]) < 1005:
        raise ValueError("Expected the archived Cu L2,3 energy range")
    source = {
        "citation": "Masashi Ishii (editor), Ritsumeikan SR Center (author). XAFS spectrum of Copper(II) oxide.",
        "dataset_doi": "10.48505/nims.3336",
        "license": "CC-BY-4.0",
        "license_url": CC_BY,
        "download_url": "https://mdr.nims.go.jp/filesets/e8785702-6956-4677-92ce-ecab81ff90d8/download",
        "source_file": "21032604.tey",
        "source_file_sha256": sha256(raw),
        "metadata_download_url": "https://mdr.nims.go.jp/filesets/9ddc653c-1524-4d19-a95f-e30d14051864/download",
        "metadata_sha256": sha256(raw_metadata),
        "figure": "BL11_Cu-L_001_tey.png",
        "trace": "21032604 CuO normalized TEY",
        "energy_column_1_based": 1,
        "signal_column_1_based": 2,
        "facility": "Ritsumeikan SR Center, BL-11",
        "measured_at": "2021-03-26T16:59:56+09:00",
        "energy_calibration": calibration,
        "signal_processing": signal_column["normalizing_process"],
        "edge_coverage_note": "Repository lists Cu L3. The measured 910.9065–1004.136 eV range contains both L3 and L2 peaks.",
    }
    entry = stage_trace(("Cu", "CuO", 2, None, 376, points, source))
    entry["id"] = "nims-3336-cuo-tey"
    entry["signal_type"] = "Source-normalized electron yield (Ie/I0)"
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mn", type=Path, required=True, help="Villalobos Figure 6b CSV")
    parser.add_argument("--co", type=Path, required=True, help="Villalobos Figure 6a CSV")
    parser.add_argument("--ni", type=Path, required=True, help="Páez Fajardo Supporting_Data.zip")
    parser.add_argument("--cu", type=Path, required=True, help="NIMS CuO 21032604.tey")
    parser.add_argument("--cu-metadata", type=Path, required=True, help="NIMS CuO metadata.json")
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("public-mn-co-ni-cu-tey.json"))
    options = parser.parse_args()
    traces = [
        *read_villalobos(options.mn, "Mn", "6b", "https://ndownloader.figshare.com/files/35574467", MN_TRACES),
        *read_villalobos(options.co, "Co", "6a", "https://ndownloader.figshare.com/files/35574470", CO_TRACES),
        *read_paez(options.ni),
    ]
    records = [stage_trace(trace) for trace in traces]
    records.append(read_nims_cuo(options.cu, options.cu_metadata))
    manifest = {
        "schema_version": 1,
        "id": "public-mn-co-ni-cu-tey",
        "version": "1.1.0",
        "label": "Published Mn, Co, Ni and Cu L-edge TEY standards",
        "standards": records,
    }
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Staged {len(records)} measured reference spectra.")


if __name__ == "__main__":
    main()
