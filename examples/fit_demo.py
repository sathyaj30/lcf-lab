"""Fit the synthetic Mn project and save its analysis archive."""

from pathlib import Path

from lcf_lab import fit_batch
from lcf_lab.demo import demo_analysis
from lcf_lab.export import build_export

analysis = demo_analysis("Mn")
result = fit_batch(analysis)
with Path("mn-example.zip").open("xb") as archive:
    archive.write(build_export(analysis, result))
