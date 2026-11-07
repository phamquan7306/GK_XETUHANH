import socket
import time

import network

try:
    import select
except ImportError:
    import uselect as select
try:
    import hashlib
except ImportError:
    import uhashlib as hashlib
try:
    import binascii
except ImportError:
    import ubinascii as binascii

import web_page

_WS_GUID = b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
IDLE_MS = 3000           # WebSocket im lặng quá lâu (điện thoại tắt màn hình / ra khỏi sóng) -> coi như mất kết nối

_sta = None
_ap = None
_srv = None
_dns = None              # máy chủ DNS mini (chỉ khi xe tự phát Wi-Fi): mọi tên miền -> IP của xe
_ip_b = b'\xc0\xa8\x04\x01'
_poll = None
_ws = None               # socket WebSocket đang điều khiển (1 điện thoại)
_ws_buf = b''
_ws_last = 0
_inbox = []
_events = []
_pend = {}               # kết nối HTTP mới đang chờ đủ phần đầu yêu cầu: socket -> [dữ liệu, lúc mở] (không chặn vòng lặp)
_ip = None
_mode = ''               # 'STA' (vào Wi-Fi điện thoại) / 'AP' (tự phát) / ''
_cfg = None
_t_retry = 0
_port = 80


def _t():
    return time.ticks_ms()


def ip():
    return _ip


def mode():
    return _mode


def _set_hostname(name):
    try:
        network.hostname(name)                 # MicroPython >= 1.20: tên mDNS -> http://<name>.local
        return
    except Exception:
        pass
    try:
        _sta.config(dhcp_hostname=name)
    except Exception:
        pass


def _start_ap(c, fallback=True):
    """ESP32 tự phát Wi-Fi (Access Point). Web luôn ở http://192.168.4.1"""
    global _ap, _ip, _mode
    pw = c['ap_pass'] if len(c['ap_pass']) >= 8 else '12345678'     # WPA2 cần >= 8 ký tự
    _ap = network.WLAN(network.AP_IF)
    _ap.active(True)
    for kw in (dict(essid=c['ap_ssid'], password=pw, authmode=3, channel=c['ap_channel'], max_clients=3),
               dict(essid=c['ap_ssid'], password=pw, authmode=3), dict(essid=c['ap_ssid'], password=pw)):
        try:
            _ap.config(**kw)
            break
        except Exception:
            continue
    try:                                        # DHCP của xe báo điện thoại dùng chính xe làm DNS (để tên dễ nhớ chạy được)
        ip0 = _ap.ifconfig()[0]
        _ap.ifconfig((ip0, '255.255.255.0', ip0, ip0))
    except Exception:
        pass
    _ip = _ap.ifconfig()[0]
    _mode = 'AP'
    if fallback:
        print("[WIFI] Không vào được Wi-Fi '%s' -> xe TỰ PHÁT Wi-Fi riêng." % c['ssid'])
    print("[WIFI] XE ĐANG PHÁT Wi-Fi '%s' (mật khẩu %s). Điện thoại vào Wi-Fi đó rồi mở Chrome:  http://%s" % (
        c['ap_ssid'], pw, _ip))


def init(name='rccar', ssid='', password='', wait_s=20, ap_fallback=True, ap_ssid='OOMWOO-XE', ap_pass='12345678', port=80,
         wifi_mode='ap', ap_channel=6, dns_port=53):
    """wifi_mode 'ap': ESP32 tự phát Wi-Fi (không cần Wi-Fi ngoài) | 'sta': vào Wi-Fi điện thoại phát (chặn tối đa wait_s giây).
    Sau đó mở web server cổng 80."""
    global _sta, _cfg, _ip, _mode, _srv, _poll, _port, _dns, _ip_b
    _cfg = dict(name=name, ssid=ssid, password=password, ap_ssid=ap_ssid, ap_pass=ap_pass, ap_channel=ap_channel)
    _port = port
    _sta = network.WLAN(network.STA_IF)
    _set_hostname(name)
    if wifi_mode == 'ap':
        _sta.active(False)                      # chỉ phát, không đi tìm Wi-Fi khác (đỡ nhảy kênh, ổn định hơn)
        _cfg['ssid'] = ''
        _start_ap(_cfg, fallback=False)
        ssid = ''
    else:
        _sta.active(True)
        try:
            _sta.config(pm=0xa11140)           # tắt tiết kiệm điện Wi-Fi: lệnh tới nhanh hơn
        except Exception:
            pass
    if ssid:
        print("[WIFI] Đang vào Wi-Fi điện thoại '%s' (điện thoại phải bật Điểm phát sóng, băng tần 2.4 GHz) ..." % ssid)
        if not _sta.isconnected():
            try:
                _sta.connect(ssid, password)
            except Exception as e:
                print("[WIFI] Lỗi:", e)
        t0 = _t()
        while not _sta.isconnected() and time.ticks_diff(_t(), t0) < wait_s * 1000:
            time.sleep_ms(200)
    if _mode == 'AP':
        pass
    elif _sta.isconnected():
        _ip = _sta.ifconfig()[0]
        _mode = 'STA'
        print("[WIFI] ĐÃ VÀO Wi-Fi '%s'. Trên điện thoại mở Chrome:  http://%s   (hoặc http://%s.local)" % (ssid, _ip, name))
    elif ap_fallback:
        _start_ap(_cfg)
    else:
        print("[WIFI] Chưa vào được Wi-Fi '%s', sẽ thử lại liên tục." % ssid)
    a = socket.getaddrinfo('0.0.0.0', port)[0][-1]
    _srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _srv.bind(a)
    _srv.listen(3)
    _srv.setblocking(False)
    _poll = select.poll()
    _poll.register(_srv, select.POLLIN)
    print("[WEB] Trang điều khiển ở cổng %d" % port)
    if _mode == 'AP':
        # Điện thoại vào Wi-Fi của xe nhận luôn xe làm máy chủ DNS -> trả lời MỌI tên bằng IP của xe:
        # gõ http://local.rccar, http://rccar.local, http://rccar ... đều ra trang điều khiển.
        try:
            _ip_b = bytes(int(x) for x in _ip.split('.'))
            _dns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            _dns.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            _dns.bind(socket.getaddrinfo('0.0.0.0', dns_port)[0][-1])
            _dns.setblocking(False)
            _poll.register(_dns, select.POLLIN)
            print("[WEB] Tên dễ nhớ: http://local.%s  hoặc  http://%s.local  (gõ đủ http://), hoặc http://%s" % (name, name, _ip))
        except Exception as e:
            _dns = None
            print("[WEB] Không mở được DNS (%s) -> dùng http://%s" % (e, _ip))


def _keep_wifi():
    """Rớt Wi-Fi điện thoại thì thử vào lại (không chặn vòng lặp)."""
    global _t_retry, _ip, _mode
    if _mode == 'AP' or _sta is None or not _cfg['ssid']:
        return
    if _sta.isconnected():
        if _mode != 'STA':
            _ip = _sta.ifconfig()[0]
            _mode = 'STA'
            print("[WIFI] Đã vào lại Wi-Fi điện thoại: http://%s" % _ip)
        return
    if _mode == 'STA':
        _mode = ''
        print("[WIFI] Mất Wi-Fi điện thoại, đang thử vào lại ...")
    if time.ticks_diff(_t(), _t_retry) > 5000:
        _t_retry = _t()
        try:
            _sta.connect(_cfg['ssid'], _cfg['password'])
        except Exception:
            pass


def is_connected():
    return _ws is not None


def events():
    global _events
    if not _events:
        return ()
    ev = _events
    _events = []
    return ev


def read():
    """Toàn bộ lệnh (chuỗi) điện thoại gửi từ lần gọi trước, nối bằng ';'."""
    global _inbox
    if not _inbox:
        return b''
    s = ';'.join(_inbox)
    _inbox = []
    return s.encode()


def _ws_send(sock, payload, opcode=1):
    if isinstance(payload, str):
        payload = payload.encode()
    n = len(payload)
    if n < 126:
        hdr = bytes((0x80 | opcode, n))
    else:
        hdr = bytes((0x80 | opcode, 126, n >> 8, n & 255))
    sock.send(hdr + payload)


def send(text):
    """Gửi 1 dòng trạng thái sang trang web (WebSocket)."""
    if _ws is None:
        return
    try:
        _ws_send(_ws, text)
    except OSError:
        _drop_ws('gửi lỗi')


def _drop_ws(why=''):
    global _ws, _ws_buf
    if _ws is None:
        return
    try:
        _poll.unregister(_ws)
    except Exception:
        pass
    try:
        _ws.close()
    except Exception:
        pass
    _ws = None
    _ws_buf = b''
    _events.append('D')
    if why:
        print("[WEB] Điện thoại ngắt (%s)" % why)


def _http(c, code, ctype, body):
    if isinstance(body, str):
        body = body.encode()
    head = ('HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n'
            % (code, ctype, len(body))).encode()
    c.settimeout(3.0)
    c.sendall(head)
    mv = memoryview(body)
    for i in range(0, len(body), 1024):
        c.sendall(mv[i:i + 1024])


def _accept():
    try:
        c, addr = _srv.accept()
    except OSError:
        return
    if len(_pend) >= 4:                         # quá nhiều kết nối treo (trình duyệt mở sẵn) -> bỏ cái cũ nhất
        old = min(_pend, key=lambda k: _pend[k][1])
        _close_pend(old)
    c.setblocking(False)
    _pend[c] = [b'', _t(), addr]
    _poll.register(c, select.POLLIN)


def _close_pend(c):
    _pend.pop(c, None)
    try:
        _poll.unregister(c)
    except Exception:
        pass
    try:
        c.close()
    except Exception:
        pass


def _handle(c, req, addr):
    """Đã có đủ phần đầu yêu cầu HTTP -> trả trang web hoặc nâng cấp lên WebSocket."""
    global _ws, _ws_buf, _ws_last
    line = req.split(b'\r\n', 1)[0]
    parts = line.split(b' ')
    path = parts[1] if len(parts) > 1 else b'/'
    key = None
    for h in req.split(b'\r\n'):
        if h.lower().startswith(b'sec-websocket-key:'):
            key = h.split(b':', 1)[1].strip()
    if path.startswith(b'/ws') and key:
        acc = binascii.b2a_base64(hashlib.sha1(key + _WS_GUID).digest()).strip()
        c.setblocking(True)
        c.settimeout(2.0)
        c.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                  b'Sec-WebSocket-Accept: ' + acc + b'\r\n\r\n')
        c.setblocking(False)
        if _ws is not None:                     # điện thoại mới (hoặc trang tải lại) -> thay kết nối cũ
            _drop_ws('kết nối mới thay thế')
        _ws = c
        _ws_buf = b''
        _ws_last = _t()
        _poll.register(_ws, select.POLLIN)
        _events.append('C')
        print("[WEB] Điện thoại đã kết nối:", addr[0] if isinstance(addr, tuple) else addr)
        return True                             # giữ socket
    if path == b'/' or path.startswith(b'/?') or path.startswith(b'/index'):
        _http(c, '200 OK', 'text/html; charset=utf-8', web_page.HTML)
    elif path.startswith(b'/generate_204') or path.startswith(b'/gen_204'):
        _http(c, '204 No Content', 'text/plain', b'')      # Android: "mạng này dùng được" -> không tự ngắt Wi-Fi của xe
    elif path.startswith(b'/hotspot-detect') or path.startswith(b'/library/test/success'):
        _http(c, '200 OK', 'text/html', b'<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>')   # iPhone
    else:
        _http(c, '404 Not Found', 'text/plain; charset=utf-8', 'Không có trang này. Mở /')
    return False


def _pend_read(c):
    ent = _pend.get(c)
    if ent is None:
        return
    try:
        d = c.recv(512)
    except OSError:
        return
    if not d:
        _close_pend(c)
        return
    ent[0] += d
    if b'\r\n\r\n' in ent[0] or len(ent[0]) > 2048:
        _pend.pop(c, None)
        try:
            _poll.unregister(c)
        except Exception:
            pass
        keep = False
        try:
            keep = _handle(c, ent[0], ent[2])
        except OSError:
            pass
        if not keep:
            try:
                c.close()
            except Exception:
                pass


def _ws_parse():
    """Tách các khung WebSocket (client -> server luôn có mặt nạ)."""
    global _ws_buf
    b = _ws_buf
    while len(b) >= 2:
        op = b[0] & 0x0F
        masked = b[1] & 0x80
        n = b[1] & 0x7F
        i = 2
        if n == 126:
            if len(b) < 4:
                break
            n = (b[2] << 8) | b[3]
            i = 4
        elif n == 127:                          # không dùng khung lớn như vậy
            _drop_ws('khung quá lớn')
            return
        if masked:
            if len(b) < i + 4 + n:
                break
            mk = b[i:i + 4]
            i += 4
            data = bytes(b[i + k] ^ mk[k & 3] for k in range(n))
        else:
            if len(b) < i + n:
                break
            data = bytes(b[i:i + n])
        b = b[i + n:]
        if op == 1 or op == 2:
            try:
                _inbox.append(data.decode())
            except Exception:
                pass
        elif op == 8:
            _ws_buf = b''
            _drop_ws('đóng trang')
            return
        elif op == 9:
            try:
                _ws_send(_ws, data, 10)
            except OSError:
                pass
    _ws_buf = b


def _dns_reply():
    """Trả lời 1 câu hỏi DNS: bản ghi A -> IP của xe; loại khác (AAAA...) -> không có, để máy hỏi lại bản ghi A."""
    try:
        q, addr = _dns.recvfrom(512)
    except OSError:
        return
    if len(q) < 17 or q[2] & 0x80:              # quá ngắn / không phải câu hỏi
        return
    i = 12
    while i < len(q) and q[i] != 0:             # bỏ qua tên miền (dãy nhãn)
        i += q[i] + 1
    if i + 5 > len(q):
        return
    qtype = (q[i + 1] << 8) | q[i + 2]
    question = q[12:i + 5]
    if qtype == 1 or qtype == 255:
        ans = b'\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04' + _ip_b     # trỏ tới tên ở câu hỏi, A, IN, TTL 60 s
        head = q[0:2] + b'\x85\x80\x00\x01\x00\x01\x00\x00\x00\x00'
    else:
        ans = b''
        head = q[0:2] + b'\x85\x80\x00\x01\x00\x00\x00\x00\x00\x00'
    try:
        _dns.sendto(head + question + ans, addr)
    except OSError:
        pass


def poll():
    """Gọi thường xuyên từ vòng lặp chính (không chặn)."""
    global _ws_buf, _ws_last
    if _poll is None:
        return
    _keep_wifi()
    for item in _poll.poll(0):
        obj = item[0]
        if isinstance(obj, int):                   # CPython (chạy thử trên máy tính) trả số fd
            fd = obj
            obj = None
            for k in [_srv, _ws, _dns] + list(_pend):
                if k is not None and k.fileno() == fd:
                    obj = k
                    break
        if obj is _srv:
            _accept()
        elif obj is not None and obj is _dns:
            _dns_reply()
        elif obj in _pend:
            _pend_read(obj)
        elif obj is not None and obj is _ws:
            try:
                d = _ws.recv(512)
            except OSError:
                continue
            if not d:
                _drop_ws('mất kết nối')
                continue
            _ws_buf += d
            _ws_last = _t()
            _ws_parse()
    for c in [k for k, v in _pend.items() if time.ticks_diff(_t(), v[1]) > 3000]:
        _close_pend(c)                          # trình duyệt mở sẵn kết nối mà không hỏi gì -> đóng sau 3 s
    if _ws is not None and time.ticks_diff(_t(), _ws_last) > IDLE_MS:
        _drop_ws('quá %d s không nhận được gì' % (IDLE_MS // 1000))
