"""Lazy source scanning and input fingerprints."""

import polars as pl
from src.config import PipelinePaths


class DataIngestion:
    def __init__(self, paths=None):
        self.paths = paths or PipelinePaths()

    def scan(self, name):
        path = self.paths.raw / name
        return (
            pl.scan_parquet(path)
            if path.suffix == ".parquet"
            else pl.scan_csv(path, try_parse_dates=False)
        )

    def fingerprint(self):
        return {
            p.relative_to(self.paths.raw).as_posix(): {
                "size": p.stat().st_size,
                "mtime_ns": p.stat().st_mtime_ns,
            }
            for p in self.paths.raw.rglob("*")
            if p.is_file()
        }
