"""Workspace paths used by file tools."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    root: Path

    def __post_init__(self) -> None:
        root = self.root.resolve()
        if not root.is_dir():
            raise ValueError(f"Workspace is not a directory: {root}")
        object.__setattr__(self, "root", root)

    def resolve(self, path: str) -> Path:
        relative = Path(path)
        if relative.is_absolute():
            raise ValueError("Path must be relative to workspace")
        resolved = (self.root / relative).resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError(f"Path escapes workspace: {path}")
        return resolved
