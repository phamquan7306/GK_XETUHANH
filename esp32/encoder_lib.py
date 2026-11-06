from machine import Pin
from array import array
import time
import config

# Biến đếm xung tuyệt đối (có dấu: cộng theo chiều đang lệnh cho bánh)
_xung_fl = 0; _xung_fr = 0; _xung_rl = 0; _xung_rr = 0
# Chiều quay hiện hành (-1, 0, 1)
_chieu_fl = 0; _chieu_fr = 0; _chieu_rl = 0; _chieu_rr = 0
# Chiều quay gần nhất trước khi ngắt điện (dùng để hứng xung quán tính khi phanh)
_last_active_fl = 1; _last_active_fr = 1; _last_active_rl = 1; _last_active_rr = 1
_stop_timestamp_ms = 0

# Chống nhiễu: bỏ qua xung đến quá sát nhau (ENC_DEBOUNCE_US = 0 để tắt)
_DEB = config.ENC_DEBOUNCE_US
_t_fl = 0; _t_fr = 0; _t_rl = 0; _t_rr = 0


# Thời điểm (µs) của 4 xung gần nhất mỗi bánh: dùng để đo tốc độ khi xung thưa (~10 mm/xung, ở 0.1 m/s chỉ ~9 xung/s,
# đếm theo chu kỳ 20 ms gần như vô nghĩa). Tốc độ = (số khoảng) / (thời gian giữa xung cũ nhất và mới nhất).
_ring = [array('I', [0, 0, 0, 0]), array('I', [0, 0, 0, 0]), array('I', [0, 0, 0, 0]), array('I', [0, 0, 0, 0])]
_ri = [0, 0, 0, 0]
_WIN_US = 400000            # chỉ tin các xung trong 0.4 s gần nhất (chậm hơn ~2.5 xung/s coi như đứng yên)
_rate = [0.0, 0.0, 0.0, 0.0]    # xung/giây đã làm mượt, không dấu
_known = [True, True, True, True]   # False = mới có 1 xung, chưa đủ để biết tốc độ
_RATE_ALPHA = 0.6


# Lớp Kalman Filter 1D tối ưu cho vận tốc từng bánh
class WheelKalman1D:
    def __init__(self, q, r):
        self.q = q
        self.r = r
        self.p = 1.0
        self.x = 0.0  # Vận tốc ước lượng (Ticks/s)

    def update(self, measurement):
        self.p += self.q
        k = self.p / (self.p + self.r)
        self.x += k * (measurement - self.x)
        self.p *= (1.0 - k)
        if abs(self.x) < 0.5 and measurement == 0.0:
            self.x = 0.0
        return self.x


# Khởi tạo 4 bộ lọc Kalman 1D độc lập cho 4 bánh
_kf_fl = WheelKalman1D(config.KF_ENC_Q, config.KF_ENC_R)
_kf_fr = WheelKalman1D(config.KF_ENC_Q, config.KF_ENC_R)
_kf_rl = WheelKalman1D(config.KF_ENC_Q, config.KF_ENC_R)
_kf_rr = WheelKalman1D(config.KF_ENC_Q, config.KF_ENC_R)

# Trạng thái phục vụ tính đạo hàm vận tốc
_prev_fl = 0; _prev_fr = 0; _prev_rl = 0; _prev_rr = 0
_vel_mps_fl = 0.0; _vel_mps_fr = 0.0; _vel_mps_rl = 0.0; _vel_mps_rr = 0.0
_ticks_per_sec = (0.0, 0.0, 0.0, 0.0)


# Hàm ngắt phần cứng (ISR) siêu gọn
def _isr_fl(p):
    global _xung_fl, _t_fl
    t = time.ticks_us()
    if time.ticks_diff(t, _t_fl) >= _DEB:
        _t_fl = t
        _xung_fl += _chieu_fl
        k = _ri[0]
        _ring[0][k & 3] = t
        _ri[0] = k + 1


def _isr_fr(p):
    global _xung_fr, _t_fr
    t = time.ticks_us()
    if time.ticks_diff(t, _t_fr) >= _DEB:
        _t_fr = t
        _xung_fr += _chieu_fr
        k = _ri[1]
        _ring[1][k & 3] = t
        _ri[1] = k + 1


def _isr_rl(p):
    global _xung_rl, _t_rl
    t = time.ticks_us()
    if time.ticks_diff(t, _t_rl) >= _DEB:
        _t_rl = t
        _xung_rl += _chieu_rl
        k = _ri[2]
        _ring[2][k & 3] = t
        _ri[2] = k + 1


def _isr_rr(p):
    global _xung_rr, _t_rr
    t = time.ticks_us()
    if time.ticks_diff(t, _t_rr) >= _DEB:
        _t_rr = t
        _xung_rr += _chieu_rr
        k = _ri[3]
        _ring[3][k & 3] = t
        _ri[3] = k + 1


def init():
    Pin(config.PIN_ENC_FL, Pin.IN, Pin.PULL_UP).irq(trigger=Pin.IRQ_RISING, handler=_isr_fl)
    Pin(config.PIN_ENC_FR, Pin.IN, Pin.PULL_UP).irq(trigger=Pin.IRQ_RISING, handler=_isr_fr)
    Pin(config.PIN_ENC_RL, Pin.IN, Pin.PULL_UP).irq(trigger=Pin.IRQ_RISING, handler=_isr_rl)
    Pin(config.PIN_ENC_RR, Pin.IN, Pin.PULL_UP).irq(trigger=Pin.IRQ_RISING, handler=_isr_rr)
    print("[INIT] Encoder + 4x 1D Kalman Ready (FL=7, FR=6, RL=5, RR=4)")


def set_chieu(c_fl, c_fr, c_rl, c_rr):
    global _chieu_fl, _chieu_fr, _chieu_rl, _chieu_rr
    global _last_active_fl, _last_active_fr, _last_active_rl, _last_active_rr, _stop_timestamp_ms

    now = time.ticks_ms()
    # Nếu có lệnh chạy, cập nhật ngay chiều quay và lưu lại lịch sử chiều
    if c_fl != 0 or c_fr != 0 or c_rl != 0 or c_rr != 0:
        _chieu_fl = c_fl; _chieu_fr = c_fr; _chieu_rl = c_rl; _chieu_rr = c_rr
        if c_fl != 0: _last_active_fl = c_fl
        if c_fr != 0: _last_active_fr = c_fr
        if c_rl != 0: _last_active_rl = c_rl
        if c_rr != 0: _last_active_rr = c_rr
        _stop_timestamp_ms = now
    else:
        # Chốt quán tính: Giữ nguyên chiều đếm thêm 150ms sau khi nhả phím để bắt trọn xung trượt phanh
        if time.ticks_diff(now, _stop_timestamp_ms) < 150:
            _chieu_fl = _last_active_fl
            _chieu_fr = _last_active_fr
            _chieu_rl = _last_active_rl
            _chieu_rr = _last_active_rr
        else:
            _chieu_fl = 0; _chieu_fr = 0; _chieu_rl = 0; _chieu_rr = 0


def update_velocities(dt_sec):
    global _prev_fl, _prev_fr, _prev_rl, _prev_rr
    global _vel_mps_fl, _vel_mps_fr, _vel_mps_rl, _vel_mps_rr, _ticks_per_sec

    if dt_sec <= 0.0:
        return

    # Đọc snapshot số xung
    cur_fl = _xung_fl; cur_fr = _xung_fr; cur_rl = _xung_rl; cur_rr = _xung_rr

    # Vận tốc thô (Xung/giây)
    raw_tps_fl = (cur_fl - _prev_fl) / dt_sec
    raw_tps_fr = (cur_fr - _prev_fr) / dt_sec
    raw_tps_rl = (cur_rl - _prev_rl) / dt_sec
    raw_tps_rr = (cur_rr - _prev_rr) / dt_sec

    _prev_fl = cur_fl; _prev_fr = cur_fr; _prev_rl = cur_rl; _prev_rr = cur_rr

    # Lọc qua 4 bộ Kalman 1D
    kal_tps_fl = _kf_fl.update(raw_tps_fl)
    kal_tps_fr = _kf_fr.update(raw_tps_fr)
    kal_tps_rl = _kf_rl.update(raw_tps_rl)
    kal_tps_rr = _kf_rr.update(raw_tps_rr)

    _ticks_per_sec = (kal_tps_fl, kal_tps_fr, kal_tps_rl, kal_tps_rr)

    # Đổi sang mét/giây (m/s)
    mpt = config.METERS_PER_TICK
    _vel_mps_fl = kal_tps_fl * mpt
    _vel_mps_fr = kal_tps_fr * mpt
    _vel_mps_rl = kal_tps_rl * mpt
    _vel_mps_rr = kal_tps_rr * mpt


def get_xung():
    return (_xung_fl, _xung_fr, _xung_rl, _xung_rr)


def get_wheel_velocities_mps():
    return (_vel_mps_fl, _vel_mps_fr, _vel_mps_rl, _vel_mps_rr)


def get_wheel_ticks_per_sec():
    return _ticks_per_sec


def is_stationary():
    return (abs(_vel_mps_fl) < 0.002 and abs(_vel_mps_fr) < 0.002 and
            abs(_vel_mps_rl) < 0.002 and abs(_vel_mps_rr) < 0.002 and
            _chieu_fl == 0 and _chieu_fr == 0 and _chieu_rl == 0 and _chieu_rr == 0)


def _tick_rate(i, now_us):
    """Tốc độ bánh i (xung/s, không dấu) từ thời điểm các xung gần nhất. Xung quá hạn (lâu chưa tới) thì chặn trên bằng 1/tuổi."""
    n = _ri[i]
    if n == 0:
        return 0.0
    r = _ring[i]
    t_last = r[(n - 1) & 3]
    age = time.ticks_diff(now_us, t_last)
    if age < 0:
        age = 0
    if age >= _WIN_US:
        return 0.0
    m = n if n < 4 else 4
    k = 1
    t_old = t_last
    while k < m:
        t = r[(n - 1 - k) & 3]
        if time.ticks_diff(now_us, t) > _WIN_US:
            break
        t_old = t
        k += 1
    if k >= 2:
        span = time.ticks_diff(t_last, t_old)
        if span <= 0:
            return 0.0
        rate = (k - 1) * 1e6 / span
        if age > span / (k - 1):                # xung kế tiếp trễ hơn khoảng trung bình -> bánh đang chậm lại
            rate = min(rate, 1e6 / age)
        return rate
    return -1.0                                         # mới có 1 xung trong cửa sổ: chưa biết tốc độ (chỉ biết chặn trên 1/tuổi)


def update_speeds(now_us):
    """Cập nhật tốc độ 4 bánh (xung/s, đã làm mượt nhẹ). Gọi mỗi chu kỳ điều khiển."""
    for i in range(4):
        r = _tick_rate(i, now_us)
        if r < 0.0:
            _known[i] = False                       # giữ giá trị cũ, nhưng chặn trên theo thời gian từ xung cuối
            n = _ri[i]
            if n:
                age = time.ticks_diff(now_us, _ring[i][(n - 1) & 3])
                if age > 0 and _rate[i] > 1e6 / age:
                    _rate[i] = 1e6 / age
            continue
        _known[i] = True
        if r == 0.0:
            _rate[i] = 0.0
        else:
            _rate[i] += _RATE_ALPHA * (r - _rate[i])


def get_speed_mps(i):
    """Độ lớn tốc độ bánh i (m/s, không dấu). Chiều lấy theo lệnh quay hiện hành (get_chieu)."""
    return _rate[i] * config.METERS_PER_TICK


def get_chieu(i):
    return (_chieu_fl, _chieu_fr, _chieu_rl, _chieu_rr)[i]


def speed_known(i):
    return _known[i]
