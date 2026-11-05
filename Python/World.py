from imps import *
from Settings import *
from Gestione Colore
import check_black, check_color
from Mappa import Mappa
from Robot import Robot
import threading
import time
import cv2
import reset_button
from gpiozero import DigitalOutputDevice

lop_interrupt = DigitalOutputDevice(17)


class World:
    def __init__(self, rows=INIT_ROWS, cols=INIT_COLS):
        # 1. Lista mappa (piani): self.piani[liv]
        self.piani = [Mappa(rows, cols)]
        self.current_floor = 0

        # 2. Oggetto Robot
        self.robot = Robot()

        # 3. Lista posizioni vittime [liv][coord]
        self.vittime = {0: {}}

        # Posizione iniziale sul piano corrente
        m = self.current_map()
        self.robot.coordinata.x = m.w // 2
        self.robot.coordinata.y = m.h // 2
        m.home = (self.robot.coordinata.x, self.robot.coordinata.y)
        m.visit_current(self.robot.coordinata.y, self.robot.coordinata.x)

        self.target = None
        self.mode = "idle"
        self.isInvertito = False

        # Thread controllo nero
        self.run_event = threading.Event()
        self.stop_event = threading.Event()
        self.thread_check_black = threading.Thread(
            target=check_black, args=(self.run_event, self.stop_event), daemon=False
        )
        self.thread_check_black.start()
        print("|||||||| thread nero iniziato ||||||||||")

        self.last_checkpoint = m.home
        self.lop_event = threading.Event()
        reset_button.setup_button()
        self.thread_lop_handler = threading.Thread(target=self.handle_lop, daemon=True)
        self.thread_lop_handler.start()
        print("|||||||| thread pulsante iniziato ||||||||")

    def current_map(self):
        """Restituisce la mappa del piano corrente."""
        return self.piani[self.current_floor]

    def add_floor(self):
        """Aggiunge un nuovo piano (livello) alla lista."""
        new_map = Mappa(self.current_map().h, self.current_map().w)
        self.piani.append(new_map)
        self.current_floor = len(self.piani) - 1
        self.vittime[self.current_floor] = {}
        self.robot.coordinata.x = new_map.w // 2
        self.robot.coordinata.y = new_map.h // 2
        new_map.home = (self.robot.coordinata.x, self.robot.coordinata.y)
        new_map.visit_current(self.robot.coordinata.y, self.robot.coordinata.x)
        print(f"::::::::: Passato al nuovo piano [{self.current_floor}] ::::::::::")

    def registra_vittima(self, x, y, tipo, lato):
        """Salva una vittima nella struttura [liv][coord]"""
        if self.current_floor not in self.vittime:
            self.vittime[self.current_floor] = {}
        self.vittime[self.current_floor][(x, y)] = {'type': tipo, 'side': lato}
        print(f"##### Vittima {tipo} ({lato}) registrata al piano {self.current_floor} in ({x},{y}) #####")

    def handle_lop(self):
        while True:
            reset_button.wait_for_press()
            print("RESET " * 10)
            lop_interrupt.on()
            time.sleep(0.05)
            lop_interrupt.off()
            self.lop_event.set()

    def shutdown(self):
        print("SHUTDOWN WORLD in corso")
        self.stop_event.set()
        self.run_event.set()
        if self.thread_check_black.is_alive():
            self.thread_check_black.join()
        print("SHUTDOWN WORLD completo")

    def check_movement_confirmation(self):
        recived_command = ""
        while recived_command != "1" and recived_command != "-1":
            if self.lop_event.is_set():
                return False
            recived_command = self.robot.seriale.readline().decode('utf-8').rstrip()
            print("ricevuto da seriale:", recived_command)
            time.sleep(0.01)
        return recived_command == "1"

    # ---------- Gestione movimento tramite Robot ----------
    def rotate_left(self):
        self.robot.gradi -= 90
        self.robot.gradi = ((self.robot.gradi % 360) + 360) % 360
        self.robot.seriale.write(b'a090,')
        print("------ inviato a090, ------")
        self.robot.checkCommand("True")
        self.check_movement_confirmation()

    def rotate_right(self):
        self.robot.gradi += 90
        self.robot.gradi = ((self.robot.gradi % 360) + 360) % 360
        self.robot.seriale.write(b'd090,')
        print("------ inviato d090, ------")
        self.robot.checkCommand("True")
        self.check_movement_confirmation()

    def flip_direction(self):
        self.robot.gradi += 180
        self.robot.gradi = ((self.robot.gradi % 360) + 360) % 360
        self.robot.seriale.write(b's,')
        self.robot.checkCommand("True")
        self.isInvertito = not self.isInvertito
        print("----- inversione -----")
        if not self.isInvertito:
            self.run_event.set()
        else:
            self.run_event.clear()

    def forward(self):
        m = self.current_map()
        rx, ry = self.robot.coordinata.x, self.robot.coordinata.y
        dir_idx = Mappa.dir_index_from_deg(self.robot.gradi)
        bit = Mappa.bit_for_dir(dir_idx)
        if (m.walls[ry, rx] & bit) != 0:
            return False

        dx, dy = self.robot.headingToDelta()
        nx, ny = rx + dx, ry + dy
        nx, ny, rx, ry = m.ensure_inside(nx, ny, rx, ry)
        self.robot.coordinata.x = rx
        self.robot.coordinata.y = ry

        opp_bit = Mappa.bit_for_dir(Mappa.opposite_dir(dir_idx))
        if (m.walls[ny, nx] & opp_bit) != 0:
            return False
        if m.visited[ny, nx] == 2:
            return False

        moved = (nx != rx) or (ny != ry)
        if moved:
            self.robot.seriale.write(b'w032,')
            print("------ inviato w032, ------")
            self.robot.checkCommand("True")
            if self.check_movement_confirmation():
                if dx == 1:
                    self.robot.coordinata.incrementoX()
                elif dx == -1:
                    self.robot.coordinata.decrementoX()
                if dy == 1:
                    self.robot.coordinata.incrementoY()
                elif dy == -1:
                    self.robot.coordinata.decrementoY()

                m.visit_current(self.robot.coordinata.y, self.robot.coordinata.x)
            else:
                if not self.lop_event.is_set():
                    for d_idx in range(4):
                        m.set_wall_absolute(nx, ny, d_idx, 1)
                        m.visited[ny, nx] = 2
                moved = False
        return moved

    def get_walls(self, par_tof, par_dir):
        m = self.current_map()
        rx, ry = self.robot.coordinata.x, self.robot.coordinata.y
        self.robot.seriale.write(par_tof.encode())
        print(f"------ inviato {par_tof} ------")
        if self.robot.checkCommand("True"):
            is_wall = -1
            while is_wall == -1:
                is_wall = int(self.robot.seriale.readline().decode('utf-8').rstrip())
                print("is_wall:", is_wall)
                if is_wall == 1:
                    cur_abs = Mappa.dir_index_from_deg(self.robot.gradi)
                    abs_idx = (cur_abs + par_dir) % 4
                    dxdy = [(0, -1), (1, 0), (0, 1), (-1, 0)][abs_idx]
                    nx, ny = rx + dxdy[0], ry + dxdy[1]
                    nx, ny, rx, ry = m.ensure_inside(nx, ny, rx, ry)
                    self.robot.coordinata.x = rx
                    self.robot.coordinata.y = ry
                    m.toggle_wall_absolute(rx, ry, abs_idx)
                    m.toggle_wall_absolute(nx, ny, Mappa.opposite_dir(abs_idx))
                    m.visit_current(ry, rx)

    # ---------- Interfaccia sensore colore ----------
    def get_color(self):
        m = self.current_map()
        rx, ry = self.robot.coordinata.x, self.robot.coordinata.y
        if m.visited[ry, rx] not in (2, 3, 4, 5):
            m.visited[ry, rx] = check_color()
        if m.visited[ry, rx] == 5:
            m.last_checkpoint = (rx, ry)
            print(f"::::::::: Checkpoint salvato: ({rx},{ry}) ::::::::::")

    def check_inclination(self):
        m = self.current_map()
        rx, ry = self.robot.coordinata.x, self.robot.coordinata.y
        inclination = self.robot.checkInclinazione()
        if inclination is not None and 20 <= abs(inclination) <= 25:
            m.visited[ry, rx] = 4

    def get_cell_info(self, gx, gy):
        m = self.current_map()
        val = int(m.visited[gy, gx])
        return {
            "x": gx,
            "y": gy,
            "state": val,
            "walls": int(m.walls[gy, gx]),
            "cost": float(m.cell_cost(val)),
            "blocked": val == 2,
        }

    def neighbors(self, gx, gy):
        return self.current_map().neighbors(gx, gy)

    def can_step_to(self, x, y, nx, ny):
        return self.current_map().can_step_to(x, y, nx, ny)

    def dijkstra(self, start, goal):
        return self.current_map().dijkstra(start, goal)

    def bottom_right_cell(self):
        m = self.current_map()
        return (m.w - 1, m.h - 1)

    def face_towards(self, nx, ny):
        rx, ry = self.robot.coordinata.x, self.robot.coordinata.y
        dx = np.sign(nx - rx)
        dy = np.sign(ny - ry)
        if dy < 0:
            want = 0
        elif dy > 0:
            want = 2
        elif dx > 0:
            want = 1
        else:
            want = 3
        while Mappa.dir_index_from_deg(self.robot.gradi) != want:
            cur = Mappa.dir_index_from_deg(self.robot.gradi)
            diff = (want - cur) % 4
            if diff == 3:
                self.rotate_left()
            else:
                self.rotate_right()

    def follow_path(self, path, on_step=None, stop_when_home=False):
        m = self.current_map()
        for idx, (nx, ny) in enumerate(path):
            if self.lop_event.is_set():
                print("Lop rilevato nel follow path, interrompo movimento")
                return False

            rx, ry = self.robot.coordinata.x, self.robot.coordinata.y
            print(f"::::::::: STEP {idx + 1}/{len(path)}: verso ({nx},{ny}) ::::::::::")

            print("::::::::: SCANSIONE MURI PRIMA DEL MOVIMENTO ::::::::::")
            self.get_walls("m001,", 0)
            self.get_walls("m002,", 1)
            self.get_walls("m003,", 2)
            self.get_walls("m004,", 3)

            if not self.can_step_to(rx, ry, nx, ny):
                print(f"::::::::: BLOCCATO! Muro tra ({rx},{ry}) e ({nx},{ny}) ::::::::::")
                return False

            print("::::::::: Orientamento verso destinazione ::::::::::")
            self.face_towards(nx, ny)

            print("::::::::: Tentativo movimento avanti ::::::::::")
            has_moved = self.forward()

            if not has_moved:
                print("::::::::: MOVIMENTO FALLITO ::::::::::")
                return False

            rx, ry = self.robot.coordinata.x, self.robot.coordinata.y
            print(f"::::::::: Movimento riuscito! Nuova posizione: ({rx},{ry}) ::::::::::")
            self.get_color()
            self.check_inclination()

            if on_step is not None:
                if on_step():
                    return False

            if stop_when_home and (rx, ry) == m.home:
                print("::::::::: RITORNO A CASA COMPLETATO ::::::::::")
                return True

        print("::::::::: PERCORSO COMPLETATO ::::::::::")
        return True

    def render(self):
        m = self.current_map()
        rx, ry = self.robot.coordinata.x, self.robot.coordinata.y
        start_c = max(0, min(m.w - VIEW_COLS, rx - VIEW_COLS // 2)) if m.w > VIEW_COLS else 0
        start_r = max(0, min(m.h - VIEW_ROWS, ry - VIEW_ROWS // 2)) if m.h > VIEW_ROWS else 0

        img = np.full((VIEW_H, VIEW_W, 3), 255, dtype=np.uint8)

        for vr in range(VIEW_ROWS):
            gy = start_r + vr
            if gy >= m.h:
                break
            for vc in range(VIEW_COLS):
                gx = start_c + vc
                if gx >= m.w:
                    break
                val = m.visited[gy, gx]
                if val == 0:
                    continue
                x0 = vc * CELL
                y0 = vr * CELL
                x1 = x0 + CELL - 1
                y1 = y0 + CELL - 1
                if val == 1:
                    cv2.rectangle(img, (x0, y0), (x1, y1), COLOR_YELLOW, thickness=-1)
                elif val == 2:
                    cv2.rectangle(img, (x0, y0), (x1, y1), COLOR_BLACK, thickness=-1)
                elif val == 3:
                    cv2.rectangle(img, (x0, y0), (x1, y1), COLOR_BLUE, thickness=-1)
                elif val == 4:
                    cv2.rectangle(img, (x0, y0), (x1, y1), COLOR_GREEN, thickness=-1)
                elif val == 5:
                    cv2.rectangle(img, (x0, y0), (x1, y1), COLOR_GREY, thickness=-1)

        for r in range(VIEW_ROWS + 1):
            y = r * CELL
            cv2.line(img, (0, y), (VIEW_W, y), GRID_COLOR, 1)
        for c in range(VIEW_COLS + 1):
            x = c * CELL
            cv2.line(img, (x, 0), (x, VIEW_H), GRID_COLOR, 1)

        inset = max(2, CELL // 8)
        thick = max(2, CELL // 10)
        for vr in range(VIEW_ROWS):
            gy = start_r + vr
            if gy >= m.h:
                break
            for vc in range(VIEW_COLS):
                gx = start_c + vc
                if gx >= m.w:
                    break
                wmask = m.walls[gy, gx]
                if wmask == 0:
                    continue
                x0 = vc * CELL
                y0 = vr * CELL
                x1 = x0 + CELL - 1
                y1 = y0 + CELL - 1
                if wmask & 1:
                    cv2.line(img, (x0 + inset, y0 + inset), (x1 - inset, y0 + inset), (0, 0, 0), thick)
                if wmask & 2:
                    cv2.line(img, (x1 - inset, y0 + inset), (x1 - inset, y1 - inset), (0, 0, 0), thick)
                if wmask & 4:
                    cv2.line(img, (x0 + inset, y1 - inset), (x1 - inset, y1 - inset), (0, 0, 0), thick)
                if wmask & 8:
                    cv2.line(img, (x0 + inset, y0 + inset), (x0 + inset, y1 - inset), (0, 0, 0), thick)

        px = rx - start_c
        py = ry - start_r
        if 0 <= px < VIEW_COLS and 0 <= py < VIEW_ROWS:
            cx = int(px * CELL + CELL / 2)
            cy = int(py * CELL + CELL / 2)
            radius = int(CELL * 0.35)
            cv2.circle(img, (cx, cy), radius, COLOR_PLAYER, thickness=-1)
            dx, dy = self.robot.headingToDelta()
            tip = (int(cx + dx * radius * 0.9), int(cy + dy * radius * 0.9))
            cv2.line(img, (cx, cy), tip, (0, 0, 0), 2)

        hud = (
            f"Piano: {self.current_floor}  Pos: ({rx},{ry})  Gradi: {self.robot.gradi}  Matrice: {m.w}x{m.h}  "
            f"Walls: {int(m.walls[ry, rx])}"
        )
        cv2.rectangle(img, (0, 0), (VIEW_W, 24), (245, 245, 245), -1)
        cv2.putText(img, hud, (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.4, TXT, 1, cv2.LINE_AA)

        return img
