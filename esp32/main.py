import gc
import math
import time
from array import array

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

import config
try:
    import giuaky_config as gk
except ImportError:
    gk = config
import lidar_lib
import motor_lib
import wander_lib
import kiemtra_lib

CONTROL = getattr(gk, 'CONTROL', 'wifi') if gk is not config else 'wifi'   # 'wifi' = web trên điện thoại | 'ble' = app Bluetooth
_ctl = None
if CONTROL == 'ble':
    try:
        import ble_lib as _ctl
    except ImportError:          # bản MicroPython không có bluetooth
        _ctl = None
else:
    import web_lib as _ctl

try:
    import random
    _getbits = random.getrandbits
except (ImportError, AttributeError):
    import urandom
    _getbits = urandom.getrandbits


def _rand01():
    return _getbits(16) / 65535.0


def _c(name, default):
    return getattr(gk, name, getattr(config, name, default))


BLE_NAME = _c('BLE_NAME', 'OOMWOO')
CHECK_ROT = bool(_c('AUTO_SELF_CHECK', True))   # lần đầu TỰ CHẠY: thử xoay/tiến/trượt, LiDAR xem xe đi đúng chiều không
PWM_MAX = int(_c('PWM_MAX', 100))           # % PWM khi thanh tốc độ 100% + đẩy hết cần = HẾT CÔNG SUẤT động cơ
HOLD_MS = _c('MANUAL_HOLD_MS', 600)         # giữ lệnh lái tay bấy nhiêu ms sau lần nhận cuối
STOP_ON_DISCONNECT = _c('STOP_ON_DISCONNECT', True)
PIN_BTN = _c('PIN_MODE_BUTTON', 0)          # None = không dùng nút trên mạch
SCAN_STALE_MS = 800
BRAKE_MM = int(_c('BLE_BRAKE_DIST_MM', 260))   # mm từ tâm LiDAR: mũi xe (~18 cm) + khe hở

MODE_MANUAL = 0
MODE_AUTO = 1

# hướng lái tay: (vx, vy, w) theo đơn vị "phần của tốc độ tối đa"
_MOVES = {
    'F': (1.0, 0.0, 0.0), 'B': (-1.0, 0.0, 0.0),
    'L': (0.0, 0.0, 1.0), 'R': (0.0, 0.0, -1.0),
    'Q': (0.0, 1.0, 0.0), 'E': (0.0, -1.0, 0.0),
    'G': (0.7, 0.7, 0.0), 'H': (0.7, -0.7, 0.0),
}

_mode = MODE_AUTO if _c('AUTO_AT_BOOT', False) else MODE_MANUAL
_speed = int(_c('BLE_SPEED_PCT', 60))
_man = (0.0, 0.0, 0.0)
_man_ms = 0
_wander = None
_last_sid = -1
_t_scan = 0
_safety = False
_stale = False
_cmd = (0.0, 0.0, 0.0)
_btn = None
_btn_prev = 1
_btn_ms = 0
_t_ctrl = 0
_t_stat = 0
_t_log = 0
_t_gc = 0
_errors = 0
_n_cmds = 0
_mask = kiemtra_lib.MatNa()
_scan_f = array('H', bytes(720))     # vòng quét đã bỏ tia chạm thân xe
_scan_m = array('H', bytes(720))     # sau mặt nạ, trước khi xoay/lật khung
_wflip = 1                           # -1: lệnh xoay làm xe xoay ngược (W_SIGN sai)          -> đảo khi lái (mọi chế độ)
_vyflip = 1                          # -1: lệnh trượt làm xe trượt ngược (VY_SIGN sai)        -> đảo khi lái
_wflip_auto = 1                      # -1: chỉ biết xoay ngược, chưa rõ lý do (chỗ chật)      -> chỉ đảo khi TỰ CHẠY
_fr_off = 0                          # khung LiDAR -> khung xe: góc_thô = _fr_off + _fr_m * góc_xe (LiDAR lắp lệch / quay ngược)
_fr_m = 1
_chk = 'CHUA' if CHECK_ROT else 'XONG'
_chk_t = 0
_chk_sid = -1
_chk_s0 = None
_chk_res = {}
_CHK_RUN = ('CHO0', 'XOAY', 'CHO1', 'TIEN', 'CHO2', 'TRUOT', 'CHO3')


def _t():
    return time.ticks_ms()


def mode_name():
    return 'TU CHAY' if _mode == MODE_AUTO else 'LAI TAY'


def set_mode(m, why=''):
    global _mode, _man
    if m == _mode:
        return
    global _chk, _chk_s0, _chk_res
    _mode = m
    _man = (0.0, 0.0, 0.0)
    motor_lib.hard_stop()
    if _chk in _CHK_RUN:                                     # đang tự kiểm tra mà bị ngắt -> làm lại lần sau
        _chk, _chk_s0, _chk_res = 'CHUA', None, {}
    if _wander is not None:
        _wander._set('CHAY')
    print("[GIUA KY] Chế độ: %s%s" % ('TỰ CHẠY (tránh vật cản bằng LiDAR)' if m == MODE_AUTO else 'LÁI TAY (app)',
                                      (' - ' + why) if why else ''))
    _send_status()


def handle_text(data):
    """Đọc chuỗi lệnh từ điện thoại. Trả số lệnh hợp lệ."""
    global _man, _man_ms, _speed, _n_cmds
    if not data:
        return 0
    try:
        s = data.decode() if isinstance(data, (bytes, bytearray)) else str(data)
    except Exception:
        s = ''.join(chr(b) for b in data if b < 128)
    s = s.upper()
    n = 0
    i = 0
    L = len(s)
    while i < L:
        ch = s[i]
        i += 1
        if ch in _MOVES:
            _man = _MOVES[ch]
            _man_ms = _t()
            if _mode != MODE_MANUAL:
                set_mode(MODE_MANUAL, 'bấm nút lái')
                _man = _MOVES[ch]
                _man_ms = _t()
        elif ch == 'S':
            _man = (0.0, 0.0, 0.0)
        elif ch == 'X':
            _man = (0.0, 0.0, 0.0)
            set_mode(MODE_MANUAL, 'DỪNG')
            motor_lib.dung_khan_cap()
        elif ch == 'A':
            set_mode(MODE_AUTO, 'từ app')
        elif ch == 'M':
            set_mode(MODE_MANUAL, 'từ app')
        elif ch == 'T':
            set_mode(MODE_MANUAL if _mode == MODE_AUTO else MODE_AUTO, 'từ app')
        elif ch == 'V':
            j = i
            while j < L and s[j] in '0123456789.':
                j += 1
            if j > i:
                try:
                    _speed = max(20, min(100, int(float(s[i:j]))))
                except ValueError:
                    pass
                i = j
        elif ch == 'J':                      # joystick: J<tiến>,<sang trái>,<xoay trái>  mỗi số -100..100 (%)
            vals = []
            while len(vals) < 3:
                j = i
                if j < L and s[j] in '+-':
                    j += 1
                k = j
                while k < L and s[k] in '0123456789':
                    k += 1
                if k == j:
                    break
                vals.append(max(-100, min(100, int(s[i:k]))) / 100.0)
                i = k
                if len(vals) < 3 and i < L and s[i] == ',':
                    i += 1
                else:
                    break
            if len(vals) != 3:
                continue
            if vals[0] == 0.0 and vals[1] == 0.0 and vals[2] == 0.0:
                _man = (0.0, 0.0, 0.0)               # thả cần = dừng
            else:
                if _mode != MODE_MANUAL:
                    set_mode(MODE_MANUAL, 'gạt joystick')
                _man = (vals[0], vals[1], vals[2])
                _man_ms = _t()
        elif ch == '?':
            _send_status()
        else:
            continue                     # ký tự lạ / '\0' / xuống dòng: bỏ qua
        n += 1
    _n_cmds += n
    return n


def _status_text():
    d = _min_dir(0, 25)
    tail = 'LIDAR?' if _stale else ('%.2fm' % (d / 1000.0) if d < 9999 else '>8m')
    if _mode == MODE_AUTO and not _stale and (_chk in _CHK_RUN or not _mask.done):
        tail = 'KIEM TRA'
    if _safety and not _stale:
        tail += ' PHANH'
    return '%s|%s' % (mode_name(), tail)


def _send_status():
    if _ctl is not None:
        _ctl.send(_status_text())


def _min_dir(deg, half):
    c = int(deg) % 360
    best = 9999
    f = _scan_f
    for k in range(-half, half + 1):
        d = f[(c + k) % 360]
        if d and d < best:
            best = d
    return best


def _count_below(deg, half, thr):
    c = int(deg) % 360
    n = 0
    f = _scan_f
    for k in range(-half, half + 1):
        d = f[(c + k) % 360]
        if d and d < thr:
            n += 1
    return n


def _wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


def _finish_check():
    """Kết luận sau khi thử xoay / tiến / trượt (đo bằng LiDAR, không cần encoder)."""
    global _wflip, _vyflip, _wflip_auto, _fr_off, _fr_m
    r = _chk_res
    rot = r.get('rot', 0)                      # +1 đúng, -1 ngược, 0 không rõ
    ff = r.get('fwd')                          # hướng đi thật (độ, khung LiDAR thô) khi ra lệnh TIẾN
    fs = r.get('side')                         # ... khi ra lệnh TRƯỢT TRÁI
    cross = None
    if ff is not None and fs is not None:
        c = _wrap180(fs - ff)
        if 45.0 <= abs(c) <= 135.0:
            cross = 1 if c > 0 else -1
    msg = []
    if ff is not None:
        snap = int(round(ff / 90.0)) * 90
        if abs(_wrap180(ff - snap)) <= 30.0 and snap % 360 != 0:
            _fr_off = snap % 360
            msg.append("LiDAR lắp lệch ~%d° (mũi xe ở góc %d° của LiDAR) -> tự xoay khung. Sửa hẳn: LIDAR_ANGLE_OFFSET_DEG" % (snap, snap))
        elif abs(_wrap180(ff - snap)) > 30.0:
            msg.append("LiDAR có thể lệch ~%.0f° (chưa tự sửa, vì không chắc). Kiểm tra LIDAR_ANGLE_OFFSET_DEG" % ff)
    if rot < 0 and cross == -1:
        _fr_m = -1
        msg.append("LiDAR quay NGƯỢC chiều cấu hình (bản đồ lật gương) -> tự lật khung. Sửa hẳn: đảo LIDAR_CLOCKWISE trong config.py")
    elif rot < 0 and cross == 1:
        _wflip = -1
        msg.append("Lệnh xoay làm xe xoay NGƯỢC -> tự đảo chiều xoay (cả lái tay). Sửa hẳn: đổi W_SIGN trong config.py")
    elif rot > 0 and cross == -1:
        _vyflip = -1
        msg.append("Lệnh trượt làm xe trượt NGƯỢC -> tự đảo chiều trượt (cả lái tay). Sửa hẳn: đổi VY_SIGN trong config.py")
    elif rot < 0:
        _wflip_auto = -1
        msg.append("Xe xoay NGƯỢC lệnh (chưa đủ chỗ để biết do W_SIGN hay LIDAR_CLOCKWISE) -> chỉ đảo khi TỰ CHẠY. "
                   "Thử joystick XOAY sang trái: xe xoay phải -> đổi W_SIGN; xoay trái đúng -> đổi LIDAR_CLOCKWISE")
    if not msg:
        msg.append("mọi chiều ĐÚNG" if (rot > 0 and cross == 1) else "không phát hiện sai (thiếu chỗ trống để thử hết)")
    print("[GIUA KY] Tự kiểm tra xong: xoay=%s tiến=%s trượt=%s ->" % (
        {1: 'đúng', -1: 'NGƯỢC', 0: '?'}[rot], '?' if ff is None else '%.0f°' % ff, '?' if fs is None else '%.0f°' % fs))
    for m in msg:
        print("[GIUA KY]   " + m)


def _self_check(now, sid):
    """Lần đầu TỰ CHẠY sau khi bật: đứng yên -> xoay TRÁI -> (nếu đủ chỗ) TIẾN 1 đoạn ngắn -> TRƯỢT TRÁI 1 đoạn ngắn,
    mỗi bước so vòng quét LiDAR trước/sau để biết xe thực sự đi hướng nào. Trả lệnh (vx, vy, w), None = xong."""
    global _chk, _chk_t, _chk_sid, _chk_s0
    el = time.ticks_diff(now, _chk_t)
    vmove = 0.25 * config.MAX_WHEEL_MPS
    if _chk == 'CHUA':
        if _wander.nearest < 0.26:
            print("[GIUA KY] Bỏ qua tự kiểm tra: có vật sát xe (< 26 cm)")
            _chk = 'XONG'
            return None
        _chk, _chk_t, _chk_sid = 'CHO0', now, sid
        _chk_res.clear()
        print("[GIUA KY] Tự kiểm tra chiều xoay / tiến / trượt bằng LiDAR (~5 s) ...")
        return (0.0, 0.0, 0.0)
    if _chk in ('CHO0', 'CHO1', 'CHO2', 'CHO3'):
        if el < (400 if _chk == 'CHO0' else 500) or sid == _chk_sid:
            return (0.0, 0.0, 0.0)
        cur = array('H', _scan_m)
        if _chk == 'CHO0':
            _chk_s0, _chk, _chk_t = cur, 'XOAY', now
            return (0.0, 0.0, 1.0)
        if _chk == 'CHO1':
            deg, conf = kiemtra_lib.do_xoay(_chk_s0, cur)
            _chk_res['rot'] = 0 if (conf < 0.05 or abs(deg) < 4) else (1 if deg > 0 else -1)
            _chk_res['rot_deg'] = deg
        else:
            ang, dist = kiemtra_lib.huong_di(_chk_s0, cur)
            if ang is not None and dist > 0.04:
                _chk_res['fwd' if _chk == 'CHO2' else 'side'] = ang
        nxt = {'CHO1': 'TIEN', 'CHO2': 'TRUOT'}.get(_chk)
        if nxt is None or _wander.nearest < 0.40:                # hết bước, hoặc không đủ chỗ để tịnh tiến thử
            _chk, _chk_s0 = 'XONG', None
            _finish_check()
            return (0.0, 0.0, 0.0)
        _chk_s0, _chk, _chk_t = cur, nxt, now
        return (vmove, 0.0, 0.0) if nxt == 'TIEN' else (0.0, vmove, 0.0)
    if _chk in ('XOAY', 'TIEN', 'TRUOT'):
        if el >= 600:
            _chk, _chk_t, _chk_sid = {'XOAY': 'CHO1', 'TIEN': 'CHO2', 'TRUOT': 'CHO3'}[_chk], now, sid
            return (0.0, 0.0, 0.0)
        return {'XOAY': (0.0, 0.0, 1.0), 'TIEN': (vmove, 0.0, 0.0), 'TRUOT': (0.0, vmove, 0.0)}[_chk]
    return None


def _apply_safety(vx, vy, w):
    """Phanh cứng theo LiDAR (cả lái tay lẫn tự chạy): đi về phía có vật cản gần hơn BLE_BRAKE_DIST_MM (+ quãng phanh theo tốc độ)
    thì bỏ phần tịnh tiến (vẫn cho xoay); gần tới đó thì giảm tốc dần. Khoảng cách tính từ tâm LiDAR."""
    v = math.sqrt(vx * vx + vy * vy)
    if config.HW_SAFETY and v > 0.02:
        phi = int(math.degrees(math.atan2(vy, vx)))
        stop = BRAKE_MM + int(v * 300.0)          # +3 cm mỗi 0.1 m/s: bù trễ LiDAR (~0.15 s) + quán tính khi chạy hở
        if _count_below(phi, 40, stop) >= 2:
            return 0.0, 0.0, w, True
        d = _min_dir(phi, 40)
        if d < stop + 350:
            k = (d - stop) / 350.0
            k = 0.35 if k < 0.35 else k
            return vx * k, vy * k, w, False
    return vx, vy, w, False


def _poll_button(now):
    global _btn_prev, _btn_ms
    if _btn is None:
        return
    v = _btn.value()
    if v == 0 and _btn_prev == 1 and time.ticks_diff(now, _btn_ms) > 400:     # vừa nhấn (nút kéo lên, nhấn = 0)
        _btn_ms = now
        set_mode(MODE_MANUAL if _mode == MODE_AUTO else MODE_AUTO, 'nút BOOT')
    _btn_prev = v


def init_all():
    global _wander, _btn, _btn_prev, _t_ctrl, _t_stat, _t_log, _t_gc, _t_scan, _ctl
    print("=" * 60)
    print("[GIUA KY] OOMWOO bản giữa kỳ: LiDAR tránh vật cản + điều khiển %s" % ('app Bluetooth' if CONTROL == 'ble' else 'web qua Wi-Fi'))
    print("[GIUA KY] Muốn quay lại bản quét bản đồ đủ cảm biến (Ubuntu/RViz2): nạp lại bản đó bằng biểu tượng của nó.")
    print("=" * 60)
    motor_lib.init()
    pe, kp, ki, ac = motor_lib.get_pid()
    motor_lib.set_pid(False, kp, ki, ac)                     # không dùng encoder -> chạy hở (có bù vùng chết + làm mượt)
    # Trần PWM của bản giữa kỳ (không sửa config.py): tốc độ bánh tối đa coi như tăng cùng tỉ lệ PWM để
    # tốc độ tự chạy (m/s) và quãng phanh vẫn đúng như cũ, còn lái tay đẩy hết cần ở 100% = PWM_MAX.
    old_lim = float(config.DEFAULT_SPEED_LIMIT)
    motor_lib.set_pwm_range(config.MIN_EFFECTIVE_PWM, PWM_MAX)
    new_lim = float(motor_lib.get_speed_limit())
    mn = float(config.MIN_EFFECTIVE_PWM)
    if old_lim > mn + 1:
        config.MAX_WHEEL_MPS = config.MAX_WHEEL_MPS * (new_lim - mn * 0.6) / (old_lim - mn * 0.6)
    print("[GIUA KY] PWM %d..%d%% (100%% tốc độ + hết cần = %d%% PWM) | tốc độ bánh tối đa ~%.2f m/s" % (
        mn, new_lim, new_lim, config.MAX_WHEEL_MPS))
    lidar_lib.init()
    _wander = wander_lib.Wander(_rand01)
    if PIN_BTN is not None:
        try:
            from machine import Pin
            _btn = Pin(PIN_BTN, Pin.IN, Pin.PULL_UP)
            _btn_prev = _btn.value()                      # nút đang bị giữ lúc khởi động thì không tính là một lần nhấn
        except Exception as e:
            print("[GIUA KY] Không dùng được nút chế độ:", e)
            _btn = None
    if CONTROL != 'ble':
        try:
            _ctl.init(name=str(_c('WEB_NAME', 'rccar')).lower(),
                      ssid=str(_c('HOTSPOT_SSID', getattr(config, 'WIFI_SSID', ''))),
                      password=str(_c('HOTSPOT_PASS', getattr(config, 'WIFI_PASS', ''))),
                      wait_s=int(_c('WIFI_WAIT_S', 20)), ap_fallback=bool(_c('AP_FALLBACK', True)),
                      ap_ssid=str(_c('AP_SSID', 'OOMWOO-XE')), ap_pass=str(_c('AP_PASS', '12345678')),
                      port=int(_c('WEB_PORT', 80)), wifi_mode=str(_c('WIFI_MODE', 'ap')),
                      ap_channel=int(_c('AP_CHANNEL', 6)), dns_port=int(_c('DNS_PORT', 53)))
        except Exception as e:
            print("[GIUA KY] LỖI Wi-Fi/web:", e, "-> chỉ dùng được nút BOOT để đổi chế độ")
            _ctl = None
    elif _ctl is not None:
        try:
            _ctl.init(BLE_NAME)
        except Exception as e:
            print("[GIUA KY] LỖI Bluetooth:", e, "-> chỉ dùng được nút BOOT để đổi chế độ")
    else:
        print("[GIUA KY] MicroPython này không có module bluetooth -> chỉ dùng được nút BOOT")
    now = _t()
    _t_ctrl = _t_stat = _t_log = _t_gc = _t_scan = now
    print("[GIUA KY] Sẵn sàng. Chế độ đầu: %s | tốc độ %d%%" % (mode_name(), _speed))


def step():
    global _last_sid, _t_scan, _safety, _stale, _cmd, _man, _t_ctrl, _t_stat, _t_log, _t_gc
    now = _t()
    lidar_lib.process_stream()

    sid = lidar_lib.scan_id()
    if sid != _last_sid:
        _last_sid = sid
        _t_scan = now
        t0 = time.ticks_us()
        raw = lidar_lib._last
        if not _mask.done and _cmd == (0.0, 0.0, 0.0):            # mới bật, xe đứng yên: học các tia chạm thân xe
            if _mask.add(raw):
                if _mask.n_masked:
                    print("[GIUA KY] Bỏ qua tia LiDAR chạm thân xe ở các góc (độ, mm):", _mask.ranges())
                else:
                    print("[GIUA KY] LiDAR không thấy thân xe (không có tia nào < 23 cm cố định).")
        _mask.apply(raw, _scan_m)
        if _fr_off == 0 and _fr_m == 1:
            for a in range(360):
                _scan_f[a] = _scan_m[a]
        else:                                                     # LiDAR lắp lệch / quay ngược: đổi về khung xe
            for a in range(360):
                _scan_f[a] = _scan_m[(_fr_off + _fr_m * a) % 360]
        _wander.scan(_scan_f)
        _wander.cpu_ms = time.ticks_diff(time.ticks_us(), t0) / 1000.0
    _stale = time.ticks_diff(now, _t_scan) > SCAN_STALE_MS

    if time.ticks_diff(now, _t_ctrl) < 20:                   # điều khiển 50 Hz
        return
    dt = time.ticks_diff(now, _t_ctrl) / 1000.0
    _t_ctrl = now
    if dt > 0.2:
        dt = 0.02

    if _ctl is not None:
        if CONTROL != 'ble':
            _ctl.poll()
        for ev in _ctl.events():
            if ev == 'C':
                print("[GIUA KY] Điện thoại đã kết nối")
                _send_status()
            elif ev == 'D':
                print("[GIUA KY] Điện thoại ngắt kết nối")
                _man = (0.0, 0.0, 0.0)
                if STOP_ON_DISCONNECT and _mode == MODE_AUTO:
                    set_mode(MODE_MANUAL, 'mất kết nối điện thoại -> dừng cho an toàn')
        handle_text(_ctl.read())
    _poll_button(now)

    if _mode == MODE_AUTO:
        chk = None
        if _stale or not _mask.done:
            vx = vy = w = 0.0                                     # mất LiDAR / chưa học xong thân xe: không tự chạy mù
        else:
            chk = _self_check(now, sid) if _chk != 'XONG' else None
            if chk is not None:
                vx, vy, w = chk
            else:
                vx, vy, w = _wander.control(dt, _speed / 60.0)
                w *= _wflip_auto
    else:
        if time.ticks_diff(now, _man_ms) > HOLD_MS:
            _man = (0.0, 0.0, 0.0)
        k = _speed / 100.0
        vmax = config.MAX_WHEEL_MPS                               # đẩy hết cần + tốc độ 100% = bánh quay ở PWM_MAX
        vx, vy, w = _man[0] * vmax * k, _man[1] * vmax * k, _man[2] * (vmax / config.MECANUM_L_SUM) * k
    vx, vy, w, _safety = _apply_safety(vx, vy, w)
    _cmd = (vx, vy, w)
    if vx == 0.0 and vy == 0.0 and w == 0.0:
        motor_lib.hard_stop()
    elif _chk in _CHK_RUN:
        motor_lib.drive_body(vx, vy, w, dt)                       # đang tự kiểm tra: lệnh đúng như config.py
    else:
        motor_lib.drive_body(vx, vy * _vyflip, w * _wflip, dt)

    if time.ticks_diff(now, _t_stat) >= 500:
        _t_stat = now
        _send_status()
    if time.ticks_diff(now, _t_gc) >= 1000:
        _t_gc = now
        gc.collect()
    if time.ticks_diff(now, _t_log) >= 3000:
        _t_log = now
        print("[GIUA KY] %s | %s | trước %.2f m | lệnh (%.2f, %.2f, %.2f) | BLE %s | quét #%d (xử lý %.0f ms)%s%s" % (
            mode_name(), _wander.state if _mode == MODE_AUTO else '-', _wander.front, vx, vy, w,
            'có' if (_ctl is not None and _ctl.is_connected()) else 'chưa', sid, _wander.cpu_ms,
            ' [PHANH AN TOAN]' if _safety else '', ' [MẤT LIDAR]' if _stale else ''))


async def _sleep_ms(ms):
    try:
        await asyncio.sleep_ms(ms)
    except AttributeError:
        await asyncio.sleep(ms / 1000.0)


async def main():
    global _errors
    init_all()
    while True:
        try:
            step()
            _errors = 0
        except KeyboardInterrupt:
            raise
        except Exception as e:
            motor_lib.dung_khan_cap()
            _errors += 1
            print("[GIUA KY-LỖI]", repr(e))
            if _errors > 5:
                import machine
                machine.reset()
            await _sleep_ms(200)
        await _sleep_ms(1)


def run():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        try:
            motor_lib.dung_khan_cap()
            lidar_lib.stop_lidar()
        except Exception:
            pass


if __name__ == "__main__":
    run()
