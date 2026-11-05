from settings import *
from imps import *
import sys

# Stati celle in "visited"
# 0 = white (not yet visited)[cite: 8]
# 1 = giallo (visited)[cite: 8]
# 2 = nero (NOT VISITABLE)[cite: 8]
# 3 = blu (B)[cite: 8]
# 4 = verde (G)[cite: 8]
# 5 = grigio (M)[cite: 8]

def main():
    # ========== INIZIALIZZAZIONE ==========[cite: 8]
    world = World()
    world.ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)  # COM* on Windows, /dev/ttyUSB* on Raspberry[cite: 8]
    world.robot.seriale = world.ser
    print("::::::::: Connessione seriale stabilita ::::::::::")
    print(world.ser)

    # Attendi che Arduino sia pronto[cite: 8]
    world.robot.checkCommand("START")
    print("::::::::: Arduino pronto ::::::::::")
    start_time = time.time()
    explore_seconds = 8 * 60 * 0.66  # prendo il 66% dei secondi di gara prima di tornare a casa autonomamente[cite: 8]

    # Setup finestra OpenCV[cite: 8]
    cv2.namedWindow('Campo', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Campo', VIEW_W, VIEW_H)

    # ========== SCANSIONE INIZIALE AMBIENTE ==========[cite: 8]
    print("\n" + "=" * 60)
    print("::::::::: SCANSIONE AMBIENTE INIZIALE ::::::::::")
    print("=" * 60)
    world.get_walls("m001,", 0)  # fronte[cite: 8]
    world.get_walls("m002,", 1)  # destra[cite: 8]
    world.get_walls("m003,", 2)  # retro[cite: 8]
    world.get_walls("m004,", 3)  # sinistra[cite: 8]

    m = world.current_map()
    rx, ry = world.robot.coordinata.x, world.robot.coordinata.y
    print(f"::::::::: Muri iniziali rilevati (bitmask): {int(m.walls[ry, rx])} ::::::::::")
    print("=" * 60 + "\n")

    # ========== FINE SCANSIONE INIZIALE ==========[cite: 8]

    def handle_key(k):
        """
        Gestisce input tastiera.[cite: 8]
        Ritorna:
            - 'quit': termina programma[cite: 8]
            - 'repath': interrompe autopilot e forza ricalcolo[cite: 8]
            - None: continua normalmente[cite: 8]
        """
        if k == ord('q') or k == 27:  # Q o ESC[cite: 8]
            return 'quit'

        # --- CONTROLLO MANUALE (interrompe autopilot) ---[cite: 8]
        elif k in (KEY_W, KEY_WU):
            world.forward()
            return 'repath'
        elif k in (KEY_A, KEY_AU):
            world.rotate_left()
            return 'repath'
        elif k in (KEY_D, KEY_DU):
            world.rotate_right()
            return 'repath'
        elif k in (KEY_S, KEY_SU):
            world.flip_direction()
            return 'repath'

        # --- MODIFICA MAPPA (NON interrompe autopilot) ---[cite: 8]
        elif k == ord('1'):
            world.get_walls("m001,", 0)
            return None
        elif k == ord('2'):
            world.get_walls("m002,", 1)
            return None
        elif k == ord('3'):
            world.get_walls("m003,", 2)
            return None
        elif k == ord('4'):
            world.get_walls("m004,", 3)
            return None
        elif k == ord('n') or k == ord('N'):
            # Blocca casella davanti[cite: 8]
            dx, dy = world.robot.headingToDelta()
            rx, ry = world.robot.coordinata.x, world.robot.coordinata.y
            nx, ny = rx + dx, ry + dy
            map_curr = world.current_map()
            nx, ny, rx, ry = map_curr.ensure_inside(nx, ny, rx, ry)
            world.robot.coordinata.x = rx
            world.robot.coordinata.y = ry
            for dir_idx in range(4):
                map_curr.set_wall_absolute(nx, ny, dir_idx, 1)
            map_curr.visited[ny, nx] = 2
            print("::::::::: Casella davanti bloccata manualmente ::::::::::")
            return None
        elif k == ord('b') or k == ord('B'):
            # Colora casella corrente di blu[cite: 8]
            map_curr = world.current_map()
            rx, ry = world.robot.coordinata.x, world.robot.coordinata.y
            map_curr.visited[ry, rx] = 3
            print("::::::::: Casella corrente colorata BLU ::::::::::")
            return None
        elif k == ord('g') or k == ord('G'):
            # Controlla inclinazione[cite: 8]
            world.check_inclination()
            return None
        elif k == ord('m') or k == ord('M'):
            # Colora casella corrente di grigio (checkpoint)[cite: 8]
            map_curr = world.current_map()
            rx, ry = world.robot.coordinata.x, world.robot.coordinata.y
            map_curr.visited[ry, rx] = 5
            print("::::::::: Casella corrente colorata GRIGIO (checkpoint) ::::::::::")
            return None

        # --- CAMBIO OBIETTIVO (interrompe autopilot) ---[cite: 8]
        elif k == ord('t') or k == ord('T'):
            world.target = world.bottom_right_cell()
            world.mode = 'to_target'
            print(f"::::::::: NUOVO OBIETTIVO: Angolo basso-destra {world.target} ::::::::::")
            return 'repath'
        elif k == ord('e') or k == ord('E'):
            map_curr = world.current_map()
            world.target = map_curr.home
            world.mode = 'to_home'
            print(f"::::::::: NUOVO OBIETTIVO: Ritorno a casa {map_curr.home} ::::::::::")
            return 'repath'

        return None

    def on_step():
        """
        Pausa intelligente durante autopilot.[cite: 8]
        Permette input utente durante il movimento automatico.[cite: 8]
        Ritorna True se l'autopilot deve fermarsi.[cite: 8]
        """
        end_t = time.time() + (STEP_DELAY_MS / 1000.0)
        need_stop = False

        while time.time() < end_t and not need_stop:
            # Aggiorna visualizzazione[cite: 8]
            frame = world.render()
            cv2.imshow('Campo', frame)

            # Controlla input (non bloccante)[cite: 8]
            k = cv2.waitKey(INPUT_POLL_MS) & 0xFF
            if k == 255:  # Nessun input[cite: 8]
                continue

            # Gestisci input[cite: 8]
            res = handle_key(k)
            if res in ('quit', 'repath'):
                need_stop = True

        return need_stop

    # ========== MAIN LOOP ==========[cite: 8]
    print("\n" + "=" * 60)
    print("::::::::: MAIN LOOP AVVIATO ::::::::::")
    print("=" * 60)
    print("COMANDI:")
    print("  T = vai verso angolo basso-destra")
    print("  E = ritorna a casa")
    print("  W/A/D/S = controllo manuale")
    print("  1/2/3/4 = scansiona muro specifico")
    print("  N = blocca casella davanti")
    print("  B = colora casella blu")
    print("  G = controlla inclinazione")
    print("  M = segna checkpoint")
    print("  Q/ESC = esci")
    print("=" * 60 + "\n")

    while True:
        # ========== RENDERING ==========[cite: 8]
        frame = world.render()
        cv2.imshow('Campo', frame)

        # ========== INPUT MANAGEMENT ==========[cite: 8]
        if world.mode in ('to_target', 'to_home'):
            key = cv2.waitKey(INPUT_POLL_MS) & 0xFF  # Non bloccante[cite: 8]
        else:
            key = cv2.waitKey(0) & 0xFF  # Bloccante in idle[cite: 8]

        # ========== GESTIONE COMANDI ==========[cite: 8]
        if key != 255:  # Input ricevuto[cite: 8]
            res = handle_key(key)
            if res == 'quit':
                print("\n::::::::: USCITA RICHIESTA ::::::::::")
                break
            if res == 'repath':
                continue

        # ========== AUTOPILOT ==========[cite: 8]
        if world.mode in ('to_target', 'to_home'):
            map_curr = world.current_map()
            goal = world.target if world.mode == 'to_target' else map_curr.home
            rx, ry = world.robot.coordinata.x, world.robot.coordinata.y

            print("\n" + "-" * 60)
            print(f"::::::::: AUTOPILOT ATTIVO: {world.mode} ::::::::::")
            print(f"::::::::: Posizione attuale: ({rx},{ry}) ::::::::::")
            print(f"::::::::: Obiettivo: {goal} ::::::::::")
            print("-" * 60)

            # ========== LOOP RETRY ==========[cite: 8]
            while time.time() - start_time < explore_seconds or world.mode == 'to_home':
                rx, ry = world.robot.coordinata.x, world.robot.coordinata.y
                start = (rx, ry)
                print(f"::::::::: Calcolo percorso da {start} a {goal} ::::::::::")

                path = world.dijkstra(start, goal)

                # ========== TERMINAZIONE SU PERCORSO IMPOSSIBILE ==========[cite: 8]
                if path is None or len(path) == 0:
                    print("\n" + "X" * 60)
                    print("ERRORE FATALE: NESSUN PERCORSO TROVATO!")
                    print(f"Posizione attuale: ({rx}, {ry})".ljust(58))
                    print(f"Obiettivo: {goal}".ljust(58))
                    print("Il robot è completamente bloccato.")
                    print("Impossibile proseguire.")
                    print("TERMINAZIONE PROGRAMMA.")
                    print("X" * 60 + "\n")

                    world.shutdown()
                    cv2.destroyAllWindows()
                    sys.exit(1)

                print(f"::::::::: Percorso trovato! Lunghezza: {len(path)} passi ::::::::::")
                print(f"::::::::: Percorso: {path[:5]}{'...' if len(path) > 5 else ''} ::::::::::")

                completed = world.follow_path(
                    path,
                    on_step=on_step,
                    stop_when_home=(world.mode == 'to_home')
                )

                if completed:
                    print("\n" + "=" * 60)
                    print("::::::::: PERCORSO COMPLETATO CON SUCCESSO! ::::::::::")
                    print("=" * 60 + "\n")

                    rx, ry = world.robot.coordinata.x, world.robot.coordinata.y
                    if world.mode == 'to_home' and (rx, ry) == map_curr.home:
                        print("::::::::: MISSIONE COMPLETATA: RITORNO A CASA ::::::::::")
                        world.mode = 'idle'

                    break
                else:
                    # ========= GESTIONE LOP =========[cite: 8]
                    if world.lop_event.is_set():
                        world.lop_event.clear()
                        print("::::::::: LoP rilevato, aspetto 15 secondi per fare /tp... :::::::::")
                        time.sleep(15)
                        world.robot.coordinata.x, world.robot.coordinata.y = map_curr.last_checkpoint
                        world.robot.gradi = 0
                        print(f"::::::::: LoP, /tp a checkpoint: {map_curr.last_checkpoint} :::::::::")
                        continue

                    if time.time() - start_time >= explore_seconds:
                        print("\n" + "!" * 60)
                        print("::::::::: TEMPO SCADUTO, TORNO A CASA ::::::::::")
                        print("!" * 60 + "\n")

            if world.mode != 'idle':
                world.mode = 'idle'
                print("::::::::: Autopilot completato, torno in IDLE ::::::::::")

    # ========== SHUTDOWN NORMALE ==========[cite: 8]
    print("\n" + "=" * 60)
    print("::::::::: SHUTDOWN IN CORSO ::::::::::")
    print("=" * 60)
    world.shutdown()
    cv2.destroyAllWindows()
    print("::::::::: PROGRAMMA TERMINATO ::::::::::")


if __name__ == '__main__':
    main()
