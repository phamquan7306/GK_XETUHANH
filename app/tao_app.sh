#!/bin/bash
# OOMWOO: tạo app Android (project App Inventor .aia) rồi mở trang App Inventor để build ra .apk
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1
NAME=$(grep -E "^BLE_NAME" "$DIR/../esp32/giuaky_config.py" 2>/dev/null | head -1 | sed -E "s/.*['\"]([^'\"]*)['\"].*/\1/")
[ -z "$NAME" ] && NAME=OOMWOO
echo "Tên Bluetooth của xe (BLE_NAME trong esp32/giuaky_config.py): $NAME"
if python3 tao_app.py --ten-xe "$NAME"; then
  echo
  echo "Bước tiếp theo (làm trên trình duyệt vừa mở):"
  echo "  1) Đăng nhập ai2.appinventor.mit.edu bằng tài khoản Google"
  echo "  2) Projects -> Import project (.aia) from my computer -> chọn $DIR/OomwooBLE.aia"
  echo "  3) Build -> Android App (.apk) -> quét mã QR bằng điện thoại (hoặc tải .apk rồi chép sang điện thoại) -> cài"
  echo "  4) Mở app, cho phép Bluetooth + Vị trí (Nearby devices), bật xe, bấm KẾT NỐI XE"
  xdg-open "https://ai2.appinventor.mit.edu" >/dev/null 2>&1 &
  xdg-open "$DIR" >/dev/null 2>&1 &
fi
echo; read -n1 -r -p "Nhấn phím bất kỳ để đóng..."
