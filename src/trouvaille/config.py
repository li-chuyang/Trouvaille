"""Minimal runtime configuration."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    workspace_root: Path

    @classmethod
    def from_cwd(cls) -> "AppConfig":
        return cls(workspace_root=Path.cwd().resolve())
