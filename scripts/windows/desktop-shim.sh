#!/usr/bin/env bash
# Installed by `make shortcut` to ~/.local/share/little-chits/desktop.sh. The Windows desktop shortcuts run
# this by absolute path, so they keep working after `git pull` or if the Little Chits folder moves:
# it finds the folder (remembered in ~/.config/little-chits/repo) and runs its scripts/desktop.sh.
CONF="$HOME/.config/little-chits/repo"
REPO="$(cat "$CONF" 2>/dev/null)"
is_repo() { [ -f "$1/scripts/desktop.sh" ] && grep -qs '^name = "little-chits"' "$1/pyproject.toml"; }
if ! is_repo "$REPO"; then
  REPO=""
  for c in "$HOME/projects/little-chits" "$HOME/little-chits" \
           $(find "$HOME" -maxdepth 4 -path '*/scripts/desktop.sh' -not -path '*/node_modules/*' 2>/dev/null |
             sed 's#/scripts/desktop.sh$##'); do
    if is_repo "$c"; then REPO="$c"; break; fi
  done
  if [ -z "$REPO" ]; then
    echo "@fail repo Couldn't find the Little Chits folder. Open WSL, go into the folder and run: make shortcut"
    exit 1
  fi
  mkdir -p "$(dirname "$CONF")" && echo "$REPO" >"$CONF"
fi
exec bash "$REPO/scripts/desktop.sh" "$@"
