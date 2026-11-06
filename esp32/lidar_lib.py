from machine import Pin, UART
from array import array
import math
import config

# YDLidar X2 / X4: gói tin  AA 55 | CT | LSN | FSA(2) | LSA(2) | CS(2) | LSN mẫu x 2 byte
# Mỗi mẫu: khoảng cách (mm) = word >> 2

_uart = None
_motor_pin = None
_buffer = bytearray()

# 360 ô, mỗi ô 1 độ, giá trị = mm (0 = không có)  | góc 0° = mũi xe, tăng NGƯỢC chiều kim đồng hồ (chuẩn ROS)
_work = array('H', bytes(720))
_last = array('H', bytes(720))
_work_cnt = 0
_last_angle = 0.0
_scan_id = 0

_use_cs = True
_cs_ok = 0
_cs_fail = 0

# mẫu trước đó (toạ độ ô phân số + khoảng cách) để nội suy đúng về từng độ
_pc = 0.0
_pd = 0
_have_prev = False

_CW = bool(config.LIDAR_CLOCKWISE)
_OFF = float(config.LIDAR_ANGLE_OFFSET_DEG)
_MIN = int(config.LIDAR_MIN_MM)
_MAX = int(config.LIDAR_MAX_MM)
_ANGCOR = bool(config.LIDAR_ANGLE_CORRECT)


def init():
    global _uart, _motor_pin, _use_cs
    _use_cs = bool(config.LIDAR_CHECKSUM)
    _motor_pin = Pin(config.PIN_LIDAR_EN, Pin.OUT)
    _motor_pin.value(1)
    _uart = UART(1, baudrate=config.LIDAR_BAUD,
                 tx=Pin(config.PIN_LIDAR_TX),
                 rx=Pin(config.PIN_LIDAR_RX),
                 rxbuf=2048)
    print("[INIT] YDLidar 360-Degree Ready")


def stop_lidar():
    if _motor_pin:
        _motor_pin.value(0)


def _finish_scan():
    """Chốt 1 vòng quay: đổi bộ đệm làm việc thành bản quét hoàn chỉnh."""
    global _work, _last, _work_cnt, _scan_id, _have_prev
    _have_prev = False
    if _work_cnt >= 100:
        _last = _work
        _scan_id = (_scan_id + 1) & 0xFFFF
    _work = array('H', bytes(720))
    _work_cnt = 0


def process_stream():
    global _buffer, _last_angle, _work_cnt, _use_cs, _cs_ok, _cs_fail, _pc, _pd, _have_prev

    avail = _uart.any()
    if avail > 0:
        _buffer.extend(_uart.read(min(avail, 512)))

    if len(_buffer) > 1500:                 # tràn: bỏ bớt dữ liệu cũ
        _buffer = _buffer[-600:]

    packets = 0
    while len(_buffer) >= 10 and packets < 8:
        idx = _buffer.find(b'\xaa\x55')
        if idx == -1:
            _buffer = _buffer[-1:]
            break
        if idx > 0:
            _buffer = _buffer[idx:]
        if len(_buffer) < 10:
            break

        ct = _buffer[2]
        n = _buffer[3]
        if n == 0 or n > 80:
            _buffer = _buffer[2:]
            continue

        pkt_len = 10 + n * 2
        if len(_buffer) < pkt_len:
            break

        fsa = (_buffer[5] << 8) | _buffer[4]
        lsa = (_buffer[7] << 8) | _buffer[6]

        if _use_cs:
            cs = 0x55AA ^ fsa ^ lsa ^ ((n << 8) | ct)
            for k in range(10, pkt_len, 2):
                cs ^= (_buffer[k + 1] << 8) | _buffer[k]
            got = (_buffer[9] << 8) | _buffer[8]
            if cs != got:
                _cs_fail += 1
                if _cs_ok == 0 and _cs_fail >= 30:
                    _use_cs = False
                    print("[LIDAR] Checksum luôn sai -> tắt kiểm tra checksum (LiDAR của bạn dùng công thức khác)")
                _buffer = _buffer[2:]
                continue
            _cs_ok += 1

        start_deg = (fsa >> 1) / 64.0
        end_deg = (lsa >> 1) / 64.0

        if ct & 1:
            # gói "điểm 0°": bắt đầu vòng quay mới
            _finish_scan()
        else:
            diff = end_deg - start_deg
            if diff < 0:
                diff += 360.0
            step = diff / max(1, n - 1)
            for i in range(n):
                off = 10 + i * 2
                d = ((_buffer[off + 1] << 8) | _buffer[off]) >> 2
                if d < _MIN or d > _MAX:
                    d = 0
                ang = start_deg + i * step
                if d and _ANGCOR:
                    ang += math.degrees(math.atan(21.8 * (155.3 - d) / (155.3 * d)))
                # toạ độ "ô" phân số: LiDAR quay CW thì ô giảm dần theo thứ tự mẫu, ngược lại tăng dần
                c = (_OFF - ang) if _CW else (ang + _OFF)
                if _have_prev:
                    dc = c - _pc
                    if -3.0 < dc < 3.0 and dc != 0.0:
                        if dc > 0:
                            k0 = math.ceil(_pc)
                            k1 = math.floor(c)
                        else:
                            k0 = math.ceil(c)
                            k1 = math.floor(_pc)
                        both = d and _pd and abs(d - _pd) <= (0.12 * max(d, _pd) + 25)
                        for k in range(k0, k1 + 1):
                            if both:
                                v = int(_pd + (d - _pd) * (k - _pc) / dc)
                            elif abs(k - _pc) <= abs(k - c):
                                v = _pd
                            else:
                                v = d
                            if v:
                                _work[k % 360] = v
                                _work_cnt += 1
                _pc = c
                _pd = d
                _have_prev = True
            if end_deg < _last_angle - 180.0:     # góc quay về 0 -> hết vòng
                _finish_scan()
        _last_angle = end_deg

        _buffer = _buffer[pkt_len:]
        packets += 1


def scan_id():
    """Tăng 1 mỗi khi có vòng quét mới."""
    return _scan_id


def get_scan_bytes():
    """360 giá trị uint16 little-endian (mm), 720 byte, dùng gửi thẳng qua UDP."""
    return bytes(_last)


def get_scan_list():
    return list(_last)


def min_in_dir_mm(deg_ccw, half_width_deg=35):
    """Khoảng cách gần nhất (mm) trong cung +-half_width quanh hướng deg_ccw (0° = mũi xe). 9999 nếu trống."""
    c = int(deg_ccw) % 360
    best = 9999
    for k in range(-half_width_deg, half_width_deg + 1):
        d = _last[(c + k) % 360]
        if d and d < best:
            best = d
    return best


def count_below_mm(deg_ccw, half_width_deg, thr_mm):
    """Số ô có vật cản gần hơn thr_mm trong cung quanh hướng deg_ccw (để loại nhiễu đơn lẻ)."""
    c = int(deg_ccw) % 360
    n = 0
    for k in range(-half_width_deg, half_width_deg + 1):
        d = _last[(c + k) % 360]
        if d and d < thr_mm:
            n += 1
    return n


def get_full_scan():
    """120 điểm cách nhau 3 độ (tương thích bản cũ)."""
    return [_last[i] for i in range(0, 360, 3)]


def get_sectors_mm():
    """4 hướng trước/trái/sau/phải (tương thích bản cũ)."""
    return (
        _last[0] if _last[0] > 0 else 9999,
        _last[90] if _last[90] > 0 else 9999,
        _last[180] if _last[180] > 0 else 9999,
        _last[270] if _last[270] > 0 else 9999
    )
