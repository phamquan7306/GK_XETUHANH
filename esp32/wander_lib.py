import math

import config
try:
    import giuaky_config as gk
except ImportError:
    gk = config


def _c(name, default):
    return getattr(gk, name, getattr(config, name, default))


HALF_W = _c('WANDER_HALF_WIDTH', 0.21)     # m: nửa bề ngang xe (tính cả bánh) + khoảng hở mỗi bên
FRONT_X = 0.16                             # m: điểm có toạ độ dọc nhỏ hơn này là đang ở BÊN CẠNH thân xe, không chắn phía trước
SIDE_X = 0.26                              # m: vùng hai bên hông xe (dọc -SIDE_X..SIDE_X) dùng để giữ cách tường
STOP_D = _c('WANDER_STOP_DIST', 0.36)      # m (tính từ tâm LiDAR): phía trước gần hơn -> dừng tiến, xoay
CLEAR_D = _c('WANDER_CLEAR_DIST', 0.75)    # m: xoay tới khi phía trước trống ít nhất bấy nhiêu
SLOW_D = 1.0                               # m: phía trước gần hơn -> giảm tốc dần
SIDE_MIN = _c('WANDER_SIDE_MIN', 0.26)     # m: tường bên hông gần hơn (tính từ tâm) -> trượt ngang ra
NEAR_R = _c('WANDER_NEAR_R', 0.22)         # m: vật gần tâm hơn -> THOAT trước (xoay có thể quẹt góc xe)
LOOK = 2.5                                 # m: không cần nhìn xa hơn
V_CRUISE = _c('WANDER_SPEED', 0.20)        # m/s
W_TURN = _c('WANDER_TURN_SPEED', 1.3)      # rad/s khi xoay tại chỗ
W_MAX = 1.6                                # rad/s khi vừa đi vừa bẻ lái
V_ESCAPE = 0.12                            # m/s khi trượt ra khỏi chỗ sát
K_STEER = 2.2                              # rad/s cho mỗi rad lệch hướng
STRAIGHT_D = 0.9                           # m: phía trước thoáng hơn chừng này thì ưu tiên đi thẳng
STRAIGHT_BONUS = _c('WANDER_STRAIGHT', 0.5)   # càng lớn càng ít lượn (sân nhỏ đỡ chạy vòng tròn)

_SIN = [math.sin(math.radians(i)) for i in range(360)]
_COS = [math.cos(math.radians(i)) for i in range(360)]
DIRS = tuple(range(-90, 91, 15))


class Wander:
    def __init__(self, rand01):
        self.rand = rand01                   # hàm trả số ngẫu nhiên 0..1
        self.state = 'CHAY'
        self.t_state = 0.0
        self.free = {d: 0.0 for d in DIRS}
        self.front = 0.0
        self.nearest = 9.9
        self.near_a = 0
        self.left = 9.9
        self.right = 9.9
        self.open_l = 0.0
        self.open_r = 0.0
        self.have = False
        self.turn_dir = 1.0
        self.turn_min = 0.5
        self.turn_best = 0.0
        self.pref = 0
        self.t_pref = 0.0
        self.best = 0
        self.turns = 0
        self.escapes = 0
        self.cpu_ms = 0.0
        self.pts = []
        self.turn_goal = CLEAR_D

    # ---------- phân tích 1 vòng quét ----------
    def scan(self, ranges_mm):
        """ranges_mm: 360 ô (mm, 0 = không có tia), ô i = góc i độ, 0° = mũi xe, tăng ngược chiều kim đồng hồ."""
        pts = []
        nearest = 9.9
        na = 0
        left = 9.9
        right = 9.9
        ol = 0.0
        orr = 0.0
        S = _SIN
        C = _COS
        for a in range(360):
            d = ranges_mm[a]
            if d == 0:
                r = LOOK                     # không có tia (quá xa / mặt đen) -> coi như trống
                if 20 <= a <= 160:
                    ol += r
                elif 200 <= a <= 340:
                    orr += r
                continue
            r = d * 0.001
            if r < nearest:                  # vật sát xe: cần 2 tia liền nhau (bỏ qua 1 tia nhiễu lẻ)
                dn = ranges_mm[(a + 1) % 360]
                dp = ranges_mm[a - 1]
                if (dn and dn * 0.001 < r + 0.05) or (dp and dp * 0.001 < r + 0.05):
                    nearest = r
                    na = a
            rr = r if r < LOOK else LOOK
            if 20 <= a <= 160:
                ol += rr
            elif 200 <= a <= 340:
                orr += rr
            if r < LOOK + HALF_W:
                x = r * C[a]
                if -SIDE_X < x < SIDE_X:
                    y = r * S[a]
                    if y > 0.0:
                        if y < left:
                            left = y
                    elif -y < right:
                        right = -y
                pts.append((r, a))
        free = self.free
        hw = HALF_W
        fx = FRONT_X
        for th in DIRS:
            f = LOOK
            for r, a in pts:
                k = (a - th) % 360
                c = C[k]
                if c <= 0.0:
                    continue
                al = r * c
                if al < fx or al >= f:
                    continue
                lat = r * S[k]
                if -hw < lat < hw:
                    f = al
            free[th] = f
        self.pts = pts
        self.front = free[0]
        self.nearest = nearest
        self.near_a = na
        self.left = left
        self.right = right
        self.open_l = ol
        self.open_r = orr
        self.have = True

    # ---------- chọn lệnh mỗi chu kỳ điều khiển ----------
    def _set(self, st):
        if st != self.state:
            self.state = st
            self.t_state = 0.0
            if st == 'QUAY':
                self.turns += 1
            elif st == 'THOAT':
                self.escapes += 1

    def free_dir(self, th):
        """Hành lang trống (m) theo hướng th độ (bất kỳ, kể cả phía sau), tính từ vòng quét gần nhất."""
        f = LOOK
        C = _COS
        S = _SIN
        hw = HALF_W
        for r, a in self.pts:
            k = (a - th) % 360
            c = C[k]
            if c <= 0.0:
                continue
            al = r * c
            if al < FRONT_X or al >= f:
                continue
            lat = r * S[k]
            if -hw < lat < hw:
                f = al
        return f

    def _start_turn(self):
        # nhìn quanh 360° tìm hướng thoáng nhất -> xoay về phía đó (đường ngắn nhất), dừng xoay khi phía trước
        # đã thoáng gần bằng hướng đó: chỗ chật không phải xoay đủ vòng tìm khoảng trống CLEAR_D.
        cand = [(th, self.free_dir(th)) for th in range(-165, 181, 15)]
        fmax = max(f for _, f in cand)
        lim = max(STOP_D + 0.3, 0.7 * fmax)
        good = [c for c in cand if c[1] >= lim] or [max(cand, key=lambda c: c[1])]
        th, f = good[int(self.rand() * len(good)) % len(good)]       # chọn NGẪU NHIÊN trong các hướng đủ thoáng: không lặp mãi 1 vòng
        if th == 180 or abs(th) < 1:
            dl, dr = self.open_l, self.open_r
            if abs(dl - dr) < 0.08 * (dl + dr + 1e-6):
                self.turn_dir = 1.0 if self.rand() < 0.5 else -1.0  # hai bên như nhau -> chọn ngẫu nhiên
            else:
                self.turn_dir = 1.0 if dl > dr else -1.0
        else:
            self.turn_dir = 1.0 if th > 0 else -1.0
        g = 0.8 * f
        lo = STOP_D + 0.15
        self.turn_goal = CLEAR_D if g > CLEAR_D else (lo if g < lo else g)
        self.turn_min = 0.2 + 0.4 * self.rand()                     # xoay thêm một chút ngẫu nhiên -> đi "lung tung"
        self._set('QUAY')

    def control(self, dt, speed_scale=1.0):
        """Trả (vx, vy, w): m/s tiến, m/s sang trái, rad/s ngược chiều kim đồng hồ."""
        self.t_state += dt
        self.t_pref -= dt
        if self.t_pref <= 0.0:
            self.t_pref = 3.0 + 5.0 * self.rand()
            self.pref = int((self.rand() * 2.0 - 1.0) * 60.0)
        if not self.have:
            return 0.0, 0.0, 0.0

        st = self.state
        if self.nearest < NEAR_R and st != 'THOAT':
            self._set('THOAT')
            st = 'THOAT'

        if st == 'THOAT':
            if self.nearest > NEAR_R + 0.05 or self.t_state > 1.5:
                self._start_turn()
                st = 'QUAY'
            else:
                a = self.near_a
                return -V_ESCAPE * _COS[a], -V_ESCAPE * _SIN[a], 0.0

        if st == 'QUAY':
            if self.t_state < dt * 1.5:
                self.turn_best = 0.0
            if self.front > self.turn_best:
                self.turn_best = self.front
            full = 6.3 / W_TURN                                      # thời gian xoay đủ 1 vòng
            ok = self.front >= self.turn_goal
            if not ok and self.t_state > full:                      # chỗ chật, không đâu trống tới CLEAR_D: lấy hướng tốt nhất đã thấy
                ok = self.front >= STOP_D + 0.15 and self.front >= 0.85 * self.turn_best
            if ok and self.t_state >= self.turn_min:
                self._set('CHAY')
                st = 'CHAY'
            elif self.t_state > 3.0 * full:                          # xoay mãi không thấy lối -> đổi chiều, thử lại
                self.turn_dir = -self.turn_dir
                self.t_state = 0.0
                return 0.0, 0.0, self.turn_dir * W_TURN
            else:
                return 0.0, 0.0, self.turn_dir * W_TURN

        # --- CHAY ---
        if self.front < STOP_D:
            self._start_turn()
            return 0.0, 0.0, self.turn_dir * W_TURN
        best = 0
        bs = -1e9
        for th in DIRS:
            f = self.free[th]
            s = (f if f < LOOK else LOOK) - 0.5 * abs(th) / 90.0
            dp = abs(th - self.pref)
            if dp < 45:
                s += 0.35 * (1.0 - dp / 45.0)
            if th == self.best:
                s += 0.15                                           # giữ hướng đã chọn, đỡ lắc qua lắc lại
            if th == 0 and f >= STRAIGHT_D:
                s += STRAIGHT_BONUS                                 # phía trước còn thoáng: cứ đi thẳng, không lượn vòng
            if s > bs:
                bs = s
                best = th
        self.best = best
        if self.free[best] < STOP_D + 0.15:                         # không hướng nào đi được xa -> xoay
            self._start_turn()
            return 0.0, 0.0, self.turn_dir * W_TURN
        k = (self.front - STOP_D) / (SLOW_D - STOP_D)
        k = 0.35 if k < 0.35 else (1.0 if k > 1.0 else k)
        ang = math.radians(best)
        ca = math.cos(ang)
        v = V_CRUISE * speed_scale * k * (ca if ca > 0.3 else 0.3)
        w = K_STEER * ang
        w = W_MAX if w > W_MAX else (-W_MAX if w < -W_MAX else w)
        vy = 0.0
        if self.left < SIDE_MIN:
            vy -= 1.6 * (SIDE_MIN - self.left)
        if self.right < SIDE_MIN:
            vy += 1.6 * (SIDE_MIN - self.right)
        vy = 0.12 if vy > 0.12 else (-0.12 if vy < -0.12 else vy)
        return v, vy, w
