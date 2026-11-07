DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$DIR/esp32"
MONITOR_ONLY=0; PORT=""
for a in "$@"; do case "$a" in --monitor) MONITOR_ONLY=1 ;; *) PORT="$a" ;; esac; done

MPR=$(command -v mpremote || true)
[ -z "$MPR" ] && [ -x "$HOME/.local/bin/mpremote" ] && MPR="$HOME/.local/bin/mpremote"
if [ -z "$MPR" ]; then
  echo "Chưa có mpremote, đang cài..."
  python3 -m pip install --user -q mpremote 2>/dev/null || python3 -m pip install --user -q --break-system-packages mpremote
  [ -x "$HOME/.local/bin/mpremote" ] && MPR="$HOME/.local/bin/mpremote"
fi
if [ -z "$MPR" ]; then echo "Không cài được mpremote. Thử:  pipx install mpremote"; read -n1 -r -p "Nhấn phím bất kỳ..."; exit 1; fi

[ -z "$PORT" ] && PORT=$(ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | head -1)
if [ -z "$PORT" ]; then
  echo "Không thấy ESP32 (cắm cáp USB data, không phải cáp chỉ sạc)."
  read -n1 -r -p "Nhấn phím bất kỳ..."; exit 1
fi
if [ ! -r "$PORT" ] || [ ! -w "$PORT" ]; then
  echo "Không có quyền mở $PORT. Chạy một lần rồi ĐĂNG XUẤT / ĐĂNG NHẬP lại:  sudo usermod -aG dialout $USER"
  read -n1 -r -p "Nhấn phím bất kỳ..."; exit 1
fi
echo "ESP32 ở cổng: $PORT"

if [ $MONITOR_ONLY = 0 ]; then
  echo "Nạp XE GIỮA KỲ (LiDAR tránh vật cản + điều khiển qua Wi-Fi)..."
  for f in "$SRC"/*.py; do
    printf "  %-20s" "$(basename "$f")"
    if "$MPR" connect "$PORT" fs cp "$f" ":$(basename "$f")" >/dev/null 2>&1; then echo "OK"; else echo "LỖI"; FAIL=1; fi
  done
  if [ -n "$FAIL" ]; then
    echo "Có file nạp lỗi. Cổng $PORT đang bị kết nối"
    read -n1 -r -p "Nhấn phím bất kỳ..."; exit 1
  fi
  echo "Nạp xong."
  echo ">>> Ctrl+D - softreset."
  echo ">>> Web-IP http://192.168.4.1"
  echo ">>> Thoát nhật ký: Ctrl+]"
fi
"$MPR" connect "$PORT" repl
