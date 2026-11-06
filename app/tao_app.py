#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OOMWOO - tạo project MIT App Inventor (.aia) cho app Android điều khiển xe qua Bluetooth (BLE).

ESP32-S3 chỉ có Bluetooth Low Energy nên app cần extension BluetoothLE CHÍNH THỨC của MIT
(không đi kèm ở đây vì là file của MIT, tải 1 lần):
    https://mit-cml.github.io/extensions/  ->  BluetoothLE  ->  tải file edu.mit.appinventor.ble-XXXXXXXX.aix

Cách dùng (trên Ubuntu):
    python3 tao_app.py                              # tự tìm file *.aix trong ~/Downloads (~/Tải xuống), không có thì tự tải
    python3 tao_app.py ~/Downloads/edu.mit.appinventor.ble-20240822.aix
    python3 tao_app.py --ten-xe OOMWOO2             # nếu đổi BLE_NAME trong esp32_giuaky/giuaky_config.py
=> tạo file OomwooBLE.aia cạnh script này. Mở https://ai2.appinventor.mit.edu -> Projects -> Import project (.aia)
   -> Build -> Android App (.apk) -> quét mã QR bằng điện thoại để cài.
"""
import argparse
import glob
import io
import json
import os
import sys
import zipfile
from xml.sax.saxutils import escape

PROJECT = 'OomwooBLE'
USER = 'ai_oomwoo'
NUS = '6E400001-B5A3-F393-E0A9-E50E24DCCA9E'
RX = '6E400002-B5A3-F393-E0A9-E50E24DCCA9E'
TX = '6E400003-B5A3-F393-E0A9-E50E24DCCA9E'

# Phiên bản định dạng: lấy theo project mẫu chính thức của App Inventor (YaVersion 208 / blocks 33).
# Bản App Inventor mới hơn sẽ tự nâng cấp khi import; không dùng số mới hơn để tránh lỗi "project của phiên bản mới hơn".
YA_VERSION = '208'
LANG_VERSION = '33'
V = dict(Form='27', Button='6', Label='4', Slider='2', Clock='4', HorizontalArrangement='3', VerticalArrangement='3', Canvas='13')

ORANGE = '&HFFFF9800'
GREEN = '&HFF4CAF50'
RED = '&HFFE53935'
BLUE = '&HFF1E88E5'
GRAY = '&HFF9E9E9E'
DARK = '&HFF37474F'
WHITE = '&HFFFFFFFF'
BG = '&HFF263238'
PAD = '&HFF37474F'
CANVAS = 190                     # px: cạnh vùng joystick (vừa màn hình ngang 320 px)
KNOB = 26                        # px: bán kính núm joystick
ASSETS = ('joy_move.png', 'joy_turn.png')   # ảnh nền joystick (ve_joystick.py)

_uuid = [1000]


def uid():
    _uuid[0] += 7919
    return str(_uuid[0])


def comp(ctype, name, **props):
    d = {'$Name': name, '$Type': ctype, '$Version': V.get(ctype, '1')}
    d.update({k: str(v) for k, v in props.items()})
    d['Uuid'] = uid()
    return d


def button(name, text, bg, h=80, w=-1031, fs=18):
    return comp('Button', name, Text=text, BackgroundColor=bg, TextColor=WHITE, FontBold='True', FontSize=fs,
                Shape='1', Height=h, Width=w)


def label(name, text, fs=14, color=WHITE, **kw):
    return comp('Label', name, Text=text, FontSize=fs, TextColor=color, **kw)


def build_scm(ble_version):
    top_row = comp('HorizontalArrangement', 'HangTren', AlignVertical='2', Width='-2')
    top_row['$Components'] = [button('BtnKetNoi', 'KẾT NỐI XE', GREEN, h=42, w=-1022, fs=16),
                              button('BtnNgat', 'NGẮT', DARK, h=42, w=-1012, fs=16),
                              label('LblTrangThai', '  Chưa kết nối – bấm KẾT NỐI XE', 15, Width='-2')]
    left = comp('VerticalArrangement', 'CotTrai', AlignHorizontal='3')
    left['$Components'] = [comp('Canvas', 'CanvasDiChuyen', Width=CANVAS, Height=CANVAS, BackgroundColor=PAD, PaintColor=BLUE, BackgroundImage='joy_move.png',
                                LineWidth='4', TapThreshold='3'),
                           label('LblDiChuyen', 'DI CHUYỂN: tiến/lùi + trượt ngang', 13)]
    mid = comp('VerticalArrangement', 'CotGiua', AlignHorizontal='3', Width='-2')
    mid['$Components'] = [button('BtnCheDo', 'CHẾ ĐỘ: --', GRAY, h=56, w=-2, fs=16),
                          button('BtnDung', '■ DỪNG', RED, h=56, w=-2, fs=20),
                          label('LblTocDo', 'Tốc độ: 60%', 15),
                          comp('Slider', 'SliderTocDo', MinValue='20', MaxValue='100', ThumbPosition='60', Width='-2', ColorLeft=BLUE)]
    right = comp('VerticalArrangement', 'CotPhai', AlignHorizontal='3')
    right['$Components'] = [comp('Canvas', 'CanvasXoay', Width=CANVAS, Height=CANVAS, BackgroundColor=PAD, PaintColor=ORANGE, BackgroundImage='joy_turn.png',
                                 LineWidth='4', TapThreshold='3'),
                            label('LblXoay', 'XOAY: gạt trái / phải', 13)]
    main_row = comp('HorizontalArrangement', 'HangChinh', AlignVertical='2', Width='-2')
    main_row['$Components'] = [left, mid, right]
    top = [top_row, main_row,
           comp('Clock', 'Clock1', TimerInterval='100', TimerAlwaysFires='False'),
           {'$Name': 'BluetoothLE1', '$Type': 'BluetoothLE', '$Version': str(ble_version), 'NullTerminateStrings': 'False',
            'Uuid': uid()}]
    form = {'$Name': 'Screen1', '$Type': 'Form', '$Version': V['Form'], 'AlignHorizontal': '3', 'AppName': 'OOMWOO',
            'BackgroundColor': BG, 'ScreenOrientation': 'landscape', 'Scrollable': 'False', 'Sizing': 'Responsive',
            'Title': 'OOMWOO joystick', 'TitleVisible': 'False',
            'Theme': 'AppTheme.Light.DarkActionBar', 'PrimaryColor': '&HFF1E88E5', 'PrimaryColorDark': '&HFF1565C0',
            'AccentColor': '&HFFFF9800', 'ShowListsAsJson': 'True', 'VersionCode': '2', 'VersionName': '2.0',
            'Uuid': '0', '$Components': top}
    data = {'authURL': ['ai2.appinventor.mit.edu'], 'YaVersion': YA_VERSION, 'Source': 'Form', 'Properties': form}
    return '#|\n$JSON\n' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n|#\n'


# ------------------------------- khối lệnh (Blockly XML) -------------------------------
def T(s):
    return f'<block type="text"><field name="TEXT">{escape(s)}</field></block>'


def G(name):
    return f'<block type="lexical_variable_get"><field name="VAR">{escape(name)}</field></block>'


def SETG(name, value_xml):
    return f'<block type="lexical_variable_set"><field name="VAR">{escape(name)}</field><value name="VALUE">{value_xml}</value></block>'


def BOOL(b):
    return f'<block type="logic_boolean"><field name="BOOL">{"TRUE" if b else "FALSE"}</field></block>'


def SETP(ctype, inst, prop, value_xml):
    return (f'<block type="component_set_get"><mutation component_type="{ctype}" set_or_get="set" property_name="{prop}" '
            f'is_generic="false" instance_name="{inst}"></mutation><field name="COMPONENT_SELECTOR">{inst}</field>'
            f'<field name="PROP">{prop}</field><value name="VALUE">{value_xml}</value></block>')


def GETP(ctype, inst, prop):
    return (f'<block type="component_set_get"><mutation component_type="{ctype}" set_or_get="get" property_name="{prop}" '
            f'is_generic="false" instance_name="{inst}"></mutation><field name="COMPONENT_SELECTOR">{inst}</field>'
            f'<field name="PROP">{prop}</field></block>')


def CALLM(ctype, inst, method, args):
    vals = ''.join(f'<value name="ARG{i}">{a}</value>' for i, a in enumerate(args))
    return (f'<block type="component_method"><mutation component_type="{ctype}" method_name="{method}" is_generic="false" '
            f'instance_name="{inst}"></mutation><field name="COMPONENT_SELECTOR">{inst}</field>{vals}</block>')


def EVENT(ctype, inst, event, body, x, y):
    return (f'<block type="component_event" x="{x}" y="{y}"><mutation component_type="{ctype}" is_generic="false" '
            f'instance_name="{inst}" event_name="{event}"></mutation><field name="COMPONENT_SELECTOR">{inst}</field>'
            f'<statement name="DO">{R(body)}</statement></block>')


def CALLP(name, args):
    argdecl = ''.join(f'<arg name="{escape(a)}"></arg>' for a, _ in args)
    vals = ''.join(f'<value name="ARG{i}">{v}</value>' for i, (_, v) in enumerate(args))
    return (f'<block type="procedures_callnoreturn"><mutation name="{name}">{argdecl}</mutation>'
            f'<field name="PROCNAME">{name}</field>{vals}</block>')


def GUI(value_xml):
    return CALLP('gui', [('lenhGui', value_xml)])


def IF(cond, then, els=None):
    if els is None:
        return f'<block type="controls_if"><value name="IF0">{cond}</value><statement name="DO0">{R(then)}</statement></block>'
    return (f'<block type="controls_if"><mutation else="1"></mutation><value name="IF0">{cond}</value>'
            f'<statement name="DO0">{R(then)}</statement><statement name="ELSE">{R(els)}</statement></block>')


def NOT(x):
    return f'<block type="logic_negate"><value name="BOOL">{x}</value></block>'


def ISEMPTY_TEXT(x):
    return f'<block type="text_isEmpty"><value name="VALUE">{x}</value></block>'


def ISEMPTY_LIST(x):
    return f'<block type="lists_is_empty"><value name="LIST">{x}</value></block>'


def JOIN(*parts):
    vals = ''.join(f'<value name="ADD{i}">{p}</value>' for i, p in enumerate(parts))
    return f'<block type="text_join"><mutation items="{len(parts)}"></mutation>{vals}</block>'


def CONTAINS(text, piece):
    return (f'<block type="text_contains"><mutation mode="CONTAINS"></mutation><field name="OP">CONTAINS</field>'
            f'<value name="TEXT">{text}</value><value name="PIECE">{piece}</value></block>')


def ROUND(x):
    return f'<block type="math_round"><field name="OP">ROUND</field><value name="NUM">{x}</value></block>'


def ITEM1(lst):
    return f'<block type="lists_select_item"><value name="LIST">{lst}</value><value name="NUM">{NUM(1)}</value></block>'


def NUM(n):
    return f'<block type="math_number"><field name="NUM">{n}</field></block>'


def COLOR(hexrgb):
    r, g, b = int(hexrgb[0:2], 16), int(hexrgb[2:4], 16), int(hexrgb[4:6], 16)
    return (f'<block type="color_make_color"><value name="COLORLIST"><block type="lists_create_with"><mutation items="3"></mutation>'
            f'<value name="ADD0">{NUM(r)}</value><value name="ADD1">{NUM(g)}</value><value name="ADD2">{NUM(b)}</value></block></value></block>')


def _flat(x):
    if isinstance(x, (list, tuple)):
        out = []
        for e in x:
            out += _flat(e)
        return out
    return [x] if x else []


def seq(*blocks):
    """Chuỗi khối lệnh (danh sách phẳng); R() mới ghép thành XML lồng <next>. Chuỗi lồng chuỗi vẫn đúng thứ tự."""
    return _flat(blocks)


def R(chain):
    blocks = _flat(chain)
    if not blocks:
        return ''
    out = blocks[-1]
    for b in reversed(blocks[:-1]):
        assert b.endswith('</block>') and '<next>' not in b[-60:]
        out = b[:-len('</block>')] + f'<next>{out}</next></block>'
    return out


def ARITH(kind, a, b):
    return f'<block type="math_{kind}"><value name="A">{a}</value><value name="B">{b}</value></block>'


def SUB(a, b):
    return ARITH('subtract', a, b)


def DIV(a, b):
    return ARITH('division', a, b)


def MUL(*xs):
    vals = ''.join(f'<value name="NUM{i}">{x}</value>' for i, x in enumerate(xs))
    return f'<block type="math_multiply"><mutation items="{len(xs)}"></mutation>{vals}</block>'


def ADD(*xs):
    vals = ''.join(f'<value name="NUM{i}">{x}</value>' for i, x in enumerate(xs))
    return f'<block type="math_add"><mutation items="{len(xs)}"></mutation>{vals}</block>'


def SQRT(x):
    return f'<block type="math_single"><field name="OP">ROOT</field><value name="NUM">{x}</value></block>'


def ABS(x):
    return f'<block type="math_abs"><field name="OP">ABS</field><value name="NUM">{x}</value></block>'


def CMP(op, a, b):
    return f'<block type="math_compare"><field name="OP">{op}</field><value name="A">{a}</value><value name="B">{b}</value></block>'


def CHOOSE(test, a, b):
    return (f'<block type="controls_choose"><value name="TEST">{test}</value><value name="THENRETURN">{a}</value>'
            f'<value name="ELSERETURN">{b}</value></block>')


def CALLR(name, args):
    argdecl = ''.join(f'<arg name="{escape(a)}"></arg>' for a, _ in args)
    vals = ''.join(f'<value name="ARG{i}">{v}</value>' for i, (_, v) in enumerate(args))
    return (f'<block type="procedures_callreturn"><mutation name="{name}">{argdecl}</mutation>'
            f'<field name="PROCNAME">{name}</field>{vals}</block>')


def DEFPROC(name, params, body, x, y):
    m = ''.join(f'<arg name="{p}"></arg>' for p in params)
    f = ''.join(f'<field name="VAR{i}">{p}</field>' for i, p in enumerate(params))
    return (f'<block type="procedures_defnoreturn" x="{x}" y="{y}"><mutation>{m}</mutation><field name="NAME">{name}</field>{f}'
            f'<statement name="STACK">{R(body)}</statement></block>')


def DEFFUNC(name, params, expr, x, y):
    m = ''.join(f'<arg name="{p}"></arg>' for p in params)
    f = ''.join(f'<field name="VAR{i}">{p}</field>' for i, p in enumerate(params))
    return (f'<block type="procedures_defreturn" x="{x}" y="{y}"><mutation>{m}</mutation><field name="NAME">{name}</field>{f}'
            f'<value name="RETURN">{expr}</value></block>')


def build_bky(car_name):
    ble = 'BluetoothLE'
    B = 'BluetoothLE1'
    top = []
    y = [0]

    def place(xml_fn, h=140, x=0):
        top.append(xml_fn(x, y[0]))
        y[0] += h

    for name, val in (('DICH_VU', T(NUS)), ('DAC_TINH_RX', T(RX)), ('DAC_TINH_TX', T(TX)), ('TEN_XE', T(car_name)),
                      ('daKetNoi', BOOL(False)), ('jx', NUM(0)), ('jy', NUM(0)), ('jw', NUM(0)),
                      ('dx', NUM(0)), ('dy', NUM(0)), ('dd', NUM(0)), ('RMAX', NUM(CANVAS // 2 - KNOB - 6)), ('NUM_KNOB', NUM(KNOB)), ('daGuiDung', BOOL(True)), ('daVe', BOOL(False))):
        place(lambda x, yy, name=name, val=val: f'<block type="global_declaration" x="{x}" y="{yy}"><field name="NAME">{name}</field>'
              f'<value name="VALUE">{val}</value></block>', 50)

    # gui(lenhGui): gửi chuỗi lệnh sang xe nếu đang kết nối
    place(lambda x, yy: DEFPROC('gui', ['lenhGui'], IF(G('global daKetNoi'), CALLM(ble, B, 'WriteStrings', [
        G('global DICH_VU'), G('global DAC_TINH_RX'), BOOL(False), G('lenhGui')])), x, yy), 160)
    # guiJoy: J<tiến>,<sang trái>,<xoay trái>
    place(lambda x, yy: DEFPROC('guiJoy', [], GUI(JOIN(T('J'), G('global jx'), T(','), G('global jy'), T(','), G('global jw'))), x, yy), 120)
    # tinhCan(x, y, w, h): độ lệch của ngón tay so với tâm, giới hạn trong vòng tròn bán kính RMAX -> global dx, dy
    place(lambda x, yy: DEFPROC('tinhCan', ['x', 'y', 'w', 'h'], seq(
        SETG('global RMAX', SUB(DIV(G('w'), NUM(2)), ADD(G('global NUM_KNOB'), NUM(6)))),
        SETG('global dx', SUB(G('x'), DIV(G('w'), NUM(2)))),
        SETG('global dy', SUB(G('y'), DIV(G('h'), NUM(2)))),
        SETG('global dd', SQRT(ADD(MUL(G('global dx'), G('global dx')), MUL(G('global dy'), G('global dy'))))),
        IF(CMP('GT', G('global dd'), G('global RMAX')), seq(
            SETG('global dx', DIV(MUL(G('global dx'), G('global RMAX')), G('global dd'))),
            SETG('global dy', DIV(MUL(G('global dy'), G('global RMAX')), G('global dd')))))), x, yy), 300)
    # phanTram(v): độ lệch (px) -> -100..100 %, vùng chết 10 % ở giữa
    pct = ROUND(MUL(DIV(G('v'), G('global RMAX')), NUM(100)))
    place(lambda x, yy: DEFFUNC('phanTram', ['v'], CHOOSE(CMP('LT', ABS(pct), NUM(10)), NUM(0), pct), x, yy), 160)

    def draw_proc(canvas, ring_color, knob_color):
        # ảnh nền (vòng tròn, mũi tên) là BackgroundImage nên Clear() không xoá; chỉ vẽ núm + viền núm
        return lambda x, yy: DEFPROC('ve' + canvas[6:], ['kx', 'ky'], seq(
            CALLM('Canvas', canvas, 'Clear', []),
            SETP('Canvas', canvas, 'PaintColor', COLOR(knob_color)),
            CALLM('Canvas', canvas, 'DrawCircle', [ROUND(G('kx')), ROUND(G('ky')), G('global NUM_KNOB'), BOOL(True)]),
            SETP('Canvas', canvas, 'PaintColor', COLOR(ring_color)),
            CALLM('Canvas', canvas, 'DrawCircle', [ROUND(G('kx')), ROUND(G('ky')), G('global NUM_KNOB'), BOOL(False)])), x, yy)
    place(draw_proc('CanvasDiChuyen', 'e3f2fd', '1e88e5'), 260)
    place(draw_proc('CanvasXoay', 'fff3e0', 'ff9800'), 260)

    def center(canvas):
        return [DIV(GETP('Canvas', canvas, 'Width'), NUM(2)), DIV(GETP('Canvas', canvas, 'Height'), NUM(2))]

    def plus_center(canvas, dxv, dyv):
        cx, cy = center(canvas)
        return [ADD(cx, dxv), ADD(cy, dyv)]

    C1, C2 = 'CanvasDiChuyen', 'CanvasXoay'
    # diChuyen(x, y): cần trái -> tiến/lùi (lên = tiến) + trượt ngang (trái = sang trái)
    place(lambda x, yy: DEFPROC('diChuyen', ['x', 'y'], seq(
        CALLP('tinhCan', [('x', G('x')), ('y', G('y')), ('w', GETP('Canvas', C1, 'Width')), ('h', GETP('Canvas', C1, 'Height'))]),
        SETG('global jx', CALLR('phanTram', [('v', MUL(NUM(-1), G('global dy')))])),
        SETG('global jy', CALLR('phanTram', [('v', MUL(NUM(-1), G('global dx')))])),
        CALLP('veDiChuyen', list(zip(['kx', 'ky'], plus_center(C1, G('global dx'), G('global dy')))))), x, yy), 260)
    # xoay(x): cần phải -> chỉ trục ngang (trái = xoay trái / ngược chiều kim đồng hồ)
    place(lambda x, yy: DEFPROC('xoay', ['x'], seq(
        CALLP('tinhCan', [('x', G('x')), ('y', DIV(GETP('Canvas', C2, 'Height'), NUM(2))), ('w', GETP('Canvas', C2, 'Width')),
                          ('h', GETP('Canvas', C2, 'Height'))]),
        SETG('global jw', CALLR('phanTram', [('v', MUL(NUM(-1), G('global dx')))])),
        CALLP('veXoay', list(zip(['kx', 'ky'], plus_center(C2, G('global dx'), NUM(0)))))), x, yy), 220)

    def reset_joys():
        return seq(SETG('global jx', NUM(0)), SETG('global jy', NUM(0)), SETG('global jw', NUM(0)),
                   CALLP('veDiChuyen', list(zip(['kx', 'ky'], center(C1)))), CALLP('veXoay', list(zip(['kx', 'ky'], center(C2)))))

    place(lambda x, yy: EVENT('Form', 'Screen1', 'Initialize', reset_joys(), x, yy), 160)

    # joystick trái
    top.append(EVENT('Canvas', C1, 'TouchDown', seq(CALLP('diChuyen', [('x', G('x')), ('y', G('y'))]), CALLP('guiJoy', [])), 900, 0))
    top.append(EVENT('Canvas', C1, 'Dragged', CALLP('diChuyen', [('x', G('currentX')), ('y', G('currentY'))]), 900, 140))
    top.append(EVENT('Canvas', C1, 'TouchUp', seq(SETG('global jx', NUM(0)), SETG('global jy', NUM(0)),
                                                  CALLP('veDiChuyen', list(zip(['kx', 'ky'], center(C1)))), CALLP('guiJoy', [])), 900, 260))
    # joystick phải
    top.append(EVENT('Canvas', C2, 'TouchDown', seq(CALLP('xoay', [('x', G('x'))]), CALLP('guiJoy', [])), 900, 420))
    top.append(EVENT('Canvas', C2, 'Dragged', CALLP('xoay', [('x', G('currentX'))]), 900, 560))
    top.append(EVENT('Canvas', C2, 'TouchUp', seq(SETG('global jw', NUM(0)),
                                                  CALLP('veXoay', list(zip(['kx', 'ky'], center(C2)))), CALLP('guiJoy', [])), 900, 680))
    # gửi lại 10 lần/giây khi đang gạt (xe tự dừng nếu 0.6 s không nhận lệnh)
    # (cần vừa về vùng chết giữa -> gửi đúng 1 lệnh J0,0,0 để xe dừng ngay, không chờ hết 0.6 s)
    top.append(EVENT('Clock', 'Clock1', 'Timer', seq(IF(NOT(G('global daVe')), seq(CALLP('veDiChuyen', list(zip(['kx', 'ky'], center(C1)))),
                                                                       CALLP('veXoay', list(zip(['kx', 'ky'], center(C2)))),
                                                                       SETG('global daVe', BOOL(True)))), IF(CMP('GT', ADD(ABS(G('global jx')), ABS(G('global jy')), ABS(G('global jw'))), NUM(0)),
                                                    seq(CALLP('guiJoy', []), SETG('global daGuiDung', BOOL(False))),
                                                    IF(NOT(G('global daGuiDung')),
                                                       seq(CALLP('guiJoy', []), SETG('global daGuiDung', BOOL(True)))))), 900, 840))

    def mode_unknown():
        return seq(SETP('Button', 'BtnCheDo', 'Text', T('CHẾ ĐỘ: --')), SETP('Button', 'BtnCheDo', 'BackgroundColor', COLOR('9e9e9e')))

    place(lambda x, yy: EVENT('Button', 'BtnKetNoi', 'Click', seq(
        SETP('Label', 'LblTrangThai', 'Text', JOIN(T('  Đang tìm xe '), G('global TEN_XE'), T(' ... (bật Bluetooth + Vị trí)'))),
        CALLM(ble, B, 'ConnectMatchingName', [G('global TEN_XE')])), x, yy), 160)
    place(lambda x, yy: EVENT('Button', 'BtnNgat', 'Click', IF(G('global daKetNoi'), seq(
        GUI(T('X')), CALLM(ble, B, 'Disconnect', []))), x, yy), 140)
    place(lambda x, yy: EVENT(ble, B, 'Connected', seq(
        SETG('global daKetNoi', BOOL(True)),
        SETP('Label', 'LblTrangThai', 'Text', JOIN(T('  Đã kết nối '), G('global TEN_XE'))),
        CALLM(ble, B, 'RegisterForStrings', [G('global DICH_VU'), G('global DAC_TINH_TX'), BOOL(False)]),
        GUI(JOIN(T('V'), ROUND(GETP('Slider', 'SliderTocDo', 'ThumbPosition')))),
        GUI(T('?'))), x, yy), 220)
    place(lambda x, yy: EVENT(ble, B, 'Disconnected', seq(
        SETG('global daKetNoi', BOOL(False)), reset_joys(),
        SETP('Label', 'LblTrangThai', 'Text', T('  Mất kết nối – bấm KẾT NỐI XE')), mode_unknown()), x, yy), 220)
    place(lambda x, yy: EVENT(ble, B, 'ConnectionFailed', seq(
        SETG('global daKetNoi', BOOL(False)),
        SETP('Label', 'LblTrangThai', 'Text', JOIN(T('  Kết nối lỗi: '), G('reason'), T(' – bấm KẾT NỐI XE lần nữa')))), x, yy), 160)
    place(lambda x, yy: EVENT(ble, B, 'StringsReceived', IF(NOT(ISEMPTY_LIST(G('stringValues'))), seq(
        SETP('Label', 'LblTrangThai', 'Text', JOIN(T('  Xe: '), ITEM1(G('stringValues')))),
        IF(CONTAINS(ITEM1(G('stringValues')), T('TU CHAY')),
           seq(SETP('Button', 'BtnCheDo', 'Text', T('CHẾ ĐỘ: TỰ CHẠY (bấm để lái tay)')),
               SETP('Button', 'BtnCheDo', 'BackgroundColor', COLOR('4caf50'))),
           seq(SETP('Button', 'BtnCheDo', 'Text', T('CHẾ ĐỘ: LÁI TAY (bấm để tự chạy)')),
               SETP('Button', 'BtnCheDo', 'BackgroundColor', COLOR('ff9800')))))), x, yy), 260)
    place(lambda x, yy: EVENT('Button', 'BtnCheDo', 'Click', GUI(T('T')), x, yy), 100)
    place(lambda x, yy: EVENT('Button', 'BtnDung', 'Click', seq(reset_joys(), GUI(T('X'))), x, yy), 160)
    place(lambda x, yy: EVENT('Slider', 'SliderTocDo', 'PositionChanged', seq(
        SETP('Label', 'LblTocDo', 'Text', JOIN(T('Tốc độ: '), ROUND(G('thumbPosition')), T('%'))),
        GUI(JOIN(T('V'), ROUND(G('thumbPosition'))))), x, yy), 160)

    return ('<xml xmlns="http://www.w3.org/1999/xhtml">\n' + '\n'.join('  ' + b for b in top) +
            f'\n  <yacodeblocks ya-version="{YA_VERSION}" language-version="{LANG_VERSION}"></yacodeblocks>\n</xml>\n')


PROPS = f"""main=appinventor.{USER}.{PROJECT}.Screen1
name={PROJECT}
assets=../assets
source=../src
build=../build
versioncode=1
versionname=1.0
useslocation=False
aname=OOMWOO
sizing=Responsive
showlistsasjson=True
actionbar=True
theme=AppTheme.Light.DarkActionBar
color.primary=&HFF1E88E5
color.primary.dark=&HFF1565C0
color.accent=&HFFFF9800
"""


def read_aix(path):
    """Trả (thư mục gốc trong aix, các file {tên: bytes}, version, type đầy đủ).
    Nhận cả file .aia đã có extension (lấy lại extension từ assets/external_comps/ của nó)."""
    z = zipfile.ZipFile(path)
    files = {n: z.read(n) for n in z.namelist() if not n.endswith('/')}
    pre = 'assets/external_comps/'
    if any(n.startswith(pre) for n in files):
        files = {n[len(pre):]: b for n, b in files.items() if n.startswith(pre)}
    roots = sorted({n.split('/')[0] for n in files})
    found = None
    for r in roots:
        for desc in ('components.json', 'component.json'):
            key = f'{r}/{desc}'
            if key in files:
                d = json.loads(files[key].decode('utf-8'))
                for c in (d if isinstance(d, list) else [d]):
                    if str(c.get('type', '')).endswith('.BluetoothLE') or c.get('name') == 'BluetoothLE':
                        found = (r, c)
    if found is None:
        raise SystemExit(f'{path}: không phải extension BluetoothLE của MIT (không thấy thành phần BluetoothLE)')
    r, c = found
    ver = c.get('version') or c.get('versionName') or '1'
    return r, {n: b for n, b in files.items() if n.split('/')[0] == r}, str(ver), c.get('type')


AIX_URL = 'https://mit-cml.github.io/extensions/data/extensions/edu.mit.appinventor.ble-20240822.aix'


def download_aix():
    """Tự tải extension BluetoothLE chính thức của MIT về cạnh script (cần Internet)."""
    import urllib.request
    dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.path.basename(AIX_URL))
    try:
        print('Đang tải extension BluetoothLE của MIT:', AIX_URL)
        with urllib.request.urlopen(AIX_URL, timeout=30) as r, open(dst + '.part', 'wb') as f:
            f.write(r.read())
        os.replace(dst + '.part', dst)
        zipfile.ZipFile(dst).namelist()
        return dst
    except Exception as e:
        print('  -> không tải được (%s)' % e)
        return None


def find_aix():
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), PROJECT + '.aia')
    if os.path.isfile(here):                     # .aia có sẵn đã chứa extension -> dùng lại, không cần Internet
        try:
            read_aix(here)
            return here
        except SystemExit:
            pass
    pats = []
    for d in ('~/Downloads', '~/Tải xuống', '~/Desktop', '~/Màn hình nền', '.', os.path.dirname(os.path.abspath(__file__))):
        d = os.path.expanduser(d)
        pats += glob.glob(os.path.join(d, '*.aix'))
    pats = [p for p in pats if 'ble' in os.path.basename(p).lower() or 'bluetooth' in os.path.basename(p).lower()]
    pats.sort(key=os.path.getmtime, reverse=True)
    return pats[0] if pats else None


def load_assets():
    """Ảnh nền joystick: lấy file cạnh script, không có thì lấy lại từ OomwooBLE.aia có sẵn, không có nữa thì tự vẽ (cần Pillow)."""
    here = os.path.dirname(os.path.abspath(__file__))
    out = {}
    old = os.path.join(here, PROJECT + '.aia')
    for n in ASSETS:
        p = os.path.join(here, n)
        if os.path.isfile(p):
            out[n] = open(p, 'rb').read()
        elif os.path.isfile(old):
            try:
                out[n] = zipfile.ZipFile(old).read('assets/' + n)
            except KeyError:
                pass
    if len(out) < len(ASSETS):
        try:
            sys.path.insert(0, here)
            import ve_joystick
            ve_joystick.base('move').save(os.path.join(here, 'joy_move.png'))
            ve_joystick.base('turn').save(os.path.join(here, 'joy_turn.png'))
            return load_assets()
        except Exception as e:
            print('[!] Thiếu ảnh nền joystick (%s): app vẫn chạy, chỉ không có hình vòng tròn' % e)
    return out


def build_aia(out_path, aix_path=None, car_name='OOMWOO'):
    if aix_path:
        root, aix_files, ver, ctype = read_aix(aix_path)
    else:
        root, aix_files, ver, ctype = None, {}, '20240822', None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('youngandroidproject/project.properties', PROPS)
        z.writestr(f'src/appinventor/{USER}/{PROJECT}/Screen1.scm', build_scm(ver))
        z.writestr(f'src/appinventor/{USER}/{PROJECT}/Screen1.bky', build_bky(car_name))
        for n, b in sorted(aix_files.items()):
            z.writestr('assets/external_comps/' + n, b)
        for n, b in load_assets().items():
            z.writestr('assets/' + n, b)
    with open(out_path, 'wb') as f:
        f.write(buf.getvalue())
    return root, ver, ctype


def main():
    ap = argparse.ArgumentParser(description='Tạo OomwooBLE.aia (App Inventor) cho xe OOMWOO')
    ap.add_argument('aix', nargs='?', help='file extension BluetoothLE (.aix) đã tải từ MIT')
    ap.add_argument('--ten-xe', default='OOMWOO', help="tên Bluetooth của xe (BLE_NAME trong esp32_giuaky/giuaky_config.py)")
    ap.add_argument('-o', '--out', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), PROJECT + '.aia'))
    ap.add_argument('--khong-extension', action='store_true', help=argparse.SUPPRESS)
    a = ap.parse_args()
    aix = None if a.khong_extension else (os.path.expanduser(a.aix) if a.aix else (find_aix() or download_aix()))
    if aix is None and not a.khong_extension:
        print('CHƯA CÓ extension BluetoothLE (.aix).')
        print('  1) Mở trình duyệt:  https://mit-cml.github.io/extensions/   -> mục BluetoothLE -> tải file .aix')
        print('     (tên dạng edu.mit.appinventor.ble-20240822.aix, lưu vào thư mục Downloads / Tải xuống)')
        print('  2) Chạy lại:  python3 ' + os.path.basename(__file__))
        sys.exit(1)
    if aix and not os.path.isfile(aix):
        sys.exit(f'Không thấy file {aix}')
    root, ver, ctype = build_aia(a.out, aix, a.ten_xe)
    print(f'Đã gắn extension: {os.path.basename(aix) if aix else "(không)"}  ({ctype}, phiên bản {ver})')
    print(f'XONG: {a.out}')
    print('Tiếp theo: https://ai2.appinventor.mit.edu -> Projects -> Import project (.aia) from my computer -> chọn file trên')
    print('           -> Build -> Android App (.apk) -> quét mã QR bằng điện thoại để tải + cài app.')


if __name__ == '__main__':
    main()
