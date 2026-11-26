"""One-command launcher (`research-hub open`) for the local visual workspace."""

from __future__ import annotations

import errno
from pathlib import Path
import stat
import sys

from .core import WorkspaceError, safe_path
from .demo import create_demo
from .library_snapshot import LibrarySnapshot
from .obsidian_validation import ObsidianValidation
from .server import serve_workspace

DEFAULT_WORKSPACE_DIRNAME = "research-hub-workspace"
_WINDOWS_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
    *(f"COM{n}" for n in range(1, 10)),
    *(f"LPT{n}" for n in range(1, 10)),
})


def _is_link_or_reparse(info: object) -> bool:
    mode = getattr(info, "st_mode", 0)
    return bool(
        stat.S_ISLNK(mode)
        or (getattr(info, "st_file_attributes", 0) & 0x400)
        or getattr(info, "st_reparse_tag", 0)
    )


def _validate_target_path(root: str | Path | None) -> Path:
    if root is None:
        supplied = Path.home() / DEFAULT_WORKSPACE_DIRNAME
    else:
        if not isinstance(root, (str, Path)) or not str(root).strip():
            raise WorkspaceError("Workspace directory path cannot be empty")
        raw = str(root)
        if "\x00" in raw:
            raise WorkspaceError("Workspace directory path cannot contain NUL characters", "unsafe_path")
        supplied = Path(raw).expanduser()
    raw_supplied = str(supplied)
    if "\x00" in raw_supplied:
        raise WorkspaceError("Workspace directory path cannot contain NUL characters", "unsafe_path")
    if ".." in supplied.parts or raw_supplied.startswith(("\\\\", "//")):
        raise WorkspaceError("Workspace directory must be a local path without parent traversal", "unsafe_path")
    absolute = supplied.absolute()
    if absolute == Path(absolute.anchor):
        raise WorkspaceError("Workspace directory cannot be a filesystem root", "unsafe_path")
    for component in absolute.parts[1:]:
        stem = component.split(".")[0].rstrip(" ").upper()
        if ":" in component or component.endswith((".", " ")) or stem in _WINDOWS_RESERVED:
            raise WorkspaceError("Ambiguous workspace path component", "unsafe_path")
    for candidate in reversed((absolute, *absolute.parents)):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as exc:
            raise WorkspaceError("Cannot inspect workspace directory safely", "unsafe_path") from exc
        if _is_link_or_reparse(info):
            raise WorkspaceError("Workspace paths cannot contain symlinks or reparse points", "unsafe_path")
        if not stat.S_ISDIR(info.st_mode):
            raise WorkspaceError("Workspace path and its ancestors must be directories", "unsafe_path")
    if not absolute.parent.is_dir():
        raise WorkspaceError(f"Parent directory does not exist: {absolute.parent}", "missing_parent")
    return absolute.resolve()


def _has_existing_workspace_db(target: Path) -> bool:
    """Safely check whether target already contains a regular .research/workspace.sqlite3."""
    control = safe_path(target, ".research")
    try:
        control_info = control.lstat()
    except FileNotFoundError:
        return False
    if _is_link_or_reparse(control_info):
        raise WorkspaceError("Workspace .research path cannot be a symlink or reparse point", "unsafe_path")
    if not stat.S_ISDIR(control_info.st_mode):
        raise WorkspaceError("Workspace .research path must be a directory", "unsafe_path")

    db_path = safe_path(target, ".research/workspace.sqlite3")
    try:
        db_info = db_path.lstat()
    except FileNotFoundError:
        return False
    if _is_link_or_reparse(db_info):
        raise WorkspaceError("Workspace database cannot be a symlink or reparse point", "unsafe_path")
    if not stat.S_ISREG(db_info.st_mode):
        raise WorkspaceError("Workspace database path must be a regular file", "unsafe_path")
    return True


def _confirm_human_approvals(parser) -> bool:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        parser.error("--human-approvals requires an interactive local operator")
    print("Enable decision buttons for this local operator session? Type enable local review:", file=sys.stderr)
    try:
        return input().strip() == "enable local review"
    except EOFError:
        return False


def run_open_workspace(args, parser) -> int:
    """Validate/prepare the workspace directory and start the local workspace UI."""
    port = getattr(args, "port", 8765)
    if not isinstance(port, int) or isinstance(port, bool) or not (0 <= port <= 65535):
        parser.error("--port must be an integer between 0 and 65535")

    obsidian_vault = getattr(args, "obsidian_vault", None)
    library_snapshot = getattr(args, "library_snapshot", None)

    # Validate target path and read-only external boundaries BEFORE prompting or writing anything.
    try:
        target = _validate_target_path(getattr(args, "root", None))
        if obsidian_vault is not None:
            ObsidianValidation(obsidian_vault).assert_storage_outside(target)
        if library_snapshot is not None:
            LibrarySnapshot(library_snapshot)
    except (WorkspaceError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    human = False
    if getattr(args, "human_approvals", False):
        if not _confirm_human_approvals(parser):
            print("Not confirmed; no server started", file=sys.stderr)
            return 1
        human = True

    try:
        if getattr(args, "demo", False):
            if target.exists() and _has_existing_workspace_db(target):
                print(
                    f"Existing workspace found at {target}; preserving your saved data.",
                    file=sys.stderr,
                )
            elif target.exists() and any(target.iterdir()):
                raise WorkspaceError(
                    f"Directory {target} is not empty and does not contain a Research Hub workspace. "
                    "Choose a new or empty --root for --demo.",
                    "conflict",
                )
            else:
                create_demo(target)
                print(f"Created sample projects in {target}", flush=True)
        elif not target.exists():
            target.mkdir(exist_ok=True)
    except (WorkspaceError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Workspace directory: {target}", flush=True)
    try:
        serve_workspace(
            target,
            port=port,
            open_browser=not getattr(args, "no_browser", False),
            human=human,
            obsidian_vault=obsidian_vault,
            library_snapshot=library_snapshot,
            integrations_config="auto",
        )
    except (WorkspaceError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        in_use = exc.errno in {errno.EADDRINUSE, 10048} or getattr(exc, "winerror", None) == 10048
        if in_use:
            next_port = port + 1 if 0 < port < 65535 else 8766
            print(
                f"Port {port} is already in use. Retry your original command with --port {next_port} "
                "(keep all other options unchanged).",
                file=sys.stderr,
            )
            return 1
        print(f"Could not start workspace server: {exc}", file=sys.stderr)
        return 1
    return 0
