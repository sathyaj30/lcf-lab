# Python interface

Use the same input structure for Python, the command line, and the workbench.

~~~python
from lcf_lab import fit_batch
from lcf_lab.demo import demo_analysis
from lcf_lab.export import build_export

analysis = demo_analysis("Mn")
result = fit_batch(analysis)
archive = build_export(analysis, result)
~~~

## Input

- Set the element to a symbol from Sc through Zn and the edge to L1, L2, L3, or L2,3.
- Supply settings with fit_min, fit_max, max_shift, and shift_step in electronvolts and the Boolean sum_to_one.
- Each sample needs an id, label, and paired numeric energy and signal arrays.
- Each standard has the same array structure and includes an element, edge, optional valence, and an included flag. A combined L2,3 standard can be used for an L2 or L3 fit when it covers the selected interval.
- Optional provenance, detection modes, and filenames are retained in the analysis export.

## Result

The fit_batch function returns the element, edge, settings, and results. Each successful sample gives the energy grid, measured and fitted signal, residual, weights, energy offset, root mean square residual, and nominal mean when available. Failed samples return an error and coverage information when available. Invalid project settings or reference definitions raise ValueError.

The demo_analysis function generates a complete synthetic request for Fe or Mn. The build_export function returns a ZIP archive as bytes.
