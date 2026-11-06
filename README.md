# LCF Lab

LCF Lab fits batches of normalized soft X-ray absorption spectra against reference standards. Its local browser workbench supports the first-row 3d series from Sc through Zn, with L₁, L₂, L₃ and combined L₂,₃ analysis windows.

## Install and open the workbench

With Python 3.10 or newer, run these commands from the source folder.

~~~sh
python -m pip install .
lcf-lab serve
~~~

The application opens in the browser and performs the fit on the same computer. Use **Examples** to load synthetic Fe or Mn data. The [user guide](docs/user-guide.md) covers files, settings, and interpretation. The [Python API](docs/api.md) supports scripted analysis.

## Reproduce an analysis

The workbench exports a ZIP with the input spectra, settings, fit results, reference weights, and curves. Extract the ZIP and use its analysis file to rerun the same model.

~~~sh
lcf-lab fit analysis.json -o rerun.zip
~~~

You can generate a synthetic example from the terminal.

~~~sh
lcf-lab example Mn -o example.json
lcf-lab fit example.json -o example-results.zip
~~~

## Develop and build

~~~sh
python -m pip install -e ".[dev]"
python -m pytest --cov=lcf_lab --cov-report=term-missing --cov-fail-under=90.01
python -m build
python -m twine check --strict dist/*
~~~

## Scientific scope

Use consistently normalized spectra with compatible measurement conditions. Fit weights describe contributions under the selected reference model. With a sum-to-one fit and suitable oxidation-state metadata, the workbench reports a weighted nominal mean. Review the residual and the sensitivity to reference choice before interpreting weights.

The Fe and Mn examples use synthetic spectra. The [bundled reference library](validation/reference-library.md) lists the sources and license for the published reference spectra. The [validation notes](validation/README.md) describe a comparison with XrayLarch using published Ni spectra.
