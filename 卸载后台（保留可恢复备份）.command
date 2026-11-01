#!/bin/zsh
cd "${0:A:h}"
RUNTIME="$HOME/Library/Application Support/NewsBridge/runtime/bin/python3"
if [[ ! -x "$RUNTIME" ]]; then
  echo '未找到已安装的后台，无需卸载。'
  exit 0
fi
exec "$RUNTIME" "$PWD/uninstall.py" --execute
