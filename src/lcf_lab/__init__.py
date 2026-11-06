"""Batch linear-combination fitting for soft X-ray absorption spectra."""

from importlib.metadata import PackageNotFoundError, version

from .engine import fit_batch

try:
    __version__ = version("lcf-lab")
except PackageNotFoundError:
    __version__ = "0+source"

__all__ = ["fit_batch", "__version__"]
