#!/usr/bin/env bash
# Put a "Little Chits" shortcut on the desktop. Run it again any time to repair or update the shortcuts.
#   Linux desktop: a .desktop icon on the desktop and in the app menu.
#   WSL (Windows): "Little Chits" and "Stop Little Chits" shortcuts on the *Windows* desktop. Their files live
#   in %LOCALAPPDATA%\LittleChits and call ~/.local/share/little-chits/desktop.sh inside WSL, which finds this
#   folder and runs scripts/desktop.sh (so they survive reboots, `git pull` and moving the folder).
# Usage: scripts/install-shortcut.sh [port]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8010}"
chmod +x "$ROOT/scripts/launch.sh" "$ROOT/scripts/desktop.sh"

if grep -qi microsoft /proc/version 2>/dev/null; then
  winps() { powershell.exe -NoProfile -NonInteractive -Command "$1" 2>/dev/null | tr -d '\r'; }
  WIN_LOCAL="$(winps '[Environment]::GetFolderPath("LocalApplicationData")')"
  if [ -z "$WIN_LOCAL" ]; then
    echo "Couldn't reach Windows (is powershell.exe reachable from WSL?)"
    exit 1
  fi
  WIN_DIR="$WIN_LOCAL\\LittleChits"
  DIR="$(wslpath "$WIN_LOCAL")/LittleChits"
  SHIM="$HOME/.local/share/little-chits/desktop.sh"

  # the WSL side: a small script at a fixed path that remembers where this folder is
  install -D -m 755 "$ROOT/scripts/windows/desktop-shim.sh" "$SHIM"
  mkdir -p "$HOME/.config/little-chits"
  echo "$ROOT" >"$HOME/.config/little-chits/repo"

  # the Windows side: the progress window, its icons and settings, and two silent starters
  mkdir -p "$DIR"
  cp "$ROOT/scripts/windows/LittleChits.ps1" "$ROOT/scripts/windows/install.ps1" "$DIR/"
  cp "$ROOT/docs/icon.ico" "$DIR/icon.ico"
  cp "$ROOT/docs/icon-stop.ico" "$DIR/icon-stop.ico"
  printf '{"distro": "%s", "shim": "%s", "port": %s}\r\n' "$WSL_DISTRO_NAME" "$SHIM" "$PORT" >"$DIR/config.json"
  for action in start stop; do
    printf '%s\r\n' \
      "' Runs LittleChits.ps1 -Action $action with no console window. Installed by \`make shortcut\`." \
      'Set fso = CreateObject("Scripting.FileSystemObject")' \
      'here = fso.GetParentFolderName(WScript.ScriptFullName)' \
      "CreateObject(\"WScript.Shell\").Run \"powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"\"\" & here & \"\\LittleChits.ps1\"\" -Action $action\", 0, False" \
      >"$DIR/$action.vbs"
  done
  WIN_DESK="$(powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$WIN_DIR\\install.ps1" -Dir "$WIN_DIR" | tr -d '\r' | tail -1)"
  if [ -z "$WIN_DESK" ]; then
    echo "Couldn't create the desktop shortcuts (see the message above)."
    exit 1
  fi

  echo "Added 'Little Chits' and 'Stop Little Chits' to your Windows desktop ($WIN_DESK)."
  echo "Their files are in $WIN_DIR; WSL runs $SHIM"
  if [ ! -f "$HOME/start-gpus.sh" ]; then
    cp "$ROOT/scripts/start-gpus.example.sh" "$HOME/start-gpus.sh"
    chmod +x "$HOME/start-gpus.sh"
    echo
    echo "Also created ~/start-gpus.sh, which the shortcut uses to start your model servers."
    echo "Put your model files in it once (docs/GPU_SETUP.md, 'Desktop shortcut'):  nano ~/start-gpus.sh"
  else
    echo "Model servers: the shortcut starts them with ~/start-gpus.sh"
  fi
  echo
  echo "Double-click 'Little Chits': a small window shows each step, then your browser opens http://localhost:$PORT"
  exit 0
fi

ICON="$ROOT/docs/icon.svg"
ENTRY="[Desktop Entry]
Type=Application
Name=Little Chits
Comment=Watch your AI civilisation grow
Exec=bash -c '\"$ROOT/scripts/launch.sh\" $PORT; sleep 3'
Icon=$ICON
Terminal=true
Categories=Game;Simulation;"
mkdir -p "$HOME/.local/share/applications"
echo "$ENTRY" >"$HOME/.local/share/applications/little-chits.desktop"
DESK="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
mkdir -p "$DESK"
echo "$ENTRY" >"$DESK/little-chits.desktop"
chmod +x "$DESK/little-chits.desktop" "$HOME/.local/share/applications/little-chits.desktop"
command -v gio >/dev/null && gio set "$DESK/little-chits.desktop" metadata::trusted true 2>/dev/null || true
echo "Added 'Little Chits' to $DESK and your applications menu (port $PORT)."
