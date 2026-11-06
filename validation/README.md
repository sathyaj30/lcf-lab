# L-edge benchmark

The benchmark script compares LCF Lab and XrayLarch fits on published nickel spectra. [Benchmark script](benchmark_l_edges.py)

## Reproduce the comparison

Run the commands from the repository root in a Python environment for LCF Lab.

```sh
python -m pip install -e .
```

Download `Supporting_Data.zip` from the cited Figshare record and pass the ZIP directly to the script. The script verifies its MD5 checksum against the record. The comparison uses XrayLarch 2026.2.2.

```sh
python -m pip install xraylarch==2026.2.2
python validation/benchmark_l_edges.py --ni-archive "/path/to/Supporting_Data.zip" --output ni-benchmark.json
```

## Measured Ni L₂,₃ spectra

The benchmark uses total electron yield (TEY) scans from Diamond Light Source beamline B07, session SI33459-1. The data were published by Páez Fajardo and colleagues under CC BY 4.0. [Figshare dataset](https://doi.org/10.6084/m9.figshare.28915994.v1) · [Research article](https://doi.org/10.1038/s41565-026-02189-y) · [License](https://creativecommons.org/licenses/by/4.0/)

Scans 48082 and 48077 serve as empirical endmembers. The benchmark subtracts the mean signal from 846 to 849 eV and scales each spectrum to unit area from 850 to 878 eV. It fits the 850 to 878 eV window on the measured target grid, with zero energy offset and nonnegative weights that sum to one. Both fitters receive the same target values and the same interpolated reference matrix. This isolates weight optimization for the chosen model. [XrayLarch linear-combination analysis](https://millenia.cars.aps.anl.gov/xraylarch/xafs_xanes.html#linear-combination-analysis)

| Measured target | Points | LCF Lab weights (48082, 48077) | LCF Lab RMSE | Maximum absolute difference in weight vs. XrayLarch 2026.2.2 |
| --- | ---: | ---: | ---: | ---: |
| 48074 | 280 | 0.000000, 1.000000 | 0.14875562 | 3.314 × 10⁻⁹ |
| 48075 | 280 | 0.000000, 1.000000 | 0.05938862 | 1.944 × 10⁻¹² |
| 48076 | 280 | 0.474042, 0.525958 | 0.01748737 | 1.002 × 10⁻¹⁰ |

The largest absolute difference in fitted signal across these targets was 5.097 × 10⁻¹⁰. Two fits reached a weight bound. These results establish numerical agreement for the selected reference model. The empirical weights describe the fit to these endmembers, and chemical interpretation depends on the suitability of those endmembers.
