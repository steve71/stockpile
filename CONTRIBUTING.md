# Contributing to stockpile

Contributions are welcome. Since this is a public repo, anyone can
fork it and open a pull request — no special permissions needed.

## Requirements

- Python 3.12+. If you don't have it, let uv manage it:
  ```bash
  uv python install 3.12
  ```
- [uv](https://docs.astral.sh/uv/):
  ```bash
  # macOS / Linux
  curl -LsSf https://astral.sh/uv/install.sh | sh

  # Windows (PowerShell)
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

## Fork → PR workflow

1. **Fork the repo** on GitHub (top-right "Fork" button).

2. **Clone your fork** and create a branch:
   ```bash
   git clone https://github.com/<your-username>/stockpile.git
   cd stockpile
   uv sync
   git checkout -b my-feature
   ```

3. **Make your changes**, then push:
   ```bash
   git add <files>
   git commit -m "describe your change"
   git push origin my-feature
   ```

4. **Open a Pull Request** on GitHub. Set the base repository to
   `medloh/stockpile` and base branch to `main`.

5. The repo owner reviews, leaves comments if needed, and merges
   when ready.

## Adding dependencies

To add a package to a specific sub-project:

```bash
uv add plotly --project cost-basis-charts
```

Then run `uv sync` to update the lockfile. Prefer adding to the
narrowest sub-project that needs it — don't add to the root
`pyproject.toml` unless it's truly shared.

## Guidelines

- Keep PRs focused on one change — easier to review and less likely
  to conflict.
- If your branch falls behind `main`, rebase before opening the PR:
  ```bash
  git remote add upstream https://github.com/medloh/stockpile.git
  git fetch upstream
  git rebase upstream/main
  ```
- PRs that touch `shared/` affect all sub-projects — call that out
  in your PR description so it gets extra scrutiny.
- Always run via `uv run` from the repo root, never `python` directly.
