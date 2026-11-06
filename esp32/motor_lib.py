from machine import Pin, PWM
import config
import encoder_lib

_fl_1 = None; _fl_2 = None; _fr_1 = None; _fr_2 = None
_rl_1 = None; _rl_2 = None; _rr_1 = None; _rr_2 = None

def _cfg(name, default):
    return getattr(config, name, default)         # config.py cũ của bạn chưa có mục PID_* thì dùng mặc định


# Mức giới hạn tốc độ hiện hành (có thể tăng/giảm trực tiếp bằng bàn phím)
_speed_limit_pwm = config.DEFAULT_SPEED_LIMIT

# Tốc độ hiện tại sau bộ làm mượt gia tốc (Slew-rate limiter)
_cur_fl = 0.0; _cur_fr = 0.0; _cur_rl = 0.0; _cur_rr = 0.0


def init():
    global _fl_1, _fl_2, _fr_1, _fr_2, _rl_1, _rl_2, _rr_1, _rr_2
    for pin_num in config.PWM_DEINIT_LIST:
        try:
            PWM(Pin(pin_num)).deinit()
        except:
            pass
        Pin(pin_num, Pin.OUT).value(0)

    _fl_1 = PWM(Pin(config.PIN_FL_IN1), freq=config.PWM_FREQ, duty_u16=0)
    _fl_2 = PWM(Pin(config.PIN_FL_IN2), freq=config.PWM_FREQ, duty_u16=0)
    _fr_1 = PWM(Pin(config.PIN_FR_IN1), freq=config.PWM_FREQ, duty_u16=0)
    _fr_2 = PWM(Pin(config.PIN_FR_IN2), freq=config.PWM_FREQ, duty_u16=0)
    _rl_1 = PWM(Pin(config.PIN_RL_IN1), freq=config.PWM_FREQ, duty_u16=0)
    _rl_2 = PWM(Pin(config.PIN_RL_IN2), freq=config.PWM_FREQ, duty_u16=0)
    _rr_1 = PWM(Pin(config.PIN_RR_IN1), freq=config.PWM_FREQ, duty_u16=0)
    _rr_2 = PWM(Pin(config.PIN_RR_IN2), freq=config.PWM_FREQ, duty_u16=0)
    print(f"[INIT] Motor Ready | Trần tốc độ bảo vệ Encoder: {_speed_limit_pwm}%")


def set_speed_limit(new_limit):
    global _speed_limit_pwm
    _speed_limit_pwm = max(30, min(100, int(new_limit)))
    return _speed_limit_pwm


def get_speed_limit():
    return _speed_limit_pwm


def _apply_slew_rate(current_val, target_val):
    if target_val == 0.0:
        # Khi phanh: cho phép giảm nhanh gấp đôi để đảm bảo an toàn
        step = config.SLEW_RATE_STEP * 2.5
    else:
        step = config.SLEW_RATE_STEP

    diff = target_val - current_val
    if abs(diff) <= step:
        return float(target_val)
    return current_val + (step if diff > 0 else -step)


def _xuat_pwm_banh(pwm1, pwm2, phan_tram, physical_sign, floor=None):
    """
    physical_sign: SIGN_FL (-1), SIGN_FR (+1)...
    Đảm bảo truyền số DƯƠNG (+100) là bánh luôn tiến về phía trước!
    """
    phan_tram = max(-100.0, min(100.0, phan_tram))
    if abs(phan_tram) < 5.0:
        # Phanh điện từ (Active Brake)
        pwm1.duty_u16(65535); pwm2.duty_u16(65535)
        return 0

    # Bù vùng chết ma sát nghỉ
    abs_val = max(config.MIN_EFFECTIVE_PWM if floor is None else floor, abs(phan_tram))
    duty = int((abs_val / 100.0) * 65535)

    # Nhân với dấu phần cứng đã calib từ motor.py
    hw_cmd = phan_tram * physical_sign
    if hw_cmd > 0:
        pwm1.duty_u16(duty); pwm2.duty_u16(0)
    else:
        pwm1.duty_u16(0); pwm2.duty_u16(duty)

    # Trả về chiều chuyển động thực tế của bánh (+1 là tiến, -1 là lùi) cho Encoder
    return 1 if phan_tram > 0 else -1


def drive_mecanum(norm_fl, norm_fr, norm_rl, norm_rr, yaw_error_rad=0.0, speed_scale=1.0):
    """
    norm_fl..rr: Hệ số hướng từ -1.0 đến +1.0 (+1.0 là Tiến, -1.0 là Lùi).
    yaw_error_rad: Độ lệch góc để bộ PID tự động bẻ lái giữ xe chạy thẳng.
    """
    global _cur_fl, _cur_fr, _cur_rl, _cur_rr

    eff_limit = _speed_limit_pwm * speed_scale

    # Bù trừ lệch hướng (Active Heading Hold)
    trim = yaw_error_rad * config.KP_HEADING_HOLD
    trim = max(-15.0, min(15.0, trim))

    # Tính tốc độ mục tiêu cho 4 bánh
    tgt_fl = (norm_fl * eff_limit) - trim
    tgt_fr = (norm_fr * eff_limit) + trim
    tgt_rl = (norm_rl * eff_limit) - trim
    tgt_rr = (norm_rr * eff_limit) + trim

    # Làm mượt gia tốc để chống trượt bánh Mecanum
    _cur_fl = _apply_slew_rate(_cur_fl, tgt_fl)
    _cur_fr = _apply_slew_rate(_cur_fr, tgt_fr)
    _cur_rl = _apply_slew_rate(_cur_rl, tgt_rl)
    _cur_rr = _apply_slew_rate(_cur_rr, tgt_rr)

    # Xuất xung ra phần cứng và cập nhật chiều cho Encoder
    c_fl = _xuat_pwm_banh(_fl_1, _fl_2, _cur_fl, config.SIGN_FL)
    c_fr = _xuat_pwm_banh(_fr_1, _fr_2, _cur_fr, config.SIGN_FR)
    c_rl = _xuat_pwm_banh(_rl_1, _rl_2, _cur_rl, config.SIGN_RL)
    c_rr = _xuat_pwm_banh(_rr_1, _rr_2, _cur_rr, config.SIGN_RR)

    encoder_lib.set_chieu(c_fl, c_fr, c_rl, c_rr)


def mix_body(vx, vy, w):
    """Vận tốc thân xe (vx tiến m/s, vy sang trái m/s, w ngược chiều kim đồng hồ rad/s) -> tốc độ 4 bánh (m/s).
    Cùng công thức với bộ mô phỏng; VY_SIGN / W_SIGN trong config để hiệu chỉnh nếu bánh lắp ngược."""
    vy = vy * config.VY_SIGN
    wl = w * config.W_SIGN * config.MECANUM_L_SUM
    return (vx - vy - wl, vx + vy + wl, vx + vy - wl, vx - vy + wl)


def set_pwm_range(min_pwm, speed_pwm):
    """Chỉnh trực tiếp (qua Wi-Fi) hai mốc PWM:
    min_pwm  = % PWM nhỏ nhất làm bánh BẮT ĐẦU quay (dưới mức này động cơ chỉ kêu "i i" mà không quay)
    speed_pwm = % PWM ứng với tốc độ MAX_WHEEL_MPS."""
    global _speed_limit_pwm
    mn = max(5, min(70, int(min_pwm)))
    sp = max(mn + 8, min(100, int(speed_pwm)))
    config.MIN_EFFECTIVE_PWM = mn
    _speed_limit_pwm = sp


def get_min_pwm():
    return int(config.MIN_EFFECTIVE_PWM)


def _compensate(n, dead, lim):
    """Tốc độ chuẩn hoá n (-1..1) -> hệ số PWM sao cho n nhỏ nhất vẫn vượt ngưỡng quay:
    PWM% = dead + |n| * (lim - dead). n ~ 0 thì dừng."""
    a = abs(n)
    if a < 0.02:
        return 0.0
    if a > 1.0:
        a = 1.0
    v = (dead + a * (lim - dead)) / lim
    return v if n > 0 else -v


# ---------------------------------------------------------------------
#  PID TỐC ĐỘ TỪNG BÁNH (vòng kín bằng encoder)
#  PWM% = tiến liệu (vùng chết + tỉ lệ theo tốc độ)  +  Kp*sai số  +  tích phân (chống bão hòa)
#  Tiến liệu lo phần lớn, PI chỉ bù lệch (bánh yếu/mạnh khác nhau, pin sụt, sàn nhám) và tự tìm ngưỡng quay của TỪNG bánh.
# ---------------------------------------------------------------------
_pid_en = bool(_cfg('PID_ENABLE', True))
_kp = float(_cfg('PID_KP', 0.15))
_ki = float(_cfg('PID_KI', 1.0))
_acc = float(_cfg('PID_ACCEL', 1.5))              # m/s^2: gia tốc tối đa của tốc độ đặt từng bánh (giảm tốc nhanh gấp 2.5 lần)
_I_MAX = float(_cfg('PID_I_MAX', 25.0))           # % PWM: trần phần tích phân
_CORR_MAX = float(_cfg('PID_CORR_MAX', 35.0))     # % PWM: trần tổng phần hiệu chỉnh (P + I)
_FLOOR_MOVING = float(_cfg('PID_FLOOR_MOVING', 0.85))   # bánh đang quay chỉ cần ~85% PWM khởi động để giữ quay (ma sát động < ma sát nghỉ)
_V_EPS = 0.012                                    # m/s: tốc độ đặt dưới mức này coi như 0
_BLIND_S = 0.25                                   # s: lúc mới khởi động chưa có xung nào -> chỉ dùng tiến liệu, không để P/I đẩy PWM lên quá tay
_tblind = [0.0, 0.0, 0.0, 0.0]
_vset = [0.0, 0.0, 0.0, 0.0]                      # tốc độ đặt sau bộ giới hạn gia tốc (m/s, có dấu)
_integ = [0.0, 0.0, 0.0, 0.0]
_diag_pwm = [0.0, 0.0, 0.0, 0.0]                  # PWM% đang xuất (có dấu), để gửi về Ubuntu xem


def set_pid(enable, kp, ki, accel):
    """Chỉnh PID qua Wi-Fi: bật/tắt vòng kín, Kp, Ki, gia tốc đặt."""
    global _pid_en, _kp, _ki, _acc
    en = bool(enable)
    if en != _pid_en:
        global _cur_fl, _cur_fr, _cur_rl, _cur_rr
        _cur_fl = _cur_fr = _cur_rl = _cur_rr = 0.0
        for i in range(4):
            _vset[i] = 0.0
            _integ[i] = 0.0
    _pid_en = en
    _kp = max(0.0, min(3.0, float(kp)))
    _ki = max(0.0, min(20.0, float(ki)))
    _acc = max(0.2, min(10.0, float(accel)))


def get_pid():
    return (1.0 if _pid_en else 0.0, _kp, _ki, _acc)


def get_diag():
    """(tốc độ đặt m/s x4, tốc độ đo m/s x4 có dấu, PWM% x4) - để vẽ đồ thị chỉnh PID."""
    meas = []
    for i in range(4):
        c = encoder_lib.get_chieu(i)
        meas.append(encoder_lib.get_speed_mps(i) * (1 if c >= 0 else -1))
    return _vset, meas, _diag_pwm


def hard_stop():
    """Dừng khẩn (lệnh dừng / mất Wi-Fi / hết thời gian chờ lệnh)."""
    if _pid_en:
        stop_now()
    else:
        drive_mecanum(0.0, 0.0, 0.0, 0.0)


def stop_now():
    """Dừng ngay (phanh điện từ), xoá trạng thái PID."""
    for i in range(4):
        _vset[i] = 0.0
        _integ[i] = 0.0
        _diag_pwm[i] = 0.0
    dung_khan_cap()


def _drive_pid(tgt, dt):
    vmax = config.MAX_WHEEL_MPS
    lim = float(_speed_limit_pwm)
    dead = float(min(config.MIN_EFFECTIVE_PWM, lim - 8))
    out = [0, 0, 0, 0]
    leak = 1.0 - dt / 5.0
    pins = ((_fl_1, _fl_2, config.SIGN_FL), (_fr_1, _fr_2, config.SIGN_FR),
            (_rl_1, _rl_2, config.SIGN_RL), (_rr_1, _rr_2, config.SIGN_RR))
    for i in range(4):
        # 1) giới hạn gia tốc của tốc độ đặt
        d = tgt[i] - _vset[i]
        step = _acc * dt * (2.5 if abs(tgt[i]) < abs(_vset[i]) else 1.0)
        if d > step:
            d = step
        elif d < -step:
            d = -step
        v = _vset[i] + d
        _vset[i] = v
        a = v if v >= 0.0 else -v
        if a < _V_EPS:
            _integ[i] *= leak                     # đứng yên: phần tích phân học được phai dần (giữ lại cho lần chạy kế tiếp)
            _tblind[i] = 0.0
            _diag_pwm[i] = 0.0
            out[i] = _xuat_pwm_banh(pins[i][0], pins[i][1], 0.0, pins[i][2])
            continue
        sgn = 1.0 if v > 0.0 else -1.0
        n = a / vmax
        if n > 1.0:
            n = 1.0
        # 2) tốc độ đo được theo chiều đang đặt. Bánh đang quay chỉ cần ngưỡng PWM thấp hơn (ma sát động < ma sát nghỉ)
        ch = encoder_lib.get_chieu(i)
        vm = encoder_lib.get_speed_mps(i) if ch == sgn else 0.0
        d_eff = dead * (_FLOOR_MOVING if vm > 0.02 else 1.0)
        ff = d_eff + n * (lim - d_eff)
        floor = d_eff
        if vm > 0.02:
            _tblind[i] = 0.0
            blind = False
        else:
            _tblind[i] += dt
            blind = _tblind[i] < _BLIND_S or not encoder_lib.speed_known(i)
        if blind:                                 # chưa đo được tốc độ: chưa tin sai số, giữ phần tích phân đã học
            u = ff + _integ[i]
            if u > 100.0:
                u = 100.0
            _diag_pwm[i] = sgn * u
            out[i] = _xuat_pwm_banh(pins[i][0], pins[i][1], sgn * u, pins[i][2], 0.0)
            continue
        e = (a - vm) / vmax
        # 3) PI có chống bão hòa
        integ = _integ[i] + _ki * e * dt * 100.0
        if integ > _I_MAX:
            integ = _I_MAX
        elif integ < -_I_MAX:
            integ = -_I_MAX
        corr = _kp * e * 100.0 + integ
        if corr > _CORR_MAX:
            corr = _CORR_MAX
        elif corr < -_CORR_MAX:
            corr = -_CORR_MAX
        u = ff + corr
        if u > 100.0:
            u = 100.0
            if e > 0.0:
                integ = _integ[i]                 # đã kịch trần mà vẫn thiếu: không tích thêm
        elif u < floor:
            u = floor
            if e < 0.0:
                integ = _integ[i]
        _integ[i] = integ
        _diag_pwm[i] = sgn * u
        out[i] = _xuat_pwm_banh(pins[i][0], pins[i][1], sgn * u, pins[i][2], 0.0)
    encoder_lib.set_chieu(out[0], out[1], out[2], out[3])


def drive_body(vx, vy, w, dt=0.02):
    """Lái bằng vận tốc thân xe (m/s, m/s, rad/s). Có PID: tốc độ từng bánh được giữ đúng bằng encoder.
    Tắt PID (set_pid) thì quay về chạy hở: quy đổi m/s -> PWM, có bù vùng chết (tốc độ nhỏ nhất vẫn >= MIN_EFFECTIVE_PWM)."""
    fl, fr, rl, rr = mix_body(vx, vy, w)
    m = max(abs(fl), abs(fr), abs(rl), abs(rr))
    if m > config.MAX_WHEEL_MPS:
        k = config.MAX_WHEEL_MPS / m          # giữ nguyên hướng, chỉ giảm tốc
        fl *= k; fr *= k; rl *= k; rr *= k
    if _pid_en:
        _drive_pid((fl, fr, rl, rr), dt)
        return
    s = 1.0 / config.MAX_WHEEL_MPS
    lim = float(_speed_limit_pwm)
    dead = float(min(config.MIN_EFFECTIVE_PWM, lim - 8))
    drive_mecanum(_compensate(fl * s, dead, lim), _compensate(fr * s, dead, lim),
                  _compensate(rl * s, dead, lim), _compensate(rr * s, dead, lim), 0.0, 1.0)


def dung_khan_cap():
    global _cur_fl, _cur_fr, _cur_rl, _cur_rr
    _cur_fl = 0.0; _cur_fr = 0.0; _cur_rl = 0.0; _cur_rr = 0.0
    _xuat_pwm_banh(_fl_1, _fl_2, 0, config.SIGN_FL)
    _xuat_pwm_banh(_fr_1, _fr_2, 0, config.SIGN_FR)
    _xuat_pwm_banh(_rl_1, _rl_2, 0, config.SIGN_RL)
    _xuat_pwm_banh(_rr_1, _rr_2, 0, config.SIGN_RR)
    encoder_lib.set_chieu(0, 0, 0, 0)
