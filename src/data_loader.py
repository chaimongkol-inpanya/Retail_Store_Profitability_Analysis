"""Read only complete, published Parquet generations."""

import json
import polars as pl
from src.config import PipelinePaths


class DashboardLoader:
    def __init__(self, paths=None):
        self.paths = paths or PipelinePaths()

    def manifest(self):
        return json.loads((self.paths.output / "current.json").read_text())

    def load(self, name, generation=None):
        generation = generation or self.manifest()["generation"]
        return pl.read_parquet(self.paths.output / generation / f"{name}.parquet")
