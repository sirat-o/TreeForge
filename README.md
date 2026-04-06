# 📦 TreeForge

> **Advanced interactive directory tree tool** — visualise, analyse, and export your project structure with a beautiful terminal UI.

---

## ✨ Features

- 🌲 **Rich interactive tree** — colour-coded, emoji-icon file tree rendered with [Rich](https://github.com/Textualize/rich)
- 🔍 **Smart filtering** — skip hidden files, `node_modules`, build artefacts, `.git`, and more via glob-pattern ignore lists
- 📊 **Inline statistics** — folder/file/symlink counts, total size, and scan time displayed side by side with a top-10 file-type breakdown
- 🔀 **Flexible sorting** — sort entries by name, size, extension, or last-modified date
- 💾 **Export** — save your tree as plain TXT or Markdown
- ⚙️ **Persistent config** — settings are saved to `~/.treeforgerc` and reloaded on next run
- 🎨 **Fully customisable** — toggle icons, colours, file sizes, hidden files, depth limit, and ignore patterns interactively

---

## 🖥️ Requirements

- Python **3.10+**
- Dependencies:

```
rich
questionary
```

---

## 🚀 Installation

```bash
# 1. Clone the repo
git clone https://github.com/sirat-o/TreeForge.git
cd treeforge

# 2. Install dependencies
pip install rich questionary

# 3. Run
python main.py
```

---

## 🎮 Usage

Simply run the script — TreeForge will walk you through all options interactively:

```bash
python main.py
```

You will be prompted to configure:

| Prompt | Description |
|---|---|
| 📂 Project folder | Path to the directory you want to visualise |
| 👁 Show hidden files | Include dotfiles and hidden directories |
| 📁 Directories only | Show folders without files |
| ⚖️ Show file sizes | Display size next to each file |
| 🎨 Use file-type icons | Emoji icons per file extension |
| 🌈 Use syntax colours | Colour each file by type |
| 🔀 Sort entries by | `name` / `size` / `ext` / `modified` |
| ↕️ Limit max depth | Restrict how deep the tree goes |
| 🚫 Edit ignore patterns | Customise glob patterns to skip |
| 💾 Export format | Preview only / Save as TXT / Save as Markdown |

---

## 📤 Export Formats

| Format | Description |
|---|---|
| Preview only | Displays tree in the terminal only |
| Save as TXT | Saves plain-text tree to a `.txt` file |
| Save as Markdown | Wraps the tree in a fenced code block inside a `.md` file |

---

## 🚫 Default Ignore Patterns

TreeForge automatically skips these by default (editable at runtime):

```
.git  .next  node_modules  dist  build
__pycache__  .venv  venv  .env
.idea  .vscode  .turbo  .cache
.DS_Store  *.pyc  *.pyo  *.egg-info
*.log  .pytest_cache  coverage
```

---

## 🎨 File-Type Icons & Colours

TreeForge maps over 50 file extensions to emoji icons and Rich colours, including:

| Category | Extensions |
|---|---|
| 🐍 Python | `.py` |
| 🟨 JavaScript / 🔷 TypeScript | `.js` `.ts` `.jsx` `.tsx` |
| 🐹 Go / 🦀 Rust / ☕ Java | `.go` `.rs` `.java` |
| 🌐 Web | `.html` `.css` `.scss` `.sass` |
| 📋 Config / Data | `.json` `.yaml` `.toml` `.xml` `.csv` |
| 📝 Docs | `.md` `.txt` `.rst` `.pdf` |
| 🖼️ Images | `.png` `.jpg` `.svg` `.webp` |
| 📦 Archives | `.zip` `.tar` `.gz` `.rar` |
| 🐚 Shell | `.sh` `.bash` `.zsh` `.fish` |

---

---

## 🛠️ Built With

- [Rich](https://github.com/Textualize/rich) — terminal rendering (tree, tables, panels, progress)
- [questionary](https://github.com/tmbo/questionary) — interactive CLI prompts

---

