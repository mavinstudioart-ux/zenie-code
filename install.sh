#!/usr/bin/env sh
set -eu

WITH_TREE_SITTER=0
DEV=0

for arg in "$@"; do
  case "$arg" in
    --with-tree-sitter) WITH_TREE_SITTER=1 ;;
    --dev) DEV=1 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INSTALL_ROOT="${ZENIE_INSTALL_ROOT:-$HOME/.zenie/app}"
VENV_ROOT="$INSTALL_ROOT/venv"
BIN_DIR="${ZENIE_BIN_DIR:-$HOME/.local/bin}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.11 or newer is required." >&2
  exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit(f"Python 3.11+ required; found {sys.version.split()[0]}")
PY

mkdir -p "$INSTALL_ROOT" "$BIN_DIR"

if [ ! -x "$VENV_ROOT/bin/python" ]; then
  python3 -m venv "$VENV_ROOT"
fi

"$VENV_ROOT/bin/python" -m pip install --upgrade pip

if [ "$DEV" -eq 1 ]; then
  "$VENV_ROOT/bin/python" -m pip install -e "$REPO_ROOT[dev]"
elif [ "$WITH_TREE_SITTER" -eq 1 ]; then
  "$VENV_ROOT/bin/python" -m pip install "$REPO_ROOT[treesitter]"
else
  "$VENV_ROOT/bin/python" -m pip install --upgrade "$REPO_ROOT"
fi

cat > "$BIN_DIR/zenie" <<EOF
#!/usr/bin/env sh
exec "$VENV_ROOT/bin/python" -m zenie_code.cli "\$@"
EOF
chmod +x "$BIN_DIR/zenie"

echo
echo "Zenie Code installed successfully."
echo "Run: zenie"
echo "Ensure $BIN_DIR is in PATH."
