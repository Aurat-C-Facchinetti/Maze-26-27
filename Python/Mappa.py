import numpy as np
from Settings import *

class Mappa:
    def __init__(self, rows=INIT_ROWS, cols=INIT_COLS):
        # Array colori (piastrelle) e array muri
        self.visited = np.zeros((rows, cols), dtype=np.uint8)
        self.walls = np.zeros((rows, cols), dtype=np.uint8)
        self.h, self.w = self.visited.shape
        self.home = (self.w // 2, self.h // 2)
        self.target = None
        self.last_checkpoint = self.home

    def expand_double(self, x, y):
        oh, ow = self.visited.shape
        nh, nw = oh * 2, ow * 2
        MAX_SIDE = 32768
        if nh > MAX_SIDE or nw > MAX_SIDE:
            return 0, 0, x, y

        new_v = np.zeros((nh, nw), dtype=np.uint8)
        new_w = np.zeros((nh, nw), dtype=np.uint8)
        off_y = (nh - oh) // 2
        off_x = (nw - ow) // 2
        new_v[off_y:off_y + oh, off_x:off_x + ow] = self.visited
        new_w[off_y:off_y + oh, off_x:off_x + ow] = self.walls
        self.visited, self.walls = new_v, new_w
        self.h, self.w = nh, nw
        x += off_x
        y += off_y
        if self.home is not None:
            self.home = (self.home[0] + off_x, self.home[1] + off_y)
        if getattr(self, 'target', None) is not None:
            tx, ty = self.target
            self.target = (tx + off_x, ty + off_y)
        if self.last_checkpoint is not None:
            cx, cy = self.last_checkpoint
            self.last_checkpoint = (cx + off_x, cy + off_y)
        return off_x, off_y, x, y

    def ensure_inside(self, gx, gy, x, y):
        safety = 0
        while gx < 0 or gx >= self.w or gy < 0 or gy >= self.h:
            off_x, off_y, x, y = self.expand_double(x, y)
            safety += 1
            if off_x == 0 and off_y == 0:
                gx = max(0, min(self.w - 1, gx))
                gy = max(0, min(self.h - 1, gy))
                break
            gx += off_x
            gy += off_y
            if safety > 8:
                gx = max(0, min(self.w - 1, gx))
                gy = max(0, min(self.h - 1, gy))
                break
        return gx, gy, x, y

    def set_wall_absolute(self, gx, gy, dir_idx, value=1):
        bit = self.bit_for_dir(dir_idx)
        if value:
            self.walls[gy, gx] |= bit
        else:
            self.walls[gy, gx] &= (~bit) & 0xF

    def toggle_wall_absolute(self, gx, gy, dir_idx):
        bit = self.bit_for_dir(dir_idx)
        self.walls[gy, gx] ^= bit

    @staticmethod
    def bit_for_dir(idx):
        return [1, 2, 4, 8][idx]

    @staticmethod
    def opposite_dir(idx):
        return (idx + 2) % 4

    @staticmethod
    def dir_index_from_deg(deg):
        return ((deg // 90) % 4)

    def visit_current(self, y, x):
        if self.visited[y, x] == 0:
            self.visited[y, x] = 1
        if self.visited[y, x] == 5:
            self.last_checkpoint = (x, y)
            print(f"::::::::: Checkpoint salvato: ({x},{y}) ::::::::::")

    def cell_cost(self, val):
        if val == 0:
            return 1
        elif val == 1:
            return 2
        elif val == 2:
            return np.inf
        elif val == 3:
            return 3
        elif val == 4:
            return 3
        return 2

    def neighbors(self, gx, gy):
        res = []
        for idx, (dx, dy) in enumerate([(0, -1), (1, 0), (0, 1), (-1, 0)]):
            nx, ny = gx + dx, gy + dy
            if not (0 <= nx < self.w and 0 <= ny < self.h):
                continue
            if (self.walls[gy, gx] & self.bit_for_dir(idx)) != 0:
                continue
            if (self.walls[ny, nx] & self.bit_for_dir(self.opposite_dir(idx))) != 0:
                continue
            if self.visited[ny, nx] == 2:
                continue
            res.append((nx, ny))
        return res

    def can_step_to(self, x, y, nx, ny):
        dx, dy = nx - x, ny - y
        if (abs(dx) + abs(dy)) != 1:
            return False
        if not (0 <= nx < self.w and 0 <= ny < self.h):
            return False
        if dy == -1:
            dir_idx = 0
        elif dx == 1:
            dir_idx = 1
        elif dy == 1:
            dir_idx = 2
        else:
            dir_idx = 3
        if (self.walls[y, x] & self.bit_for_dir(dir_idx)) != 0:
            return False
        if (self.walls[ny, nx] & self.bit_for_dir(self.opposite_dir(dir_idx))) != 0:
            return False
        if self.visited[ny, nx] == 2:
            return False
        return True

    def dijkstra(self, start, goal):
        import heapq
        sx, sy = start
        gx, gy = goal
        if not (0 <= gx < self.w and 0 <= gy < self.h):
            return None
        if self.cell_cost(self.visited[gy, gx]) == np.inf:
            return None
        dist = np.full((self.h, self.w), np.inf, dtype=float)
        prev = np.full((self.h, self.w, 2), -1, dtype=int)
        pq = []
        dist[sy, sx] = 0.0
        heapq.heappush(pq, (0.0, (sx, sy)))
        while pq:
            d, (cx, cy) = heapq.heappop(pq)
            if d != dist[cy, cx]:
                continue
            if (cx, cy) == (gx, gy):
                break
            for nx, ny in self.neighbors(cx, cy):
                w = self.cell_cost(self.visited[ny, nx])
                nd = d + w
                if nd < dist[ny, nx]:
                    dist[ny, nx] = nd
                    prev[ny, nx] = [cx, cy]
                    heapq.heappush(pq, (nd, (nx, ny)))
        if not np.isfinite(dist[gy, gx]):
            return None
        path = []
        cx, cy = gx, gy
        while not (cx == sx and cy == sy):
            path.append((cx, cy))
            pcx, pcy = prev[cy, cx]
            if pcx < 0:
                return None
            cx, cy = int(pcx), int(pcy)
        path.reverse()
        return path
