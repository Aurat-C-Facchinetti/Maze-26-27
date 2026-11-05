VIEW_W, VIEW_H = 640, 480      # fixed window
CELL = 20                      # constant cell size
VIEW_COLS = VIEW_W // CELL     # 32
VIEW_ROWS = VIEW_H // CELL     # 24
INIT_ROWS, INIT_COLS = VIEW_ROWS, VIEW_COLS  # start 24x32

STEP_DELAY_MS = 220            # pause between automatic steps
INPUT_POLL_MS = 35             # input polling delay

GRID_COLOR = (180, 180, 180)
TXT = (30, 30, 30)

# Colori celle
COLOR_YELLOW = (0, 255, 255)   # visited
COLOR_BLACK  = (0, 0, 0)       # blocked
COLOR_BLUE   = (255, 0, 0)     # special Blue
COLOR_GREEN  = (0, 255, 0)     # special Green
COLOR_GREY   = (128, 128, 128) # special Gray
COLOR_PLAYER = (0, 200, 0)     # player's color

# (WASD) Keys
KEY_W = ord('w'); KEY_WU = ord('W')
KEY_A = ord('a'); KEY_AU = ord('A')
KEY_S = ord('s'); KEY_SU = ord('S')
KEY_D = ord('d'); KEY_DU = ord('D')
# ============================================
