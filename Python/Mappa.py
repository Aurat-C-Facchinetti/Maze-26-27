import numpy as np

from Settings import *
class Mappa:
    def __init__(self, rows=INIT_ROWS, cols=INIT_COLS):
        # matrice logica
        self.visited = np.zeros((rows, cols))
        # walls bitmask per N,E,S,W = 1,2,4,8
        self.walls = np.zeros((rows, cols), dtype=np.int8)
        self.h, self.w = self.visited.shape


    def expand_double(self, y, x):
        # Raddoppia la mappa nel momento in cui il Robot si avvicina al bordo
        oh, ow = self.visited.shape
        nh, nw = oh * 2, ow * 2
        # guardia anti OOM
        MAX_SIDE = 32768
        if nh > MAX_SIDE or nw > MAX_SIDE:
            return 0,0 # non espandere

        new_v = np.zeros((nh, nw), dtype=np.int8)
        new_w = np.zeros((nh, nw), dtype=np.int8)
        off_y = (nh - oh) // 2
        off_x = (nw - ow) // 2
        new_v[off_y:off_x+oh, off_x:off_x+ow] = self.visited
        new_w[off_y:off_y + oh, off_x:off_x + ow] = self.walls
        self.visited, self.walls = new_v, new_w
        self.h, self.w = nh, nw
        x += off_x
        y += off_y
        # Mantieni allineati anche home e target quando la matrice si espande
        if hasattr(self, 'home') and self.home is not None:
            self.home = (self.home[0] + off_x, self.home[1] + off_y)
        if getattr(self, 'target', None) is not None:
            tx, ty = self.target
            self.target = (tx + off_x, ty + off_y)
        return off_x, off_y

    # Prima di espandere controlla che non andiamo oltre il limite massimo
    def ensure_inside(self, gx, gy):
        safety = 0
        while gx < 0 or gx >= self.w or gy < 0 or gy >= self.h:
            off_x, off_y = self.expand_double()
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
        return gx, gy

    # Setta o rimuove un muro da una posizione assoluta nella matrice
    def set_wall_absolute(self, gx, gy, dir_idx, value=1):
        bit = self.bit_for_dir(dir_idx)
        if value:
            self.walls[gy, gx] |= bit
        else:
            self.walls[gy, gx] &= (~bit) & 0xF


    # Fa la stessa cosa di quello sopra (TODO: Capire perchè è così)
    def toggle_wall_absolute(self, gx, gy, dir_idx):
        bit = self.bit_for_dir(dir_idx)
        self.walls[gy, gx] ^= bit

    @staticmethod
    def bit_for_dir(idx):
        return [1, 2, 4, 8][idx]

    def set_wall_relative(self, rel_idx, y, x, deg, toggle=True):
        #rel_idx: 0=fronte,1=destra,2=retro,3=sinistra rispetto all'heading.
        cur_abs = self.dir_index_from_deg(deg)
        abs_idx = (cur_abs + rel_idx) % 4
        dxdy = [(0, -1), (1, 0), (0, 1), (-1, 0)][abs_idx]
        nx, ny = x + dxdy[0], y + dxdy[1]
        nx, ny = self.ensure_inside(nx, ny)
        if toggle:
            self.toggle_wall_absolute(x, y, abs_idx)
            self.toggle_wall_absolute(nx, ny, self.opposite_dir(abs_idx))
        else:
            self.set_wall_absolute(x, y, abs_idx, 1)
            self.set_wall_absolute(nx, ny, self.opposite_dir(abs_idx), 1)
        self.visit_current(y, x)

    # Funzione per segnare la cella dove passiamo
    def visit_current(self, y, x):
        # non sovrascrivere stati speciali (2..5)
        if self.visited[y,x] == 0:
            self.visited[y,x] = 1
        if self.visited[y,x] == 5:
            self.last_checkpoint = (x,y)
            print(f"::::::::: Checkpoint salvato: ({x},{y}) ::::::::::")

    @staticmethod
    def dir_index_from_deg(deg):
        # 0=N,1=E,2=S,3=W
        return ((deg // 90) % 4)

    @staticmethod
    def opposite_dir(idx):
        return (idx + 2) % 4
