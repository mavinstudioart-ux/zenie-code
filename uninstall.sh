#!/usr/bin/env sh
set -eu
rm -f "${ZENIE_BIN_DIR:-$HOME/.local/bin}/zenie"
rm -rf "${ZENIE_INSTALL_ROOT:-$HOME/.zenie/app}"
echo "Zenie Code runtime removed."
echo "Model profiles and user config remain in $HOME/.zenie"
