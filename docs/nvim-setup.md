# Neovim + NvChad Setup

## What it is

**Neovim** is a modern, terminal-native text editor — a refactored fork of Vim with an async plugin API and Lua scripting.

**NvChad** (v2.5) is a curated Neovim configuration framework that layers on top of Neovim to give it IDE-level features: a polished UI, file tree, fuzzy finder, git integration, LSP autocomplete, and a large library of themes — all pre-wired and working out of the box.

Under the hood NvChad uses **lazy.nvim** as its plugin manager: plugins load on demand so startup stays fast.

Current install: Neovim v0.12.2, NvChad v2.5, theme: `onedark`.

---

## Installation

### Prerequisites

```bash
# Homebrew (macOS)
brew install neovim
brew install ripgrep   # used by Telescope live grep — must be brew-installed, not just bundled with another tool
brew install fd        # used by Telescope file finder
brew install git
# A Nerd Font is required for icons — install one and set it in your terminal
brew install --cask font-jetbrains-mono-nerd-font
```

### Install NvChad

```bash
# Back up any existing config first
mv ~/.config/nvim ~/.config/nvim.bak 2>/dev/null

# Clone the NvChad starter
git clone https://github.com/NvChad/starter ~/.config/nvim

# Launch nvim — lazy.nvim bootstraps itself, then downloads all plugins
nvim
```

On first launch Neovim will install everything automatically. When the progress window says `Done`, restart nvim.

### Config location

```
~/.config/nvim/
├── init.lua              # entry point
├── lazy-lock.json        # pinned plugin versions
└── lua/
    ├── chadrc.lua        # your NvChad overrides (theme, UI tweaks)
    ├── mappings.lua      # your custom keymaps
    ├── options.lua       # your editor options
    ├── autocmds.lua      # your autocommands
    ├── configs/          # plugin-specific config files
    └── plugins/          # plugins you add beyond NvChad defaults
        └── init.lua
```

---

## How it works — key components

| Component | What it does |
|---|---|
| **lazy.nvim** | Plugin manager — lazy-loads plugins by event/filetype/command |
| **base46** | Theme engine — swap themes with `Space th` |
| **nvim-tree** | File explorer sidebar |
| **Telescope** | Fuzzy finder for files, grep, buffers, git, etc. |
| **nvim-cmp** | Autocompletion engine |
| **nvim-lspconfig** | Connects language servers for diagnostics and go-to-def |
| **mason.nvim** | Installs LSP servers, formatters, linters |
| **gitsigns.nvim** | Git blame, hunk navigation, diff signs in gutter |
| **which-key.nvim** | Shows available keybindings as you type a prefix |
| **nvim-treesitter** | Syntax highlighting and code structure parsing |
| **conform.nvim** | Code formatting on save |
| **indent-blankline** | Visual indent guides |

---

## Walkthrough

This section walks through everything you need for the read-side workflow, in the order you should learn it.

### Step 1 — Open nvim

```bash
nvim .
```

You land in a blank buffer. The file tree is hidden by default.

### Step 2 — Open the file tree

Press `Ctrl-n` to toggle the file tree on the left. Use `j`/`k` to move up and down, then `Enter` to open a file.

> **Note:** `Ctrl-w l` (letter L) moves your cursor from the tree into the file panel. `Ctrl-w h` moves back left. This is how you switch between any panels in nvim.

### Step 3 — Read a file

Once a file is open, you're in **normal mode** (the default). You cannot type — normal mode is for navigation. Everything below assumes normal mode. If you're ever unsure, press `Escape` to get back to it.

**Scrolling:**

| Key | Action |
|---|---|
| `Ctrl-f` | Scroll forward one full page |
| `Ctrl-b` | Scroll back one full page |
| `Ctrl-d` | Scroll down half a page |
| `Ctrl-u` | Scroll up half a page |
| `gg` | Jump to top of file |
| `G` | Jump to bottom of file |

**Line wrap** — long lines extend off-screen by default. Fix it with:

```vim
:set wrap
```

Type `:` (a command prompt appears at the bottom), then `set wrap`, then `Enter`. To turn it off: `:set nowrap`.

> You must be in the file panel (not the tree) for `:set wrap` to work. If it says "unknown option", press `Ctrl-w l` to move into the file first.

### Step 4 — Search within a file

Press `/` then type any word and hit `Enter`. Nvim jumps to the first match and highlights all others.

| Key | Action |
|---|---|
| `/pattern` | Search forward |
| `?pattern` | Search backward |
| `n` | Next match |
| `N` | Previous match |
| `Escape` or `:noh` | Clear highlights |

### Step 5 — Find any file by name (Telescope)

Press `Space ff`. A fuzzy finder popup appears. Start typing any part of a filename — the list filters live.

**Inside any Telescope popup:**

| Key | Action |
|---|---|
| type anything | filter the list |
| `Ctrl-n` or `↓` | move down the list |
| `Ctrl-p` or `↑` | move up the list |
| `Enter` | open selected item |
| `Ctrl-c` or `Escape` | close without opening |

> `j`/`k` do NOT work while the search box is active — use `Ctrl-n`/`Ctrl-p` or the arrow keys.

### Step 6 — Switch between open files (buffers)

Every file you open stays in memory as a buffer. The buffer tabs are shown at the top of the screen.

| Key | Action |
|---|---|
| `Tab` | Next buffer |
| `Shift-Tab` | Previous buffer |
| `Space x` | Close current buffer |

### Step 7 — Grep across the whole repo

Press `Space fw`. A Telescope popup opens where you can type any word and it searches every file in the repo live. Navigate with `Ctrl-n`/`Ctrl-p`, press `Enter` to jump directly to that line in that file.

Requires `ripgrep` installed via brew (`brew install ripgrep`).

### Step 8 — Git status and diffs

`Space gt` opens a Telescope list of all files with uncommitted changes. Navigate to a file and press `Enter` to open it.

With a changed file open:

| Key | Action |
|---|---|
| `]c` | Jump to next changed hunk |
| `[c` | Jump to previous changed hunk |
| `Space ph` | Preview the diff for the hunk under cursor |
| `Space gb` | Toggle inline git blame for current line |

`Space cm` opens the git commit history in Telescope — useful for browsing what changed across commits.

### Step 9 — Quit

```vim
:q       " quit
:q!      " quit without saving (force)
:wq      " save and quit
```

---

## Cheatsheet

### File tree

| Key | Action |
|---|---|
| `Ctrl-n` | Toggle file tree |
| `Enter` | Open file |
| `a` | New file |
| `d` | Delete file |
| `r` | Rename file |

### Telescope (fuzzy finder)

| Key | Action |
|---|---|
| `Space ff` | Find file by name |
| `Space fo` | Recent files |
| `Space fw` | Live grep across project |
| `Space fb` | List open buffers |
| `Space gt` | Git status |
| `Space cm` | Git commits |
| `Ctrl-n` / `↓` | Move down in list |
| `Ctrl-p` / `↑` | Move up in list |
| `Enter` | Open selection |
| `Escape` | Close |

### Buffers and panels

| Key | Action |
|---|---|
| `Tab` | Next buffer |
| `Shift-Tab` | Previous buffer |
| `Space x` | Close buffer |
| `Ctrl-w l` | Move cursor right (into file panel) |
| `Ctrl-w h` | Move cursor left (into tree) |
| `Ctrl-w v` | Split vertically |
| `Ctrl-w s` | Split horizontally |

### Scrolling

| Key | Action |
|---|---|
| `Ctrl-f` | Full page forward |
| `Ctrl-b` | Full page back |
| `Ctrl-d` | Half page down |
| `Ctrl-u` | Half page up |
| `gg` | Top of file |
| `G` | Bottom of file |

### Search

| Key | Action |
|---|---|
| `/pattern` | Search forward |
| `?pattern` | Search backward |
| `n` / `N` | Next / previous match |
| `Escape` or `:noh` | Clear highlights |

### Git

| Key | Action |
|---|---|
| `Space gt` | Git status (Telescope) |
| `Space cm` | Git commits (Telescope) |
| `]c` / `[c` | Next / previous hunk |
| `Space ph` | Preview hunk diff |
| `Space gb` | Toggle git blame |

### LSP (when a language server is active)

| Key | Action |
|---|---|
| `gd` | Go to definition |
| `gr` | List references |
| `K` | Hover docs |
| `Space ca` | Code action |
| `Space fm` | Format file |
| `[d` / `]d` | Previous / next diagnostic |

---

## How I use it — split terminal workflow

The intended workflow is a permanent vertical split in the terminal:

```
┌─────────────────────┬─────────────────────┐
│   Claude Code CLI   │       nvim          │
│                     │                     │
│  (left pane)        │  (right pane)       │
└─────────────────────┴─────────────────────┘
```

**Claude Code (left)** does all writing, running commands, and generating code.

**nvim (right)** is the read-side companion:

- **Browse repo files** — `Ctrl-n` to open the tree, navigate what Claude Code just produced
- **View git diffs** — `Space gt` to see changed files, `Space ph` to preview hunks
- **Check commit history** — `Space cm` to browse commits in Telescope
- **Read Markdown docs** — open any `.md` file; treesitter syntax highlights it cleanly; `:set wrap` for long lines
- **Search across the repo** — `Space fw` to live-grep for a symbol, function name, or string Claude mentioned
- **Find any file fast** — `Space ff` to jump to any file by fuzzy name

Nvim stays open — no need to quit between sessions. After Claude Code writes new files, press `Ctrl-n` to refresh the tree (close and reopen it).

### Useful aliases to add to `.zshrc`

```bash
alias v='nvim'
alias vd='nvim -d'        # vimdiff two files: vd file1 file2
alias vr='nvim -R'        # read-only view
```
