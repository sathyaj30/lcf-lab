# Published Mn, Co, Ni and Cu L-edge references

`reference-library.json` contains 13 measured soft X-ray absorption spectra from the sources below. The app can load the JSON directly. Every trace uses total electron yield (TEY) and retains the intensity values normalized by the source authors.

| Element | Reference materials | Source |
| --- | --- | --- |
| Mn | Mn₃O₄ (mixed +2/+3), MnO₂ (+4), Mn₂O₃ (+3), and MnSO₄ hydrate (+2) | [Villalobos et al., Figure 6b](https://doi.org/10.1002/celc.202200482), [dataset](https://doi.org/10.6084/m9.figshare.18415520.v1), [CSV](https://ndownloader.figshare.com/files/35574467) |
| Co | CoO (+2), Co₃O₄ (mixed +2/+3), LiCoO₂ (+3), and Co(NO₃)₂·6H₂O (+2) | [Villalobos et al., Figure 6a](https://doi.org/10.1002/celc.202200482), [dataset](https://doi.org/10.6084/m9.figshare.18415520.v1), [CSV](https://ndownloader.figshare.com/files/35574470) |
| Ni | LaNiO₂ (+1), NiO (+2), LiNiO₂ (+3), and Li₂NiO₃ (+4) | [Páez Fajardo et al., Figure 3a](https://doi.org/10.1038/s41565-026-02189-y), [dataset](https://doi.org/10.6084/m9.figshare.28915994.v1), [ZIP](https://ndownloader.figshare.com/files/58424281) |
| Cu | CuO (+2), measured at Ritsumeikan SR Center BL-11 | [NIMS record](https://mdr.nims.go.jp/datasets/e9f3e974-98d6-4702-9e56-3079f94483e5), [TEY data](https://mdr.nims.go.jp/filesets/e8785702-6956-4677-92ce-ecab81ff90d8/download), [metadata](https://mdr.nims.go.jp/filesets/9ddc653c-1524-4d19-a95f-e30d14051864/download) |

The datasets are licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The generated JSON attributes each source. Each entry records the source figure and trace, source file and checksum, detection mode, and processing. The numbers in parentheses are formal oxidation-state labels. Mixed-valence compounds have no single scalar valence in the pack. The sulfate is a separate Mn(II) reference with a different ligand environment from MnO.

## Reproduce

Download Figure 6b, Figure 6a, the Figure 3 source archive, and the CuO TEY data and metadata using the links above. From the LCF Lab source folder, run the following with Python 3 and substitute the paths to the downloaded files as needed.

```text
python validation/build_reference_library.py --mn figure-6b.csv --co figure-6a.csv --ni Supporting_Data.zip --cu 21032604.tey --cu-metadata nims-3336-metadata.json --output src/lcf_lab/web/reference-library.json
```

The script extracts the labeled reference columns, excluding the authors' experimental electrode traces. It sorts the Ni measurements by energy while preserving each measured energy and intensity pair. It leaves the original energy calibration and signal normalization intact.

The CuO file has 376 points from 910.9065 to 1004.136 eV, with both L₃ and L₂ maxima. The repository assigns the CuO L₃ calibration to 931.1 eV and describes the processed TEY signal as normalized electron yield (Ie/I₀).

| File | SHA-256 |
| --- | --- |
| `21032604.tey` | `02779acdea83d34e5e738f766b57a02761949c7d4308f3c4b064a98fb9c84bc4` |
| `nims-3336-metadata.json` | `0acfcc7fea225a3600ecbfdf9da4d68c02983154f6b60c9963c3d1de88db8348` |
| `reference-library.json` with CRLF line endings | `dcf3731aeed623c87b0a2542dfc8c34fd80e338d730acd00f6427621f102ab7d` |
| `reference-library.json` with LF line endings | `79379a74cf153cb4bd61f66c40be9796e10a94733fe21f858947dd60bdffc924` |
