# ---- điều khiển từ điện thoại ----
CONTROL = 'wifi'             # 'wifi' = trang web trên điện thoại qua Wi-Fi | 'ble' = app Bluetooth
WIFI_MODE = 'ap'             # 'ap' = ESP32 TỰ PHÁT Wi-Fi (không cần Wi-Fi ngoài), web luôn ở http://192.168.4.1
                             # 'sta' = xe vào Wi-Fi điện thoại phát (4G hotspot) HOTSPOT_SSID bên dưới
AP_SSID = 'OOMWOO-XE'        # tên Wi-Fi xe phát (chế độ 'ap')
AP_PASS = '12345678'         # mật khẩu, >= 8 ký tự
AP_CHANNEL = 6               # kênh Wi-Fi 1..13 (đổi nếu chỗ demo nhiều Wi-Fi bị nhiễu)
WEB_NAME = 'rccar'           # tên dễ nhớ: http://local.rccar hoặc http://rccar.local (chế độ 'sta': chỉ http://rccar.local, nếu máy hỗ trợ)
HOTSPOT_SSID = 'TEN_WIFI_DIEN_THOAI'   # (chế độ 'sta') tên Điểm phát sóng của điện thoại - BẬT BĂNG TẦN 2.4 GHz
HOTSPOT_PASS = 'MAT_KHAU'              # (chế độ 'sta') mật khẩu hotspot

WIFI_WAIT_S = 20             # (chế độ 'sta') chờ vào Wi-Fi điện thoại tối đa bấy nhiêu giây lúc bật xe
AP_FALLBACK = True           # (chế độ 'sta') không vào được -> xe tự phát Wi-Fi AP_SSID như chế độ 'ap'
BLE_NAME = 'OOMWOO'          # (chỉ khi CONTROL = 'ble') tên Bluetooth của xe (app tìm và kết nối theo tên này). Tối đa ~20 ký tự, không dấu
AUTO_AT_BOOT = False         # True = vừa bật nguồn là tự chạy luôn (không cần điện thoại)
BLE_SPEED_PCT = 60           # tốc độ ban đầu (%), app chỉnh được 20..100
STOP_ON_DISCONNECT = True    # điện thoại mất kết nối khi đang TỰ CHẠY -> xe dừng + về LÁI TAY
PIN_MODE_BUTTON = 0          # nút BOOT trên mạch ESP32-S3 (GPIO0): nhấn = đổi TỰ CHẠY <-> LÁI TAY. None = không dùng

# ---- lái tay ----
PWM_MAX = 100                # % PWM khi thanh Tốc độ = 100% và đẩy hết cần = HẾT CÔNG SUẤT động cơ (giảm nếu xe quá bốc / pin sụt)
MANUAL_HOLD_MS = 600         # thả nút / mất sóng: xe dừng sau bấy nhiêu ms không nhận lệnh

# ---- tự chạy lung tung ----
WANDER_SPEED = 0.20          # m/s tốc độ tự chạy ở 60% (app tăng/giảm theo tỉ lệ)
WANDER_TURN_SPEED = 1.3      # rad/s xoay tại chỗ khi gặp vật cản
WANDER_HALF_WIDTH = 0.21     # m: nửa bề ngang xe (tính cả bánh) + khe hở mỗi bên. Xe hay quẹt tường -> tăng
WANDER_STOP_DIST = 0.36      # m (tính từ tâm LiDAR): phía trước gần hơn thì dừng tiến và xoay tìm lối
WANDER_CLEAR_DIST = 0.75     # m: xoay tới khi phía trước trống ít nhất bấy nhiêu
WANDER_SIDE_MIN = 0.26       # m (tính từ tâm): tường bên hông gần hơn -> trượt ngang ra
WANDER_NEAR_R = 0.22         # m: vật gần tâm xe hơn -> trượt ra xa trước khi xoay (tránh quẹt góc xe)
WANDER_STRAIGHT = 0.5        # phía trước còn thoáng thì ưu tiên đi thẳng (lớn hơn = ít lượn vòng hơn, 0 = lượn tự do)
AUTO_SELF_CHECK = True       # lần đầu TỰ CHẠY sau khi bật: tự thử xoay/tiến/trượt ~5 s, LiDAR phát hiện xe xoay ngược,
                             # LiDAR lắp lệch/quay ngược -> tự sửa khi chạy + in cách sửa hẳn trong config.py (xem nhật ký)

# ---- phanh an toàn (cả lái tay lẫn tự chạy) ----
BLE_BRAKE_DIST_MM = 260      # mm (từ tâm LiDAR): vật cản gần hơn (+ quãng phanh theo tốc độ) thì xe không tiến về phía đó nữa
