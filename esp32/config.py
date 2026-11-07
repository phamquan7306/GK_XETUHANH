from micropython import const
import math

PIN_ENC_FL = const(7)
PIN_ENC_FR = const(6)
PIN_ENC_RL = const(5)
PIN_ENC_RR = const(4)

# PWM motor
PIN_FL_IN1 = const(21); PIN_FL_IN2 = const(47)
PIN_FR_IN1 = const(40); PIN_FR_IN2 = const(39)
PIN_RL_IN1 = const(45); PIN_RL_IN2 = const(48)
PIN_RR_IN1 = const(2);  PIN_RR_IN2 = const(1)
PWM_DEINIT_LIST = (47, 21, 48, 45, 40, 39, 38, 1, 2)
PWM_FREQ = const(1000)

# MOTOR DIR
SIGN_FL = const(-1)
SIGN_FR = const(1)
SIGN_RL = const(-1)
SIGN_RR = const(1)

# MPU
PIN_I2C_SCL = const(42)
PIN_I2C_SDA = const(41)
I2C_FREQ    = const(400000)
MPU_ADDR    = const(0x68)
MPU_REG_PWR = const(0x6B)
MPU_REG_GZ  = const(0x47)

# LIDAR
PIN_LIDAR_EN = const(14)
PIN_LIDAR_TX = const(17)
PIN_LIDAR_RX = const(18)
LIDAR_BAUD   = const(115200)

# MECANUM WHEEL
WHEEL_RADIUS = 0.034
WHEEL_DIAMETER = 0.068
PPR          = const(20)
METERS_PER_TICK = (2 * math.pi * WHEEL_RADIUS) / PPR

MECANUM_LX = 0.146
MECANUM_LY = 0.116
MECANUM_L_SUM = MECANUM_LX + MECANUM_LY

# TỐC ĐỘ & KALMAN / EKF
DEFAULT_SPEED_LIMIT = const(55)
MIN_EFFECTIVE_PWM   = const(30)   # % PWM nhỏ nhất làm bánh BẮT ĐẦU quay. Bánh kêu "i i" mà đứng yên = số này còn thấp. Chỉnh trực tiếp bằng phím [ ] trên Ubuntu rồi ghi lại số đúng vào đây
SLEW_RATE_STEP      = const(12)         # chỉ dùng khi tắt PID (chạy hở)

# PID tốc độ từng bánh (vòng kín bằng encoder). PWM = tiến liệu (vùng chết MIN_EFFECTIVE_PWM..DEFAULT_SPEED_LIMIT) + Kp*sai số + Ki*tích phân.
# Chỉnh trực tiếp lúc xe chạy bằng phím trên Ubuntu (v: bật/tắt, t/g: Kp, y/h: Ki), ưng ý thì ghi số vào đây rồi bấm "Nạp ESP32".
PID_ENABLE = True
PID_KP = 0.15             # % PWM cộng thêm cho mỗi 1% sai số tốc độ (so với MAX_WHEEL_MPS) x100. Lớn quá -> xe rung/giật
PID_KI = 1.0              # 1/giây. Lớn hơn -> bù lệch nhanh hơn nhưng dễ dao động
PID_ACCEL = 1.5           # m/s^2: gia tốc tối đa của tốc độ đặt từng bánh (giảm tốc nhanh gấp 2.5). Nhỏ hơn -> xe êm hơn, phản ứng chậm hơn
ENC_DEBOUNCE_US     = const(2500)

KF_ENC_Q = 0.03
KF_ENC_R = 15

EKF_MPU_Q = 0.05
EKF_MPU_R = 0.50
GYRO_DEADZONE_DEG = 0.20
ENC_BASE_R = 0.25
SLIP_PENALTY_GAIN = 5.0

KP_HEADING_HOLD = 18.0

# An toàn cứng ở phía xe (độc lập với PC): lệnh đi về hướng nào mà LiDAR thấy vật cản gần hơn
# SAFE_STOP_DIST_MM thì xe tự dừng phần tịnh tiến (vẫn cho xoay). PC đã tự giữ >= 0.24 m nên để 180.
SAFE_STOP_DIST_MM = const(180)
WARN_SLOW_DIST_MM = const(400)
HW_SAFETY    = True          # False = tắt phanh an toàn phía xe
HW_SLOWDOWN  = False         # True = giảm tốc dần trong vùng SAFE_STOP..WARN_SLOW (xe sẽ chậm trong lối hẹp)

# ---------------------------------------------------------------------
#  MỚI: NÂNG CẤP SLAM (gửi dữ liệu thô về Ubuntu, Ubuntu tự vẽ map + lái)
# ---------------------------------------------------------------------
# [KIỂM TRA] Chiều dương của các cảm biến / cơ cấu. Nếu bản đồ bị lật gương hoặc xe đi lệch
# so với bản đồ thì đảo dấu ở đây (xem README "Chạy thử lần đầu").
GYRO_SIGN = 1                # +1: xe quay NGƯỢC chiều kim đồng hồ (nhìn từ trên) thì gyro dương. Ngược lại đặt -1
VY_SIGN = 1                  # +1: lệnh trượt ngang dương = trượt sang TRÁI. Nếu thấy ngược thì đặt -1
W_SIGN = 1                   # +1: lệnh xoay dương = xoay NGƯỢC chiều kim đồng hồ. Nếu thấy ngược thì đặt -1

# [KIỂM TRA] LiDAR YDLidar: góc tăng theo chiều KIM ĐỒNG HỒ, ROS cần NGƯỢC chiều kim đồng hồ.
LIDAR_CLOCKWISE = True
LIDAR_ANGLE_OFFSET_DEG = 0   # 0° của LiDAR lệch so với mũi xe bao nhiêu độ (dương = ngược chiều kim đồng hồ)
LIDAR_MIN_MM = 120
LIDAR_MAX_MM = 8000          # X2: 8000, X4: 10000
LIDAR_ANGLE_CORRECT = True   # bù góc theo khoảng cách (YDLidar X2/X4). Tắt nếu LiDAR của bạn không cần
LIDAR_CHECKSUM = True        # kiểm tra checksum gói tin; tự tắt nếu 30 gói đầu đều sai

# [KIỂM TRA] Tốc độ bánh (m/s) đạt được khi PWM = DEFAULT_SPEED_LIMIT%. Đo: cho xe chạy thẳng 2 s ở
# lệnh vx = MAX_WHEEL_MPS rồi xem /odom đi được bao nhiêu mét, chỉnh lại cho khớp.
MAX_WHEEL_MPS = 0.40

# Giao thức UDP
CMD_TIMEOUT_MS = const(500)  # quá thời gian này không có lệnh từ PC thì xe tự dừng
ODOM_PERIOD_MS = const(20)   # gửi encoder + gyro 50 Hz
GYRO_PERIOD_MS = const(10)   # đọc gyro 100 Hz
CFG_PERIOD_MS  = const(2000) # gửi thông số cho PC mỗi 2 s
SCAN_MIN_PERIOD_MS = const(80)

# CẤU HÌNH WI-FI & GIAO THỨC UDP (CHO ROS 2 / RVIZ2)
WIFI_SSID   = "TEN_WIFI"      # (chỉ bản cuối kỳ) Tên Wi-Fi băng tần 2.4GHz
WIFI_PASS   = "MAT_KHAU"      # (chỉ bản cuối kỳ) Mật khẩu Wi-Fi
PC_IP       = "192.168.1.100" # (chỉ bản cuối kỳ) IP máy tính Ubuntu

UDP_PORT_TX = const(8888)
UDP_PORT_RX = const(8889)
