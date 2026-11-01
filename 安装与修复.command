#!/bin/zsh
set -eu
cd "${0:A:h}"
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1
INSTALL_DATA="${TRANSLATOR_DATA_DIR:-$HOME/Library/Application Support/NewsBridge}"
FORCE_BUNDLED=0
for INSTALL_ARG in "$@"; do
  if [[ "$INSTALL_ARG" == --refresh-runtime ]]; then FORCE_BUNDLED=1; fi
done
if [[ "$(/usr/bin/uname -s)" != Darwin || "$(/usr/bin/uname -m)" != arm64 ]]; then
  echo '当前测试安装包适用于 Apple 芯片 Mac。Intel、Windows 版尚未验收。'
  exit 1
fi
if [[ "$FORCE_BUNDLED" == 0 && -x "$INSTALL_DATA/runtime/bin/python3" ]] && "$INSTALL_DATA/runtime/bin/python3" -I -c 'import ssl,jwt,cryptography,youtube_transcript_api;from cryptography.hazmat.primitives.asymmetric import rsa' >/dev/null 2>&1; then
  exec "$INSTALL_DATA/runtime/bin/python3" -I "$PWD/setup_installer.py" "$@"
fi
# The verified standalone interpreter removes the need for Xcode/system Python.
BOOTSTRAP="$INSTALL_DATA/python-3.12.16"
if [[ ! -x "$BOOTSTRAP/python/bin/python3" ]] || ! "$BOOTSTRAP/python/bin/python3" -I -c 'import ssl,json,venv,hashlib' >/dev/null 2>&1; then
  if [[ -d "$BOOTSTRAP" ]]; then
    BOOTSTRAP="$INSTALL_DATA/python-3.12.16-repair-$$"
  fi
  mkdir -p "$INSTALL_DATA/downloads"
  ARCHIVE="$PWD/assets/python-arm64.tar.gz"
  if [[ ! -f "$ARCHIVE" ]]; then
    ARCHIVE="$INSTALL_DATA/downloads/python-arm64.tar.gz"
    URL=$(/usr/bin/plutil -extract url raw -o - packaging/runtime.json)
    echo '正在获取独立运行组件…'
    /usr/bin/curl --fail --location --retry 2 --connect-timeout 15 --max-time 240 --output "$ARCHIVE.part" "$URL"
    mv "$ARCHIVE.part" "$ARCHIVE"
  fi
  EXPECTED=$(/usr/bin/plutil -extract sha256 raw -o - packaging/runtime.json)
  ACTUAL=$(/usr/bin/shasum -a 256 "$ARCHIVE" | /usr/bin/cut -d ' ' -f 1)
  if [[ "$EXPECTED" != "$ACTUAL" ]]; then
    echo '运行组件校验未通过，未执行安装。请重新解压原始安装包。'
    exit 1
  fi
  mkdir -p "$BOOTSTRAP"
  /usr/bin/tar -xzf "$ARCHIVE" -C "$BOOTSTRAP"
fi
# -I excludes the source folder, so the Python entry adds only its own directory.
exec "$BOOTSTRAP/python/bin/python3" "$PWD/setup_installer.py" "$@"
