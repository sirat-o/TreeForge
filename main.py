"""
TreeForge — Advanced Interactive Directory Tree Tool
"""

from __future__ import annotations

import fnmatch
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

import questionary
from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

console = Console()

CONFIG_FILE = Path.home() / ".treeforgerc"

# ── Default ignore patterns (supports glob wildcards) ─────────────────────────
DEFAULT_IGNORE_PATTERNS: list[str] = [
    ".git", ".next", "node_modules", "dist", "build",
    "__pycache__", ".venv", "venv", ".env",
    ".idea", ".vscode", ".turbo", ".cache",
    ".DS_Store", "*.pyc", "*.pyo", "*.egg-info",
    "*.log", ".pytest_cache", "coverage",
]

# ── File-type icon map (extension → emoji) ────────────────────────────────────
EXTENSION_ICONS: dict[str, str] = {
    # Code
    ".py": "🐍", ".js": "🟨", ".ts": "🔷", ".jsx": "⚛️ ", ".tsx": "⚛️ ",
    ".go": "🐹", ".rs": "🦀", ".cpp": "⚙️ ", ".c": "⚙️ ", ".h": "📎",
    ".java": "☕", ".kt": "🎯", ".swift": "🍎", ".rb": "💎",
    ".php": "🐘", ".cs": "🔵", ".lua": "🌙", ".r": "📊",
    # Web
    ".html": "🌐", ".css": "🎨", ".scss": "🎨", ".sass": "🎨",
    # Data / Config
    ".json": "📋", ".yaml": "📋", ".yml": "📋", ".toml": "📋",
    ".xml": "📋", ".csv": "📊", ".sql": "🗄️ ", ".env": "🔐",
    # Docs
    ".md": "📝", ".txt": "📄", ".rst": "📝", ".pdf": "📕",
    ".doc": "📘", ".docx": "📘",
    # Images
    ".png": "🖼️ ", ".jpg": "🖼️ ", ".jpeg": "🖼️ ", ".gif": "🎞️ ",
    ".svg": "✏️ ", ".ico": "🎯", ".webp": "🖼️ ",
    # Archives
    ".zip": "📦", ".tar": "📦", ".gz": "📦", ".rar": "📦",
    # Shell / Scripts
    ".sh": "🐚", ".bash": "🐚", ".zsh": "🐚", ".fish": "🐟",
    # Lock / Package
    ".lock": "🔒",
}

# ── Rich color per extension category ─────────────────────────────────────────
EXTENSION_COLORS: dict[str, str] = {
    ".py": "green3", ".js": "yellow3", ".ts": "cornflower_blue", ".jsx": "cyan2",
    ".tsx": "cyan2", ".go": "aquamarine3", ".rs": "orange3", ".html": "orange1",
    ".css": "medium_purple3", ".scss": "medium_purple3",
    ".json": "bright_cyan", ".yaml": "bright_cyan", ".yml": "bright_cyan",
    ".md": "bright_white", ".txt": "white", ".env": "bright_red",
    ".png": "pink3", ".jpg": "pink3", ".jpeg": "pink3", ".svg": "pink3",
    ".zip": "gold3", ".tar": "gold3", ".gz": "gold3",
    ".sh": "green_yellow", ".bash": "green_yellow",
}

EXPORT_FORMATS = ["Preview only", "Save as TXT", "Save as Markdown"]


# ══════════════════════════════════════════════════════════════════════════════
# Data models
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(slots=True)
class TreeOptions:
    root: Path
    show_hidden: bool = False
    dirs_only: bool = False
    max_depth: int | None = None
    show_file_sizes: bool = False
    ignore_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORE_PATTERNS))
    use_icons: bool = True
    use_colors: bool = True
    follow_symlinks: bool = False
    sort_by: str = "name"          # name | size | ext | modified
    export_format: str = "Preview only"
    output_path: Path | None = None


@dataclass
class TreeStats:
    folders: int = 0
    files: int = 0
    total_file_size: int = 0
    symlinks: int = 0
    ext_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    ext_sizes: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    scan_time_ms: float = 0.0


@dataclass
class JsonNode:
    name: str
    type: str                       # "dir" | "file" | "symlink"
    size: int | None = None
    extension: str | None = None
    children: list["JsonNode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict = {"name": self.name, "type": self.type}
        if self.size is not None:
            d["size"] = self.size
        if self.extension:
            d["extension"] = self.extension
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def is_hidden(path: Path) -> bool:
    return path.name.startswith(".")


def matches_ignore(path: Path, patterns: list[str]) -> bool:
    name = path.name
    for pat in patterns:
        if fnmatch.fnmatch(name, pat):
            return True
    return False


def should_ignore(path: Path, options: TreeOptions) -> bool:
    if not options.show_hidden and is_hidden(path):
        return True
    if matches_ignore(path, options.ignore_patterns):
        return True
    return False


def safe_iterdir(path: Path) -> list[Path]:
    try:
        return list(path.iterdir())
    except (PermissionError, OSError):
        return []


def safe_stat(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
    except (PermissionError, OSError):
        return None


def safe_file_size(path: Path) -> int:
    st = safe_stat(path)
    return st.st_size if st else 0


def safe_mtime(path: Path) -> float:
    st = safe_stat(path)
    return st.st_mtime if st else 0.0


def format_bytes(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.2f} {unit}"
        size /= 1024
    return f"{num_bytes} B"


def sort_paths(paths: Iterable[Path], sort_by: str) -> list[Path]:
    match sort_by:
        case "size":
            return sorted(paths, key=lambda p: (0 if p.is_dir() else 1, -safe_file_size(p)))
        case "ext":
            return sorted(paths, key=lambda p: (0 if p.is_dir() else 1, p.suffix.lower(), p.name.lower()))
        case "modified":
            return sorted(paths, key=lambda p: (0 if p.is_dir() else 1, -safe_mtime(p)))
        case _:  # name
            return sorted(paths, key=lambda p: (0 if p.is_dir() else 1, p.name.lower()))


def get_icon(path: Path) -> str:
    if path.is_symlink():
        return "🔗"
    if path.is_dir():
        return "📁"
    return EXTENSION_ICONS.get(path.suffix.lower(), "📄")


def get_color(path: Path) -> str:
    if path.is_dir():
        return "bold bright_blue"
    return EXTENSION_COLORS.get(path.suffix.lower(), "white")


def get_display_name(path: Path, options: TreeOptions) -> Text:
    icon = (get_icon(path) + " ") if options.use_icons else ""
    color = get_color(path) if options.use_colors else "white"
    label = path.name

    if path.is_symlink():
        try:
            target = path.resolve()
            label += f" → {target}"
        except OSError:
            label += " → [broken]"

    if not path.is_dir() and options.show_file_sizes:
        size = safe_file_size(path)
        label += f"  [dim]({format_bytes(size)})[/dim]"

    return Text.from_markup(f"{icon}[{color}]{label}[/{color}]")


def get_plain_name(path: Path, options: TreeOptions) -> str:
    icon = (get_icon(path) + " ") if options.use_icons else ""
    name = path.name
    if not path.is_dir() and options.show_file_sizes:
        size = safe_file_size(path)
        name += f" ({format_bytes(size)})"
    return f"{icon}{name}"


# ══════════════════════════════════════════════════════════════════════════════
# Tree builders
# ══════════════════════════════════════════════════════════════════════════════

def add_to_rich_tree(
    tree: Tree,
    root: Path,
    options: TreeOptions,
    stats: TreeStats,
    current_depth: int = 0,
) -> None:
    if options.max_depth is not None and current_depth >= options.max_depth:
        return

    children = [c for c in safe_iterdir(root) if not should_ignore(c, options)]
    if options.dirs_only:
        children = [c for c in children if c.is_dir()]

    for child in sort_paths(children, options.sort_by):
        if child.is_symlink():
            stats.symlinks += 1
            tree.add(get_display_name(child, options))
        elif child.is_dir():
            stats.folders += 1
            branch = tree.add(get_display_name(child, options))
            add_to_rich_tree(branch, child, options, stats, current_depth + 1)
        else:
            stats.files += 1
            sz = safe_file_size(child)
            stats.total_file_size += sz
            ext = child.suffix.lower() or "(none)"
            stats.ext_counts[ext] += 1
            stats.ext_sizes[ext] += sz
            tree.add(get_display_name(child, options))


def build_rich_tree(options: TreeOptions) -> tuple[Tree, TreeStats]:
    t0 = time.perf_counter()
    label = Text()
    label.append("📦 ", style="")
    label.append(options.root.name + "/", style="bold bright_white")
    tree = Tree(label, guide_style="bright_blue")
    stats = TreeStats()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TextColumn("[cyan]{task.fields[items]} items"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("[cyan]Scanning…", total=None, items=0)

        def _scan(t: Tree, root: Path, depth: int) -> None:
            if options.max_depth is not None and depth >= options.max_depth:
                return
            children = [c for c in safe_iterdir(root) if not should_ignore(c, options)]
            if options.dirs_only:
                children = [c for c in children if c.is_dir()]
            for child in sort_paths(children, options.sort_by):
                progress.advance(task)
                progress.update(task, items=stats.files + stats.folders)
                if child.is_symlink():
                    stats.symlinks += 1
                    t.add(get_display_name(child, options))
                elif child.is_dir():
                    stats.folders += 1
                    branch = t.add(get_display_name(child, options))
                    _scan(branch, child, depth + 1)
                else:
                    stats.files += 1
                    sz = safe_file_size(child)
                    stats.total_file_size += sz
                    ext = child.suffix.lower() or "(none)"
                    stats.ext_counts[ext] += 1
                    stats.ext_sizes[ext] += sz
                    t.add(get_display_name(child, options))

        _scan(tree, options.root, 0)

    stats.scan_time_ms = (time.perf_counter() - t0) * 1000
    return tree, stats


def build_plain_lines(
    root: Path,
    options: TreeOptions,
    current_depth: int = 0,
    prefix: str = "",
    stats: TreeStats | None = None,
) -> list[str]:
    if options.max_depth is not None and current_depth >= options.max_depth:
        return []

    children = [c for c in safe_iterdir(root) if not should_ignore(c, options)]
    if options.dirs_only:
        children = [c for c in children if c.is_dir()]
    children = sort_paths(children, options.sort_by)
    lines: list[str] = []

    for i, child in enumerate(children):
        is_last = i == len(children) - 1
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{get_plain_name(child, options)}")
        if child.is_dir():
            if stats:
                stats.folders += 1
            ext_prefix = "    " if is_last else "│   "
            lines.extend(build_plain_lines(
                child, options, current_depth + 1, prefix + ext_prefix, stats
            ))
        else:
            if stats:
                stats.files += 1
                sz = safe_file_size(child)
                stats.total_file_size += sz
                ext = child.suffix.lower() or "(none)"
                stats.ext_counts[ext] += 1
                stats.ext_sizes[ext] += sz

    return lines


def generate_plain_tree(options: TreeOptions) -> tuple[str, TreeStats]:
    stats = TreeStats()
    lines = [f"{options.root.name}/"]
    lines.extend(build_plain_lines(options.root, options, stats=stats))
    return "\n".join(lines), stats


def build_json_tree(
    root: Path,
    options: TreeOptions,
    current_depth: int = 0,
) -> JsonNode:
    node = JsonNode(name=root.name, type="dir")
    if options.max_depth is not None and current_depth >= options.max_depth:
        return node

    children = [c for c in safe_iterdir(root) if not should_ignore(c, options)]
    if options.dirs_only:
        children = [c for c in children if c.is_dir()]

    for child in sort_paths(children, options.sort_by):
        if child.is_symlink():
            node.children.append(JsonNode(name=child.name, type="symlink"))
        elif child.is_dir():
            node.children.append(build_json_tree(child, options, current_depth + 1))
        else:
            node.children.append(JsonNode(
                name=child.name,
                type="file",
                size=safe_file_size(child),
                extension=child.suffix.lower() or None,
            ))
    return node


# ══════════════════════════════════════════════════════════════════════════════
# Export helpers
# ══════════════════════════════════════════════════════════════════════════════

def to_markdown(tree_text: str, root: Path) -> str:
    return f"# Directory Tree: `{root.name}`\n\n```text\n{tree_text}\n```\n"


def to_html(tree_text: str, root: Path, stats: TreeStats) -> str:
    escaped = tree_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TreeForge — {root.name}</title>
  <style>
    :root {{
      --bg: #0d1117; --surface: #161b22; --border: #30363d;
      --text: #e6edf3; --dim: #8b949e; --accent: #58a6ff;
      --green: #3fb950; --font: 'Cascadia Code', 'Fira Code', monospace;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: var(--bg); color: var(--text); font-family: var(--font);
            font-size: 14px; padding: 2rem; }}
    header {{ border-bottom: 1px solid var(--border); padding-bottom: 1rem;
              margin-bottom: 1.5rem; }}
    h1 {{ color: var(--accent); font-size: 1.4rem; }}
    .meta {{ color: var(--dim); font-size: 0.85rem; margin-top: .4rem; }}
    .stats {{ display: flex; gap: 2rem; margin: 1.5rem 0;
              padding: 1rem; background: var(--surface);
              border: 1px solid var(--border); border-radius: 8px; }}
    .stat {{ display: flex; flex-direction: column; }}
    .stat-val {{ font-size: 1.5rem; color: var(--green); font-weight: 700; }}
    .stat-lbl {{ font-size: 0.75rem; color: var(--dim); margin-top: 2px; }}
    pre {{ background: var(--surface); border: 1px solid var(--border);
           border-radius: 8px; padding: 1.5rem; overflow-x: auto;
           line-height: 1.6; color: var(--text); }}
    footer {{ margin-top: 2rem; color: var(--dim); font-size: 0.75rem; }}
  </style>
</head>
<body>
  <header>
    <h1>📦 {root.name}/</h1>
    <div class="meta">Generated by TreeForge</div>
  </header>
  <div class="stats">
    <div class="stat"><span class="stat-val">{stats.folders}</span><span class="stat-lbl">Folders</span></div>
    <div class="stat"><span class="stat-val">{stats.files}</span><span class="stat-lbl">Files</span></div>
    <div class="stat"><span class="stat-val">{format_bytes(stats.total_file_size)}</span><span class="stat-lbl">Total size</span></div>
    <div class="stat"><span class="stat-val">{stats.scan_time_ms:.0f} ms</span><span class="stat-lbl">Scan time</span></div>
  </div>
  <pre>{escaped}</pre>
  <footer>TreeForge — Interactive Directory Tree Tool</footer>
</body>
</html>"""


def save_output(content: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def copy_to_clipboard(text: str) -> bool:
    """Try to copy text to clipboard via xclip/pbcopy/clip."""
    import subprocess
    for cmd in (["pbcopy"], ["xclip", "-selection", "clipboard"], ["clip"]):
        try:
            proc = subprocess.run(cmd, input=text.encode(), capture_output=True, timeout=3)
            if proc.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return False


# ══════════════════════════════════════════════════════════════════════════════
# Config persistence
# ══════════════════════════════════════════════════════════════════════════════

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return {}


def save_config(options: TreeOptions) -> None:
    cfg = {
        "show_hidden": options.show_hidden,
        "dirs_only": options.dirs_only,
        "show_file_sizes": options.show_file_sizes,
        "max_depth": options.max_depth,
        "ignore_patterns": options.ignore_patterns,
        "use_icons": options.use_icons,
        "use_colors": options.use_colors,
        "sort_by": options.sort_by,
        "follow_symlinks": options.follow_symlinks,
    }
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


# ══════════════════════════════════════════════════════════════════════════════
# Rich rendering
# ══════════════════════════════════════════════════════════════════════════════

def render_summary(options: TreeOptions, stats: TreeStats, output_path: Path | None, top_n: int = 10) -> None:
    # ── Stats table
    stat_table = Table(title="Statistics", box=box.SIMPLE_HEAVY, show_header=True, header_style="bold green")
    stat_table.add_column("Metric", style="dim green", no_wrap=True)
    stat_table.add_column("Value", style="bright_white")

    stat_table.add_row("Folders", str(stats.folders))
    stat_table.add_row("Files", str(stats.files))
    stat_table.add_row("Symlinks", str(stats.symlinks))
    stat_table.add_row("Total size", format_bytes(stats.total_file_size))
    stat_table.add_row("Scan time", f"{stats.scan_time_ms:.1f} ms")

    # ── File-type breakdown table
    ext_table = Table(
        title=f"Top {top_n} File Types",
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold magenta",
    )
    ext_table.add_column("Extension", style="cyan", no_wrap=True)
    ext_table.add_column("Count", justify="right", style="yellow")
    ext_table.add_column("Total Size", justify="right", style="green")
    ext_table.add_column("Avg Size", justify="right", style="dim")

    if stats.ext_counts:
        sorted_exts = sorted(stats.ext_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
        for ext, count in sorted_exts:
            total_sz = stats.ext_sizes.get(ext, 0)
            avg_sz = total_sz // count if count else 0
            icon = EXTENSION_ICONS.get(ext, "📄")
            ext_table.add_row(
                f"{icon} {ext}",
                str(count),
                format_bytes(total_sz),
                format_bytes(avg_sz),
            )

    console.print()
    console.print(Columns([stat_table, ext_table]))


def preview_plain_text(tree_text: str) -> None:
    syntax = Syntax(
        tree_text, "text",
        theme="github-dark",
        line_numbers=False,
        word_wrap=False,
    )
    console.print(Panel(
        syntax,
        title="[bold]Plain Text Preview[/bold]",
        border_style="bright_blue",
        padding=(0, 1),
    ))


# ══════════════════════════════════════════════════════════════════════════════
# Interactive prompts
# ══════════════════════════════════════════════════════════════════════════════

def ask_project_path(default_cfg: dict) -> Path:
    default_str = str(Path.cwd())
    while True:
        value = questionary.path(
            "📂  Project folder:",
            default=default_str,
            only_directories=True,
        ).ask()
        if not value:
            console.print("[red]No path selected.[/red]")
            raise SystemExit(1)
        path = Path(value).expanduser().resolve()
        if path.exists() and path.is_dir():
            return path
        console.print(f"[red]Invalid directory:[/red] {path}")


def ask_yes_no(message: str, default: bool = False) -> bool:
    return bool(questionary.confirm(message, default=default).ask())


def ask_max_depth(default_cfg: dict) -> int | None:
    cfg_depth = default_cfg.get("max_depth")
    default_val = str(cfg_depth) if cfg_depth is not None else "3"

    if not ask_yes_no("↕️   Limit max depth?", default=cfg_depth is not None):
        return None
    while True:
        val = questionary.text("   Max depth:", default=default_val).ask()
        if val is None:
            return None
        try:
            d = int(val)
            if d >= 0:
                return d
        except ValueError:
            pass
        console.print("[red]Enter a valid non-negative integer.[/red]")


def ask_sort_by(default_cfg: dict) -> str:
    default = default_cfg.get("sort_by", "name")
    result = questionary.select(
        "🔀  Sort entries by:",
        choices=["name", "size", "ext", "modified"],
        default=default,
    ).ask()
    return result or "name"


def ask_ignore_patterns(default_cfg: dict) -> list[str]:
    if not ask_yes_no("🚫  Edit ignore patterns?", default=False):
        stored = default_cfg.get("ignore_patterns")
        return stored if stored else list(DEFAULT_IGNORE_PATTERNS)
    current = ", ".join(default_cfg.get("ignore_patterns", DEFAULT_IGNORE_PATTERNS))
    val = questionary.text("   Patterns (comma-separated, globs OK):", default=current).ask()
    if not val:
        return list(DEFAULT_IGNORE_PATTERNS)
    return [p.strip() for p in val.split(",") if p.strip()]


def ask_export_format() -> str:
    result = questionary.select("💾  Export format:", choices=EXPORT_FORMATS).ask()
    if not result:
        raise SystemExit(1)
    return result


def ask_output_path(fmt: str) -> Path | None:
    if fmt == "Preview only":
        return None
    ext_map = {
        "Save as TXT": ".txt",
        "Save as Markdown": ".md",
        "Save as JSON": ".json",
        "Save as HTML": ".html",
    }
    default_ext = ext_map.get(fmt, ".txt")
    default_name = f"project-tree{default_ext}"
    val = questionary.text("   Output filename:", default=default_name).ask()
    if not val:
        raise SystemExit(1)
    p = Path(val).expanduser()
    if not p.suffix:
        p = p.with_suffix(default_ext)
    return p.resolve()


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def run() -> None:
    console.print()
    console.print(Panel.fit(
        "[bold bright_white]TreeForge[/bold bright_white]  [dim bright_blue]v2.0[/dim bright_blue]\n"
        "[dim]Advanced interactive directory tree — preview, analyse, export[/dim]",
        border_style="bright_blue",
        padding=(0, 2),
    ))
    console.print()

    cfg = load_config()
    if cfg:
        console.print("[dim]  ↳ Loaded settings from ~/.treeforgerc[/dim]\n")

    # ── Gather options ────────────────────────────────────────────────────────
    root          = ask_project_path(cfg)
    show_hidden   = ask_yes_no("👁   Show hidden files/folders?",  cfg.get("show_hidden", False))
    dirs_only     = ask_yes_no("📁  Directories only?",            cfg.get("dirs_only", False))
    show_sizes    = ask_yes_no("⚖️   Show file sizes?",             cfg.get("show_file_sizes", True))
    use_icons     = ask_yes_no("🎨  Use file-type icons?",         cfg.get("use_icons", True))
    use_colors    = ask_yes_no("🌈  Use syntax colours?",          cfg.get("use_colors", True))
    sort_by       = ask_sort_by(cfg)
    max_depth     = ask_max_depth(cfg)
    ignore_pats   = ask_ignore_patterns(cfg)
    fmt           = ask_export_format()
    output_path   = ask_output_path(fmt)

    options = TreeOptions(
        root=root,
        show_hidden=show_hidden,
        dirs_only=dirs_only,
        max_depth=max_depth,
        show_file_sizes=show_sizes,
        ignore_patterns=ignore_pats,
        use_icons=use_icons,
        use_colors=use_colors,
        sort_by=sort_by,
        export_format=fmt,
        output_path=output_path,
    )

    # ── Build & display rich tree ─────────────────────────────────────────────
    console.print()
    console.print(Rule("[bold bright_blue]Directory Tree[/bold bright_blue]", style="bright_blue"))
    console.print()

    rich_tree, stats = build_rich_tree(options)
    console.print(rich_tree)

    # ── Summary + breakdown ───────────────────────────────────────────────────
    console.print(Rule("[bold green]Summary[/bold green]", style="green"))
    render_summary(options, stats, output_path)

    # ── Plain-text (used for export) ─────────────────────────────────────────
    plain_tree, _ = generate_plain_tree(options)

    # ── Export ────────────────────────────────────────────────────────────────
    if output_path:
        suffix = output_path.suffix.lower()
        if suffix == ".md":
            content = to_markdown(plain_tree, options.root)
        else:
            content = plain_tree

        save_output(content, output_path)
        console.print(f"\n[bold green]✔  Saved:[/bold green] {output_path}")

    console.print()
    console.print(Panel.fit(
        f"[bold green]Done.[/bold green]  "
        f"[dim]{stats.folders} dirs · {stats.files} files · "
        f"{format_bytes(stats.total_file_size)} · {stats.scan_time_ms:.0f} ms[/dim]",
        border_style="green",
        padding=(0, 2),
    ))
    console.print()


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        sys.exit(0)
