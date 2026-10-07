# Real aviation maintenance text and parts catalogue (SAARTHI field validation)

| File | What it is | Source |
|---|---|---|
| `logbook.csv` | 6,169 real maintenance logbook entries (problem and action, free text, truncated by the source system at about 60 characters) from aircraft engines of the University of North Dakota aviation program | MaintNet (Akhbardeh, Desell & Zampieri, COLING 2020 demos), as redistributed in the AKGAM / Zorro repository, `Aircraft_Annotation_DataFile.csv` |
| `ipc.csv` | 307 rows of the Lycoming O-320 illustrated parts catalogue: section, figure (assembly), item, part number, part type, specifics | AKGAM / Zorro repository, `pdf-extracted/parts-catalog.csv` (extracted from the manufacturer's catalogue) |
| `troubleshooting.csv` | 50 rows of the operator manual's troubleshooting table (trouble, probable cause, remedy) | AKGAM / Zorro repository, `pdf-extracted/troubleshooting.csv` |
| `reference_problems_gpt4o.csv`, `reference_actions_gpt4o.csv` | Machine extractions of part, problem, cylinders, engine side and action for each entry, made with GPT-4o by the AKGAM authors; used here as a **silver** reference (not expert-validated; the authors' corrected corpus is on Zenodo, doi 10.5281/zenodo.17815628) | AKGAM / Zorro repository, `log-extracted/` |

Repository: github.com/kai-vu/zorro (AKGAM components released under CC-BY 4.0; cite the AKGAM paper and MaintNet). The parts catalogue content belongs to its manufacturer and is used here only to test vocabulary linking; a deployment loads the IPC of its own fleet.
