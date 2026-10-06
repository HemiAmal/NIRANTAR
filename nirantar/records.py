"""Record tables emitted by the twin (the e-MMS / IMMOLS / BRD analogue)."""
from __future__ import annotations

import pandas as pd


def to_frames(records: dict) -> dict[str, pd.DataFrame]:
    """Convert raw twin records into pandas tables: spells, repairs, snags."""
    return {
        "spells": pd.DataFrame(records["spells"]),
        "repairs": pd.DataFrame(records["repairs"]),
        "snags": pd.DataFrame(records["snags"]),
        "receipts": pd.DataFrame(records.get("receipts", [])),
    }
