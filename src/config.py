from pathlib import Path
from dataclasses import dataclass

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class PipelinePaths:
    root: Path = ROOT

    @property
    def raw(self):
        return self.root / "raw_data"

    @property
    def output(self):
        return self.root / "dashboard_data"
