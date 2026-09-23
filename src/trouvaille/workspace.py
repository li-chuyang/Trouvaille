"""Workspace resource classification and the Agent-visible filesystem view."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterator


class ResourceScope(Enum):
    PROJECT = "project"
    INTERNAL = "internal"
    OUTSIDE = "outside"


@dataclass(frozen=True)
class WorkspaceResource:
    path: Path
    scope: ResourceScope


@dataclass(frozen=True)
class Workspace:
    """Canonical paths and resource facts for one real workspace."""

    root: Path
    internal_root: Path = field(init=False)

    def __post_init__(self) -> None:
        root = self.root.resolve()
        if not root.is_dir():
            raise ValueError(f"Workspace is not a directory: {root}")
        internal_root = (root / ".agentcore").resolve()
        if not internal_root.is_relative_to(root):
            raise ValueError(f"Workspace internal directory escapes workspace: {internal_root}")
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "internal_root", internal_root)

    def resolve(self, path: str | Path) -> Path:
        raw = Path(path)
        candidate = raw if raw.is_absolute() else self.root / raw
        return candidate.resolve()

    def resource(self, path: str | Path) -> WorkspaceResource:
        resolved = self.resolve(path)
        return WorkspaceResource(resolved, self.classify(resolved))

    def classify(self, path: Path) -> ResourceScope:
        resolved = path.resolve()
        if resolved.is_relative_to(self.internal_root):
            return ResourceScope.INTERNAL
        if resolved.is_relative_to(self.root):
            return ResourceScope.PROJECT
        return ResourceScope.OUTSIDE

    def internal_path(self, *parts: str) -> Path:
        relative = Path(*parts)
        if relative.is_absolute():
            raise ValueError("Internal path must be relative")
        resolved = (self.internal_root / relative).resolve()
        if not resolved.is_relative_to(self.internal_root):
            raise ValueError(f"Internal path escapes internal root: {relative}")
        return resolved


@dataclass(frozen=True)
class AgentWorkspaceView:
    """A PROJECT-only view used by Agent-facing filesystem tools."""

    workspace: Workspace

    @property
    def root(self) -> Path:
        return self.workspace.root

    def resolve(self, path: str | Path) -> Path:
        raw = Path(path)
        resource = self.workspace.resource(raw)
        if raw.is_absolute():
            raise ValueError("Path must be relative to workspace")
        if resource.scope is ResourceScope.INTERNAL:
            raise ValueError(f"Access denied to internal workspace resource: {path}")
        if resource.scope is ResourceScope.OUTSIDE:
            raise ValueError(f"Path escapes workspace: {path}")
        return resource.path

    def iterdir(self, path: str | Path = ".") -> Iterator[Path]:
        target = self.resolve(path)
        if not target.is_dir():
            raise ValueError(f"Not a directory: {path}")
        yield from self._visible_entries(target)

    def iter_files(
        self,
        path: str | Path = ".",
        *,
        excluded_directories: frozenset[str] = frozenset(),
    ) -> Iterator[Path]:
        target = self.resolve(path)
        if not target.exists():
            raise ValueError(f"Path does not exist: {path}")
        if target.is_file():
            yield target
            return
        relative_parts = target.relative_to(self.root).parts
        if any(part in excluded_directories for part in relative_parts):
            return

        pending = [target]
        while pending:
            directory = pending.pop()
            for entry in self._visible_entries(directory):
                if entry.is_dir():
                    if entry.name not in excluded_directories and not entry.is_symlink():
                        pending.append(entry)
                elif entry.is_file():
                    yield entry

    def _visible_entries(self, directory: Path) -> Iterator[Path]:
        for entry in directory.iterdir():
            if self.workspace.resource(entry).scope is ResourceScope.PROJECT:
                yield entry
