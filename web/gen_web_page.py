#!/usr/bin/env python3
"""web_page.html -> web_page.py (chuỗi HTML để MicroPython phục vụ, nạp cùng các *.py khác)."""
import os
import sys
src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web_page.html')
dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'esp32', 'web_page.py')
h = open(src, encoding='utf-8').read()
assert "'''" not in h and '\\' not in h, 'HTML không được chứa \'\'\' hoặc dấu \\'
open(dst, 'w', encoding='utf-8').write('# Trang điều khiển (tự sinh từ web_page.html - sửa file .html rồi chạy gen_web_page.py)\nHTML = r\'\'\'' + h + "'''\n")
print(dst, len(h.encode()), 'byte')
