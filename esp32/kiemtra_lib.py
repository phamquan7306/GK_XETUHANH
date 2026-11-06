# =====================================================================
#  OOMWOO giữa kỳ - tự kiểm tra bằng LiDAR (không cần encoder / MPU)
#   1) MatNa: lúc mới bật, xe đứng yên vài vòng quét -> ghi lại các tia chạm chính THÂN XE (cột đỡ LiDAR, dây, bánh...)
#      ở gần (< 30 cm) và không đổi -> bỏ qua chúng, nếu không xe tưởng luôn có vật cản sát mình và xoay tròn mãi.
#   2) do_xoay(): so 2 vòng quét trước/sau khi ra lệnh xoay TRÁI -> biết xe thực sự xoay trái hay phải
#      (W_SIGN / LIDAR_CLOCKWISE sai làm xe xoay ngược -> tự chạy sẽ bẻ lái sai và xoay tròn).
# =====================================================================
import math
from array import array

SELF_MAX_MM = 230        # tia chạm thân xe chỉ tính khi gần hơn chừng này (thân xe ~19-22 cm tính từ tâm LiDAR)
SELF_SPREAD_MM = 40      # và gần như không đổi giữa các vòng quét
SELF_MARGIN_MM = 25
WIDEN_DEG = 5            # nới cụm che thêm bấy nhiêu độ mỗi bên
MISS_UNMASK = 10         # cả cụm bị che 10 vòng liền không có tia ngắn mà thấy vật XA hơn -> không phải thân xe -> bỏ che


class MatNa:
    def __init__(self, n_scans=8):
        self.need = n_scans
        self.n = 0
        self.cnt = array('B', bytes(360))
        self.lo = array('H', [65535] * 360)
        self.hi = array('H', bytes(720))
        self.mask = array('H', bytes(720))     # 0 = không che; >0 = bỏ tia ngắn hơn hoặc bằng số mm này
        self.done = False
        self.n_masked = 0
        self.groups = []                        # [[từ ô, tới ô, số vòng liền không thấy]] - mỗi cụm = 1 phần thân xe

    def add(self, scan):
        """Gọi với mỗi vòng quét mới khi xe đứng yên. Trả True khi đã đủ dữ liệu và tạo xong mặt nạ."""
        if self.done:
            return True
        for a in range(360):
            d = scan[a]
            if 0 < d < SELF_MAX_MM:
                self.cnt[a] += 1
                if d < self.lo[a]:
                    self.lo[a] = d
                if d > self.hi[a]:
                    self.hi[a] = d
        self.n += 1
        if self.n < self.need:
            return False
        keep = self.need * 3 // 4
        m = self.mask
        for a in range(360):
            if self.cnt[a] >= keep and self.hi[a] - self.lo[a] <= SELF_SPREAD_MM:
                v = self.hi[a] + SELF_MARGIN_MM
                for k in range(-WIDEN_DEG, WIDEN_DEG + 1):     # nới mỗi bên: góc tia chạm cột/dây nhảy vài độ giữa các vòng
                    j = (a + k) % 360
                    if v > m[j]:
                        m[j] = v
        self.groups = [[a, b, 0] for a, b, _ in self.ranges()]
        self.n_masked = sum(1 for a in range(360) if m[a])
        self.done = True
        return True

    def apply(self, scan, out):
        """out = scan đã bỏ các tia chạm thân xe. Thân xe gắn chặt vào xe nên cụm của nó luôn còn tia ngắn;
        nếu cả một cụm 10 vòng liền không còn tia ngắn mà lại thấy được vật xa hơn -> đó là vật thật lúc khởi động -> bỏ che."""
        m = self.mask
        for a in range(360):
            d = scan[a]
            out[a] = 0 if (d and d <= m[a]) else d
        if not self.groups:
            return
        for g in self.groups:
            hit = far = False
            a = g[0]
            while a <= g[1]:
                d = scan[a]
                if d:
                    if d <= m[a]:
                        hit = True
                        break
                    far = True
                a += 1
            if hit:
                g[2] = 0
            elif far:
                g[2] += 1
                if g[2] >= MISS_UNMASK:
                    for a in range(g[0], g[1] + 1):
                        m[a] = 0
                        out[a] = scan[a]
                    g[1] = -1                                  # đánh dấu đã bỏ
        self.groups = [g for g in self.groups if g[1] >= g[0]]
        self.n_masked = sum(g[1] - g[0] + 1 for g in self.groups)

    def ranges(self):
        """Các cung bị che, dạng [(từ độ, tới độ, mm)], để in ra nhật ký."""
        out = []
        a = 0
        while a < 360:
            if self.mask[a]:
                b = a
                mx = 0
                while b < 360 and self.mask[b]:
                    mx = max(mx, self.mask[b])
                    b += 1
                out.append((a, b - 1, mx))
                a = b
            else:
                a += 1
        return out


def do_xoay(s0, s1, max_deg=90):
    """Góc xe đã xoay (độ, dương = ngược chiều kim đồng hồ = xoay TRÁI) giữa vòng quét s0 và s1, cùng độ tin cậy 0..1.
    Vật đứng yên: sau khi xe xoay trái θ, vật ở góc a trước đó nay ở góc a-θ -> s1[a] ~ s0[a+θ]."""
    scores = {}
    for s in range(-max_deg, max_deg + 1):
        err = 0
        n = 0
        for a in range(0, 360, 2):
            d1 = s1[a]
            d0 = s0[(a + s) % 360]
            if d1 and d0:
                e = d1 - d0
                if e < 0:
                    e = -e
                err += e if e < 500 else 500
                n += 1
        if n >= 40:
            scores[s] = err / n
    if not scores:
        return 0, 0.0
    best_s = min(scores, key=lambda k: scores[k])
    best = scores[best_s]
    others = [v for k, v in scores.items() if abs(k - best_s) > 8]
    second = min(others) if others else best
    return best_s, (second - best) / (second + 1.0)


_COS = [math.cos(math.radians(i)) for i in range(360)]
_SIN = [math.sin(math.radians(i)) for i in range(360)]


def huong_di(s0, s1, max_mm=4000):
    """Xe vừa tịnh tiến một đoạn ngắn (không xoay): ước lượng hướng đi (độ, trong khung LiDAR) và quãng (m).
    Tia ở góc a ngắn đi ~ d*cos(a - hướng): khớp bình phương nhỏ nhất dr(a) = A cos a + B sin a."""
    sxx = sxy = syy = sx = sy = 0.0
    n = 0
    for a in range(360):
        d0 = s0[a]
        d1 = s1[a]
        if not d0 or not d1 or d0 > max_mm or d1 > max_mm:
            continue
        dr = (d1 - d0) * 0.001
        if dr > 0.25 or dr < -0.25:
            continue
        c = _COS[a]
        s = _SIN[a]
        sxx += c * c
        sxy += c * s
        syy += s * s
        sx += c * dr
        sy += s * dr
        n += 1
    det = sxx * syy - sxy * sxy
    if n < 60 or abs(det) < 1e-6:
        return None, 0.0
    A = (syy * sx - sxy * sy) / det
    B = (sxx * sy - sxy * sx) / det
    return math.degrees(math.atan2(-B, -A)), math.sqrt(A * A + B * B)
