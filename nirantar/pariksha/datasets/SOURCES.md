# Real public datasets used by PARIKSHA

These are real field records, vendored so the checks run on an air-gapped machine. They are not aircraft-fleet data of any air force. Each one stands in for one kind of question NIRANTAR has to answer from real records.

| File | What it is | Source | Licence / terms |
|---|---|---|---|
| `genfan.csv` | Hours to failure or censoring of 70 diesel-generator fans (Nelson, 1982), 12 failures | R package `survival`, data set `genfan` (from Meeker & Escobar, *Statistical Methods for Reliability Data*, 1998) | LGPL (package); published data |
| `valve_seats.csv` | Valve-seat replacements of 41 diesel engines over about 2 years; `status=1` is a replacement, `0` the last inspection (Nelson & Doganaksoy, 1989) | R package `survival`, data set `valveSeat` | LGPL (package); published data |
| `braking_grids.csv` | Ages at which braking grids were replaced on locomotives, grids from two manufacturing batches (Doganaksoy & Nelson, 1998) | R package `survival`, data set `braking` | LGPL (package); published data |
| `backblaze_drives.csv.gz` | 52,422 hard drives of 85 models observed for about 2 years in a data centre (2,885 failures), with temperature and SMART flags | R package `frailtySurv`, data set `hdfail`, derived from Backblaze's public drive statistics (backblaze.com, hard-drive test data) | GPL (package); Backblaze data free to use with attribution to Backblaze |

All files were taken from the CRAN mirror on GitHub (`github.com/cran/<package>`) and converted from `.rda` to CSV without other changes. Exceptions: the valve-seat ids and status were cast to integers, and the drive file was gzip-compressed.
