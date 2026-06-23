from abc import ABC, abstractmethod

import pandas as pd

IDENTITY_COLUMNS = ["player_name", "team", "position", "source"]


class Fetcher(ABC):
    """
    Normalized contract for a single external data source.

    fetch() must return a DataFrame containing at minimum the IDENTITY_COLUMNS
    plus any number of source-specific stat columns. merge.py relies on this
    shape to combine sources without needing per-source logic.
    """

    source_name: str = None

    @abstractmethod
    def fetch(self, **kwargs) -> pd.DataFrame:
        ...
