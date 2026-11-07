import bluetooth
from micropython import const

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)
_IRQ_MTU_EXCHANGED = const(21)

_F_READ = const(0x0002)
_F_WRITE_NR = const(0x0004)
_F_WRITE = const(0x0008)
_F_NOTIFY = const(0x0010)

NUS_UUID = '6E400001-B5A3-F393-E0A9-E50E24DCCA9E'
RX_UUID = '6E400002-B5A3-F393-E0A9-E50E24DCCA9E'
TX_UUID = '6E400003-B5A3-F393-E0A9-E50E24DCCA9E'

_ble = None
_h_tx = None
_h_rx = None
_conns = set()
_inbox = bytearray()
_events = []          # 'C' = vừa kết nối, 'D' = vừa mất kết nối (vòng lặp chính đọc qua events())
_mtu = 23
_adv = None
_resp = None


def _adv_payload(name):
    nb = name.encode() if isinstance(name, str) else bytes(name)
    nb = nb[:26]
    adv = bytes((2, 0x01, 0x06)) + bytes((len(nb) + 1, 0x09)) + nb        # cờ "chỉ BLE" + tên đầy đủ
    u = bytes(bluetooth.UUID(NUS_UUID))
    resp = bytes((len(u) + 1, 0x07)) + u                                   # UUID dịch vụ trong gói trả lời quét
    return adv, resp


def _advertise():
    try:
        _ble.gap_advertise(100000, adv_data=_adv, resp_data=_resp)        # 100 ms
    except OSError as e:
        print("[BLE] Không quảng bá được:", e)


def _irq(event, data):
    global _mtu, _inbox
    if event == _IRQ_CENTRAL_CONNECT:
        conn = data[0]
        _conns.add(conn)
        _events.append('C')
    elif event == _IRQ_CENTRAL_DISCONNECT:
        conn = data[0]
        _conns.discard(conn)
        _events.append('D')
        _mtu = 23
        _advertise()
    elif event == _IRQ_GATTS_WRITE:
        conn, h = data[0], data[1]
        if h == _h_rx:
            _inbox.extend(_ble.gatts_read(_h_rx))
            if len(_inbox) > 256:                   # không bao giờ để bộ đệm phình mãi
                _inbox = _inbox[len(_inbox) - 256:]
    elif event == _IRQ_MTU_EXCHANGED:
        _mtu = data[1]


def init(name='OOMWOO'):
    global _ble, _h_tx, _h_rx, _adv, _resp
    _ble = bluetooth.BLE()
    _ble.active(True)
    try:
        _ble.config(gap_name=name)
    except Exception:
        pass
    try:
        _ble.config(mtu=128)
    except Exception:
        pass
    svc = (bluetooth.UUID(NUS_UUID), ((bluetooth.UUID(TX_UUID), _F_READ | _F_NOTIFY),
                                      (bluetooth.UUID(RX_UUID), _F_WRITE | _F_WRITE_NR)))
    ((_h_tx, _h_rx),) = _ble.gatts_register_services((svc,))
    _ble.gatts_set_buffer(_h_rx, 128, True)        # True = nối tiếp: nhiều lệnh tới liền nhau không bị mất
    _ble.irq(_irq)
    _adv, _resp = _adv_payload(name)
    _advertise()
    print("[BLE] Đang quảng bá tên '%s' - mở app trên điện thoại rồi bấm KẾT NỐI" % name)


def is_connected():
    return len(_conns) > 0


def events():
    """Các sự kiện kết nối/mất kết nối từ lần gọi trước ('C' / 'D')."""
    global _events
    if not _events:
        return ()
    ev = _events
    _events = []
    return ev


def read():
    """Lấy toàn bộ byte điện thoại đã gửi từ lần gọi trước (rỗng nếu không có)."""
    global _inbox
    if not _inbox:
        return b''
    b = _inbox                     # đổi bộ đệm trước rồi mới đọc: lệnh tới giữa chừng vẫn nằm trong b
    _inbox = bytearray()
    return bytes(b)


def send(text):
    """Gửi một dòng trạng thái ngắn sang điện thoại (cắt theo MTU, mặc định 20 byte)."""
    if not _conns:
        return
    data = text.encode() if isinstance(text, str) else text
    data = data[:max(20, _mtu - 3)]
    try:
        _ble.gatts_write(_h_tx, data)
    except Exception:
        pass
    for c in list(_conns):
        try:
            _ble.gatts_notify(c, _h_tx, data)
        except Exception:
            pass
