"""Orchestrate raw_data -> validated Polars transforms -> dashboard_data."""

from datetime import datetime, timezone
import json
import os
import uuid
from src.config import PipelinePaths
from src.data_ingestion import DataIngestion
from src.data_transformation import DataTransformer, DataValidator


class RetailPipeline:
    def __init__(self, paths=None):
        self.paths = paths or PipelinePaths()
        self.ingestion = DataIngestion(self.paths)

    def run(self):
        before = self.ingestion.fingerprint()
        tables = DataTransformer(self.ingestion).transform()
        DataValidator().validate(tables)
        source = (
            self.ingestion.scan("sales_lines.parquet")
            .select("units", "revenue", "cost_of_goods")
            .sum()
            .collect()
        )
        for column in source.columns:
            actual = tables["category"][column].sum()
            expected = source[column][0]
            if abs(actual - expected) > max(0.001, abs(expected) * 1e-10):
                raise ValueError(f"Raw sales do not reconcile: {column}")
        if before != self.ingestion.fingerprint():
            raise RuntimeError("Raw data changed during pipeline run")
        generation = "run_" + uuid.uuid4().hex[:12]
        folder = self.paths.output / generation
        folder.mkdir(parents=True)
        for name, frame in tables.items():
            frame.write_parquet(folder / f"{name}.parquet", compression="zstd")
        manifest = {
            "generation": generation,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "currency": "THB",
            "provenance": "Mock data augmented by AI; fictional Thailand retail scenario",
            "inputs": before,
            "rows": {n: f.height for n, f in tables.items()},
        }
        temp = self.paths.output / f"current.{uuid.uuid4().hex}.tmp"
        temp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        os.replace(temp, self.paths.output / "current.json")
        return manifest


if __name__ == "__main__":
    print(json.dumps(RetailPipeline().run(), indent=2))
