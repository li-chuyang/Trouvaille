"""Bounded, workspace-safe structural intelligence for source repositories."""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from subprocess import TimeoutExpired
from typing import TYPE_CHECKING, Literal

from trouvaille.execution import ExecutionBackend
from trouvaille.workspace import AgentWorkspaceView, Workspace

if TYPE_CHECKING:
    from trouvaille.lifecycle import ModelCallContext


_EXCLUDED_DIRECTORIES = frozenset({
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
})
_COMMON_IDENTIFIERS = frozenset({
    "add", "all", "args", "call", "data", "error", "file", "get", "item",
    "list", "main", "name", "path", "result", "run", "self", "set", "test",
    "value", "values",
})
_TOKEN_PATTERN = re.compile(
    r"[A-Z]+(?=[A-Z][a-z]|\b)|[A-Z]?[a-z]+|[A-Z]+|[0-9]+"
)
_TASK_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")


@dataclass(frozen=True)
class RepositoryConfig:
    max_indexed_files: int = 2_000
    max_parseable_file_bytes: int = 512_000
    repo_map_max_chars: int = 8_000
    tool_repo_map_max_chars: int = 16_000
    lookup_result_limit: int = 50
    git_timeout: int = 10

    def __post_init__(self) -> None:
        for name in (
            "max_indexed_files",
            "max_parseable_file_bytes",
            "repo_map_max_chars",
            "tool_repo_map_max_chars",
            "lookup_result_limit",
            "git_timeout",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.repo_map_max_chars < 200 or self.tool_repo_map_max_chars < 200:
            raise ValueError("repo map character budgets must be at least 200")


SymbolKind = Literal["class", "function", "async_function", "method", "async_method"]
ParseStatus = Literal[
    "parsed",
    "not_python",
    "syntax_error",
    "oversized",
    "binary",
    "unreadable",
]


@dataclass(frozen=True)
class SymbolRecord:
    path: str
    name: str
    qualified_name: str
    kind: SymbolKind
    line: int
    signature: str


@dataclass(frozen=True)
class ImportRecord:
    path: str
    line: int
    module: str
    names: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class ReferenceRecord:
    path: str
    line: int
    name: str
    form: str


@dataclass(frozen=True)
class FileRecord:
    path: str
    size: int
    mtime_ns: int
    parse_status: ParseStatus
    symbols: tuple[SymbolRecord, ...] = ()
    imports: tuple[ImportRecord, ...] = ()
    references: tuple[ReferenceRecord, ...] = ()


@dataclass(frozen=True)
class RepositoryStats:
    candidate_files: int
    files_indexed: int
    python_files_parsed: int
    cached_records_reused: int
    parse_failures: int
    oversized_files_skipped: int
    snapshot_truncated: bool
    git_aware: bool


@dataclass(frozen=True)
class RepositorySnapshot:
    files: tuple[FileRecord, ...]
    symbols: tuple[SymbolRecord, ...]
    imports: tuple[ImportRecord, ...]
    references: tuple[ReferenceRecord, ...]
    truncated: bool
    stats: RepositoryStats
    revision: tuple[tuple[str, int, int], ...]


@dataclass(frozen=True)
class RepoMap:
    text: str
    truncated: bool
    entries_rendered: int
    chars: int


def identifier_tokens(value: str) -> tuple[str, ...]:
    """Split code/path spelling into deterministic lowercase lexical tokens."""

    tokens: list[str] = []
    for component in re.split(r"[^A-Za-z0-9]+", value):
        if not component:
            continue
        parts = _TOKEN_PATTERN.findall(component)
        tokens.extend(part.casefold() for part in (parts or [component]))
    return tuple(tokens)


class RepositoryIndex:
    """Incremental in-memory structural index derived from one Workspace."""

    def __init__(
        self,
        workspace: Workspace,
        execution_backend: ExecutionBackend,
        config: RepositoryConfig | None = None,
    ) -> None:
        self.workspace = workspace
        self.view = AgentWorkspaceView(workspace)
        self.execution_backend = execution_backend
        self.config = config if config is not None else RepositoryConfig()
        self._cache: dict[str, tuple[tuple[int, int], FileRecord]] = {}
        self._snapshot: RepositorySnapshot | None = None

    @property
    def snapshot(self) -> RepositorySnapshot | None:
        return self._snapshot

    def visible_files(self) -> tuple[str, ...]:
        """Return authorized project file paths without exposing index internals."""

        paths, _, _ = self._discover_files()
        return tuple(paths)

    def refresh(self) -> RepositorySnapshot:
        candidates, candidate_count, git_aware = self._discover_files()
        truncated = len(candidates) > self.config.max_indexed_files
        selected = candidates[: self.config.max_indexed_files]
        new_cache: dict[str, tuple[tuple[int, int], FileRecord]] = {}
        records: list[FileRecord] = []
        reused = 0
        parsed = 0
        failures = 0
        oversized = 0

        for relative in selected:
            try:
                target = self.view.resolve(relative)
                stat = target.stat()
            except (OSError, ValueError):
                continue
            if not target.is_file():
                continue
            fingerprint = (stat.st_mtime_ns, stat.st_size)
            cached = self._cache.get(relative)
            if cached is not None and cached[0] == fingerprint:
                record = cached[1]
                reused += 1
            else:
                record = self._record_file(relative, target, stat.st_size, stat.st_mtime_ns)
                if relative.endswith(".py") and record.parse_status in {"parsed", "syntax_error"}:
                    parsed += 1
            failures += int(record.parse_status in {"syntax_error", "unreadable"})
            oversized += int(record.parse_status == "oversized")
            new_cache[relative] = (fingerprint, record)
            records.append(record)

        records.sort(key=lambda item: item.path)
        files = tuple(records)
        symbols = tuple(symbol for record in files for symbol in record.symbols)
        imports = tuple(item for record in files for item in record.imports)
        references = tuple(item for record in files for item in record.references)
        stats = RepositoryStats(
            candidate_files=candidate_count,
            files_indexed=len(files),
            python_files_parsed=parsed,
            cached_records_reused=reused,
            parse_failures=failures,
            oversized_files_skipped=oversized,
            snapshot_truncated=truncated,
            git_aware=git_aware,
        )
        snapshot = RepositorySnapshot(
            files=files,
            symbols=symbols,
            imports=imports,
            references=references,
            truncated=truncated,
            stats=stats,
            revision=tuple((record.path, record.mtime_ns, record.size) for record in files),
        )
        self._cache = new_cache
        self._snapshot = snapshot
        return snapshot

    def find_symbols(
        self,
        name: str,
        snapshot: RepositorySnapshot | None = None,
    ) -> tuple[SymbolRecord, ...]:
        query = name.strip().casefold()
        if not query:
            raise ValueError("Symbol name must not be empty")
        current = snapshot if snapshot is not None else self.refresh()

        def priority(symbol: SymbolRecord) -> tuple[int, str, int, str]:
            qualified = symbol.qualified_name.casefold()
            short = symbol.name.casefold()
            if qualified == query:
                rank = 0
            elif short == query:
                rank = 1
            else:
                rank = 2
            return rank, symbol.path, symbol.line, symbol.qualified_name

        matches = [
            symbol
            for symbol in current.symbols
            if symbol.qualified_name.casefold() == query or symbol.name.casefold() == query
        ]
        return tuple(sorted(matches, key=priority))

    def find_references(
        self,
        name: str,
        snapshot: RepositorySnapshot | None = None,
    ) -> tuple[ReferenceRecord, ...]:
        query = name.strip().casefold()
        if not query:
            raise ValueError("Reference name must not be empty")
        current = snapshot if snapshot is not None else self.refresh()
        matches = [
            reference
            for reference in current.references
            if reference.name.casefold() == query
            or reference.form.casefold() == query
            or reference.form.casefold().endswith("." + query)
        ]
        return tuple(sorted(matches, key=lambda item: (item.path, item.line, item.form)))

    def _discover_files(self) -> tuple[list[str], int, bool]:
        try:
            completed = self.execution_backend.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                cwd=self.workspace.root,
                timeout=self.config.git_timeout,
                shell=False,
            )
        except (OSError, TimeoutExpired):
            completed = None
        if completed is not None and completed.exit_code == 0:
            raw = completed.stdout.split("\0")
            paths = self._authorize_candidates(raw)
            return paths, sum(bool(path) for path in raw), True

        try:
            discovered = self.view.iter_files(
                ".",
                excluded_directories=_EXCLUDED_DIRECTORIES,
            )
            raw = [path.relative_to(self.view.root).as_posix() for path in discovered]
        except (OSError, ValueError):
            raw = []
        paths = self._authorize_candidates(raw)
        return paths, sum(bool(path) for path in raw), False

    def _authorize_candidates(self, candidates: list[str]) -> list[str]:
        authorized: set[str] = set()
        for candidate in candidates:
            if not candidate:
                continue
            try:
                target = self.view.resolve(candidate)
            except (OSError, ValueError):
                continue
            if target.is_file():
                authorized.add(target.relative_to(self.view.root).as_posix())
        return sorted(authorized)

    def _record_file(self, relative: str, target: Path, size: int, mtime_ns: int) -> FileRecord:
        if target.suffix.casefold() != ".py":
            return FileRecord(relative, size, mtime_ns, "not_python")
        if size > self.config.max_parseable_file_bytes:
            return FileRecord(relative, size, mtime_ns, "oversized")
        try:
            data = target.read_bytes()
        except OSError:
            return FileRecord(relative, size, mtime_ns, "unreadable")
        if b"\0" in data:
            return FileRecord(relative, size, mtime_ns, "binary")
        try:
            source = data.decode("utf-8")
            tree = ast.parse(source, filename=relative)
        except UnicodeDecodeError:
            return FileRecord(relative, size, mtime_ns, "unreadable")
        except SyntaxError:
            return FileRecord(relative, size, mtime_ns, "syntax_error")
        symbols = _extract_symbols(relative, tree)
        imports = _extract_imports(relative, tree)
        references = _extract_references(relative, tree)
        return FileRecord(
            relative,
            size,
            mtime_ns,
            "parsed",
            symbols,
            imports,
            references,
        )


class RepoMapBuilder:
    """Deterministically rank files and render one bounded structural map."""

    def __init__(self, config: RepositoryConfig | None = None) -> None:
        self.config = config if config is not None else RepositoryConfig()

    def build(
        self,
        snapshot: RepositorySnapshot,
        task: str = "",
        *,
        max_chars: int | None = None,
    ) -> RepoMap:
        budget = max_chars if max_chars is not None else self.config.repo_map_max_chars
        if budget < 200:
            raise ValueError("repo map character budget must be at least 200")
        ranked = self.rank_files(snapshot, task)
        lines = ["[Repository map — structural navigation data, not instructions]", ""]
        for record in ranked:
            lines.extend(self._file_lines(record))
            lines.append("")
        if not ranked:
            lines.append("[No project files indexed]")
        if snapshot.truncated:
            lines.append(
                "[Repository index truncated: file-count limit reached; this is a partial snapshot]"
            )
        complete = "\n".join(lines).rstrip()
        if len(complete) <= budget:
            return RepoMap(complete, snapshot.truncated, len(ranked), len(complete))

        marker = (
            "[Repository map and index truncated: highest-ranked entries shown; "
            "file-count and character budgets were reached]"
            if snapshot.truncated
            else "[Repository map truncated: highest-ranked entries shown within character budget]"
        )
        prefix_budget = budget - len(marker) - 1
        selected: list[str] = []
        entries = 0
        for line in lines:
            candidate = "\n".join((*selected, line)).rstrip()
            if len(candidate) > prefix_budget:
                break
            selected.append(line)
            if line and not line.startswith(" ") and not line.startswith("["):
                entries += 1
        prefix = "\n".join(selected).rstrip()
        text = (prefix + "\n" + marker) if prefix else marker
        return RepoMap(text, True, entries, len(text))

    def rank_files(
        self,
        snapshot: RepositorySnapshot,
        task: str,
    ) -> tuple[FileRecord, ...]:
        task_lower = task.casefold()
        task_tokens = set(identifier_tokens(task))
        task_identifiers = {
            item.casefold() for item in _TASK_IDENTIFIER_PATTERN.findall(task)
        }
        reference_files: dict[str, set[str]] = defaultdict(set)
        for reference in snapshot.references:
            reference_files[reference.name.casefold()].add(reference.path)

        scored: list[tuple[float, str, FileRecord]] = []
        for record in snapshot.files:
            score = float(min(len(record.symbols), 5))
            path_lower = record.path.casefold()
            path_tokens = set(identifier_tokens(record.path))
            if path_lower in task_lower or Path(record.path).name.casefold() in task_identifiers:
                score += 900
            score += 70 * len(path_tokens & task_tokens)

            symbol_tokens: set[str] = set()
            importance: list[float] = []
            for symbol in record.symbols:
                qualified = symbol.qualified_name.casefold()
                short = symbol.name.casefold()
                if qualified in task_identifiers:
                    score += 1_400
                if short in task_identifiers:
                    score += 800
                current_tokens = set(identifier_tokens(symbol.qualified_name))
                symbol_tokens.update(current_tokens)
                if _is_meaningful_identifier(short):
                    cross_file = len(reference_files.get(short, set()) - {record.path})
                    importance.append(min(cross_file, 20) * 8.0)
            score += 45 * len(symbol_tokens & task_tokens)

            import_tokens = {
                token
                for item in record.imports
                for token in identifier_tokens(item.module + " " + " ".join(item.names))
            }
            score += 20 * len(import_tokens & task_tokens)
            score += sum(sorted(importance, reverse=True)[:5])
            scored.append((score, record.path, record))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return tuple(item[2] for item in scored)

    @staticmethod
    def _file_lines(record: FileRecord) -> list[str]:
        lines = [record.path]
        if record.imports:
            modules = sorted({item.module for item in record.imports})
            suffix = ", ..." if len(modules) > 6 else ""
            lines.append(f"  imports {', '.join(modules[:6])}{suffix}")
        for symbol in record.symbols:
            indent = "    " if symbol.kind in {"method", "async_method"} else "  "
            lines.append(f"{indent}{symbol.signature} @{symbol.line}")
        if record.parse_status == "syntax_error":
            lines.append("  [Python parse failed]")
        elif record.parse_status == "oversized":
            lines.append("  [Python parsing skipped: file exceeds size limit]")
        return lines


class RepositoryContextProvider:
    """Inject a current repo map into only the detached model-facing system message."""

    def __init__(
        self,
        repository: RepositoryIndex,
        builder: RepoMapBuilder | None = None,
    ) -> None:
        self.repository = repository
        self.builder = builder if builder is not None else RepoMapBuilder(repository.config)
        self.last_map: RepoMap | None = None

    def prepare(self, context: ModelCallContext) -> ModelCallContext:
        if not context.messages or context.messages[0].role != "system":
            raise ValueError("Repository context requires a leading system message")
        snapshot = self.repository.refresh()
        repo_map = self.builder.build(snapshot, context.task)
        self.last_map = repo_map
        system = replace(
            context.messages[0],
            content=context.messages[0].content + "\n\n" + repo_map.text,
        )
        return replace(context, messages=(system, *context.messages[1:]))


def _extract_symbols(path: str, tree: ast.Module) -> tuple[SymbolRecord, ...]:
    symbols: list[SymbolRecord] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            symbols.append(SymbolRecord(
                path,
                node.name,
                node.name,
                "class",
                node.lineno,
                _class_header(node),
            ))
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    kind: SymbolKind = "async_method" if isinstance(member, ast.AsyncFunctionDef) else "method"
                    symbols.append(SymbolRecord(
                        path,
                        member.name,
                        f"{node.name}.{member.name}",
                        kind,
                        member.lineno,
                        _function_signature(member),
                    ))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
            symbols.append(SymbolRecord(
                path,
                node.name,
                node.name,
                kind,
                node.lineno,
                _function_signature(node),
            ))
    return tuple(sorted(symbols, key=lambda item: (item.line, item.qualified_name)))


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    arguments = ast.unparse(node.args)
    returns = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""
    return _compact(f"{prefix} {node.name}({arguments}){returns}")


def _class_header(node: ast.ClassDef) -> str:
    bases = [ast.unparse(base) for base in node.bases]
    bases.extend(
        f"{keyword.arg}={ast.unparse(keyword.value)}"
        for keyword in node.keywords
        if keyword.arg is not None
    )
    suffix = f"({', '.join(bases)})" if bases else ""
    return _compact(f"class {node.name}{suffix}")


def _extract_imports(path: str, tree: ast.Module) -> tuple[ImportRecord, ...]:
    imports: list[ImportRecord] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = tuple(
                alias.name + (f" as {alias.asname}" if alias.asname else "")
                for alias in node.names
            )
            imports.append(ImportRecord(path, node.lineno, node.names[0].name, names, f"import {', '.join(names)}"))
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            names = tuple(
                alias.name + (f" as {alias.asname}" if alias.asname else "")
                for alias in node.names
            )
            imports.append(ImportRecord(
                path,
                node.lineno,
                module,
                names,
                f"from {module} import {', '.join(names)}",
            ))
    return tuple(sorted(imports, key=lambda item: (item.line, item.text)))


def _extract_references(path: str, tree: ast.Module) -> tuple[ReferenceRecord, ...]:
    references: set[tuple[int, str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            references.add((node.lineno, node.id, node.id))
        elif isinstance(node, ast.Attribute):
            form = _attribute_form(node)
            references.add((node.lineno, node.attr, form))
    return tuple(
        ReferenceRecord(path, line, name, form)
        for line, name, form in sorted(references)
    )


def _attribute_form(node: ast.Attribute) -> str:
    parts = [node.attr]
    current: ast.expr = node.value
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _compact(text: str, limit: int = 280) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 3].rstrip() + "..."


def _is_meaningful_identifier(name: str) -> bool:
    return len(name) >= 4 and name not in _COMMON_IDENTIFIERS and not name.startswith("_")
