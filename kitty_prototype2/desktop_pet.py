#!/usr/bin/env python3
"""
Desktop Kitten - a little pixel-art black cat that lives on your screen.

Walks around, gets curious and plays when your mouse is nearby, watches
you with its eyes, can be picked up and dragged, and does a few small
real file-system chores from its right-click menu (nothing it does is
destructive - files only ever get *moved into* a folder, never deleted).

Run it with:  python3 desktop_pet.py
Quit it from the right-click menu, or Ctrl+C in the terminal.
"""

import sys
import time
import random
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

try:
    from PIL import Image, ImageTk
except ImportError:
    print("This needs Pillow. Install it with:\n    pip3 install --user Pillow")
    sys.exit(1)

import sprites

# ---------------------------------------------------------------- CONFIG --
SCALE = 3                    # sprite pixel scale (bigger = bigger cat)
WALK_SPEED = 3                 # pixels per tick while walking
TICK_MS = 120                    # animation/behavior tick, ms
BOTTOM_MARGIN = 90               # keep clear of the Dock
ALERT_RADIUS = 180               # how close the mouse gets before the cat notices
CURIOUS_RADIUS = 350               # wider range where a walking cat drifts toward the cursor
DRAG_THRESHOLD = 4               # pixels of movement before a click counts as a drag
DESKTOP = Path.home() / "Desktop"
DOWNLOADS = Path.home() / "Downloads"
BG_COLOR = "#f0e6ff"               # solid backdrop used unless EXPERIMENTAL_TRANSPARENCY is on

# EXPERIMENTAL: fakes a transparent background by screenshotting whatever
# is behind the cat and using that as the backdrop instead of a solid
# color. No box - but it means capturing the screen every tick, which is
# slower and can look choppy on older Macs. Off by default so the cat is
# always at least reliably visible; flip to True to try it.
EXPERIMENTAL_TRANSPARENCY = True

DEBUG = True
# ----------------------------------------------------------------------- --


def log(*args):
    if DEBUG:
        print("[kitten]", *args)


class DesktopPet:
    def __init__(self):
        log("creating window...")
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.config(bg=BG_COLOR)

        sample = sprites.base_frame("idle", "right", 0)
        self.pet_w = sample.width * SCALE
        self.pet_h = sample.height * SCALE

        self.label = tk.Label(self.root, bd=0, bg=BG_COLOR)
        self.label.pack()

        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()
        self.x = random.randint(50, self.screen_w - 150)
        self.y = self.screen_h - BOTTOM_MARGIN - self.pet_h
        self.root.geometry(f"+{self.x}+{self.y}")
        log(f"screen is {self.screen_w}x{self.screen_h}, cat placed at ({self.x},{self.y}), "
            f"sprite size {self.pet_w}x{self.pet_h}, transparency={EXPERIMENTAL_TRANSPARENCY}")

        self.direction = random.choice(["left", "right"])
        self.pose = "idle"
        self.anim_frame = 0
        self.state = "idle"          # idle, walk, sleep, alert, pounce, play, stretch, dragged
        self.state_timer = 0
        self.cooldown_until = 0
        self.chase_mode = False

        self.dragging = False
        self.drag_moved = False
        self.drag_offset = (0, 0)

        self.watch_desktop = False
        self._desktop_snapshot = None

        self.bubble = None
        self._gaze = (0, 0)

        self.label.bind("<ButtonPress-1>", self.on_press)
        self.label.bind("<B1-Motion>", self.on_motion)
        self.label.bind("<ButtonRelease-1>", self.on_release)
        self.label.bind("<Double-Button-1>", self.toggle_chase_mode)
        self.label.bind("<Button-2>", self.show_menu)
        self.label.bind("<Button-3>", self.show_menu)
        self.label.bind("<Control-Button-1>", self.show_menu)

        self._build_menu()
        self._render()
        self.root.after(TICK_MS, self.tick)

    # ----------------------------------------------------------- render --
    def _current_pil_frame(self, mx, my):
        frame_idx = self.anim_frame % sprites.FRAME_COUNTS.get(self.pose, 1)
        img = sprites.base_frame(self.pose, self.direction, frame_idx)
        anchors = sprites.eye_anchor_points(self.pose, self.direction, frame_idx)
        if anchors:
            cat_cx = self.x + self.pet_w / 2
            cat_cy = self.y + self.pet_h / 2
            gx = 1 if mx > cat_cx + 10 else (-1 if mx < cat_cx - 10 else 0)
            gy = 1 if my > cat_cy + 10 else (-1 if my < cat_cy - 10 else 0)
            self._gaze = (gx, gy)
            img = sprites.with_pupils(img, anchors, gx, gy)
        return img.resize((self.pet_w, self.pet_h), Image.NEAREST)

    def _capture_background(self):
        tmp = "/tmp/_kitten_bg.png"
        try:
            self.root.withdraw()
            self.root.update()
            subprocess.run(
                ["screencapture", "-x", f"-R{int(self.x)},{int(self.y)},{self.pet_w},{self.pet_h}", tmp],
                timeout=1.5, check=True,
            )
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            return Image.open(tmp).convert("RGBA")
        except Exception as e:
            try:
                self.root.deiconify()
                self.root.attributes("-topmost", True)
            except tk.TclError:
                pass
            log("background capture failed:", repr(e))
            return None

    def _render(self):
        mx, my = self.root.winfo_pointerx(), self.root.winfo_pointery()
        cat_img = self._current_pil_frame(mx, my)

        if EXPERIMENTAL_TRANSPARENCY:
            bg = self._capture_background()
            if bg is not None and bg.size == cat_img.size:
                bg.alpha_composite(cat_img)
                final = bg
            else:
                final = cat_img
        else:
            final = cat_img

        photo = ImageTk.PhotoImage(final)
        self.label.configure(image=photo)
        self.label.image = photo
        self.root.geometry(f"+{int(self.x)}+{int(self.y)}")

    # ------------------------------------------------------------- menu --
    def _build_menu(self):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="Pet the cat", command=self.do_pet)
        m.add_command(label="Toggle chase mode (or double-click the cat)", command=self.toggle_chase_mode)
        m.add_separator()
        m.add_command(label="Tidy up Desktop by file type", command=self.tidy_desktop)
        m.add_command(label="Find old Downloads (30+ days)", command=self.find_old_downloads)
        m.add_command(label="Count files in a folder...", command=self.count_folder)
        m.add_command(label="Open Desktop in Finder", command=lambda: self.open_in_finder(DESKTOP))
        m.add_command(label="Open Downloads in Finder", command=lambda: self.open_in_finder(DOWNLOADS))
        self.watch_var = tk.BooleanVar(value=False)
        m.add_checkbutton(label="Watch Desktop for new files", variable=self.watch_var,
                           command=lambda: setattr(self, "watch_desktop", self.watch_var.get()))
        m.add_separator()
        m.add_command(label="Nap", command=self.force_sleep)
        m.add_command(label="Quit", command=self.root.destroy)
        self.menu = m

    def show_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    # -------------------------------------------------------- interaction
    def on_press(self, event):
        self.dragging = True
        self.drag_moved = False
        self.drag_offset = (event.x, event.y)
        self.state = "dragged"

    def on_motion(self, event):
        if not self.dragging:
            return
        dx = event.x - self.drag_offset[0]
        dy = event.y - self.drag_offset[1]
        if abs(dx) > DRAG_THRESHOLD or abs(dy) > DRAG_THRESHOLD:
            self.drag_moved = True
        self.x += dx
        self.y += dy
        self.x = max(0, min(self.screen_w - self.pet_w, self.x))
        self.y = max(0, min(self.screen_h - self.pet_h, self.y))
        self._render()

    def on_release(self, event):
        self.dragging = False
        if not self.drag_moved:
            self.do_pet()
        else:
            self.state = "idle"
            self.state_timer = 0

    def do_pet(self):
        self.pose = "alert"
        self.say(random.choice(["mrrp!", "purr~", ":3", "mew"]))
        self.state = "idle"
        self.state_timer = 0
        self.cooldown_until = time.time() + 2

    def toggle_chase_mode(self, event=None):
        self.chase_mode = not self.chase_mode
        self.say("chase mode on!" if self.chase_mode else "chase mode off")
        self.state = "idle"
        self.state_timer = 0

    def force_sleep(self):
        self.state = "sleep"
        self.state_timer = 0

    def say(self, text):
        if self.bubble is not None:
            self.bubble.destroy()
        b = tk.Toplevel(self.root)
        b.overrideredirect(True)
        b.attributes("-topmost", True)
        lbl = tk.Label(b, text=text, bg="#fffdf0", fg="#333",
                        font=("Menlo", 11), padx=6, pady=2,
                        relief="solid", bd=1)
        lbl.pack()
        b.update_idletasks()
        bx = int(self.x + self.pet_w / 2 - b.winfo_width() / 2)
        by = int(self.y - b.winfo_height() - 4)
        b.geometry(f"+{bx}+{by}")
        self.bubble = b
        self.root.after(1600, self._clear_bubble)

    def _clear_bubble(self):
        if self.bubble is not None:
            try:
                self.bubble.destroy()
            except tk.TclError:
                pass
            self.bubble = None

    # ---------------------------------------------------------- behavior
    def tick(self):
        if not self.dragging:
            self._behave()
        self.anim_frame += 1
        self._render()
        if self.anim_frame % 25 == 0:
            log(f"alive - pos=({int(self.x)},{int(self.y)}) pose={self.pose} state={self.state}")
        if self.bubble is not None:
            bx = int(self.x + self.pet_w / 2 - self.bubble.winfo_width() / 2)
            by = int(self.y - self.bubble.winfo_height() - 4)
            self.bubble.geometry(f"+{bx}+{by}")
        self.root.after(TICK_MS, self.tick)

    def _behave(self):
        mx, my = self.root.winfo_pointerx(), self.root.winfo_pointery()
        cat_cx = self.x + self.pet_w / 2
        cat_cy = self.y + self.pet_h / 2
        dist = ((mx - cat_cx) ** 2 + (my - cat_cy) ** 2) ** 0.5

        if self.chase_mode:
            self.pose = "walk" if dist > 15 else "play"
            self.direction = "right" if mx > cat_cx else "left"
            if dist > 15:
                step = min(WALK_SPEED * 2, dist) * (1 if mx > cat_cx else -1)
                self.x += step
                self.x = max(0, min(self.screen_w - self.pet_w, self.x))
            return

        now = time.time()
        if (self.state in ("idle", "walk") and dist < ALERT_RADIUS
                and now > self.cooldown_until):
            self.state = "alert"
            self.state_timer = 0
            self.cooldown_until = now + 0.8
            self.direction = "right" if mx > cat_cx else "left"

        self.state_timer += 1

        if self.state == "alert":
            self.pose = "alert"
            self.direction = "right" if mx > cat_cx else "left"
            if self.state_timer > 3:
                self.state = "pounce"
                self.state_timer = 0
        elif self.state == "pounce":
            self.pose = "pounce"
            step = 5 if self.direction == "right" else -5
            if dist > 25:
                self.x += step
                self.x = max(0, min(self.screen_w - self.pet_w, self.x))
                self.direction = "right" if mx > cat_cx else "left"
            if self.state_timer > 6:
                self.state = "play" if dist < ALERT_RADIUS * 1.4 else "idle"
                self.state_timer = 0
        elif self.state == "play":
            self.pose = "play"
            self.direction = "right" if mx > cat_cx else "left"
            if self.state_timer > 12 or dist > ALERT_RADIUS * 1.8:
                self.state = "idle"
                self.state_timer = 0
        elif self.state == "stretch":
            self.pose = "stretch"
            if self.state_timer > 8:
                self.state = "idle"
                self.state_timer = 0
        elif self.state == "sleep":
            self.pose = "sleep"
            if self.state_timer > random.randint(40, 90):
                self.state = "stretch"
                self.state_timer = 0
        elif self.state == "walk":
            self.pose = "walk"
            if dist < CURIOUS_RADIUS:
                self.direction = "right" if mx > cat_cx else "left"
            step = WALK_SPEED if self.direction == "right" else -WALK_SPEED
            new_x = self.x + step
            if new_x <= 0 or new_x >= self.screen_w - self.pet_w:
                self.direction = "left" if self.direction == "right" else "right"
            else:
                self.x = new_x
            if self.state_timer > random.randint(25, 60):
                self.state = random.choice(["idle", "idle", "walk", "sleep"])
                self.state_timer = 0
        else:  # idle (sitting)
            self.pose = "idle"
            if self.state_timer > random.randint(15, 40):
                self.state = random.choice(["walk", "walk", "idle", "sleep", "stretch"])
                self.direction = random.choice(["left", "right"])
                self.state_timer = 0

        if self.watch_desktop and self.anim_frame % 25 == 0:
            self._check_desktop()

    # ------------------------------------------------------- file tasks --
    def open_in_finder(self, path):
        if not path.exists():
            messagebox.showinfo("Desktop Kitten", f"Couldn't find {path}.")
            return
        subprocess.run(["open", str(path)])
        self.say("here you go!")

    def _check_desktop(self):
        try:
            current = {p.name for p in DESKTOP.iterdir()}
        except FileNotFoundError:
            return
        if self._desktop_snapshot is None:
            self._desktop_snapshot = current
            return
        new_items = current - self._desktop_snapshot
        self._desktop_snapshot = current
        if new_items:
            name = next(iter(new_items))
            self.say(f"new file: {name[:18]}")

    def tidy_desktop(self):
        if not DESKTOP.exists():
            messagebox.showinfo("Desktop Kitten", "Couldn't find your Desktop folder.")
            return
        if not messagebox.askyesno(
            "Desktop Kitten",
            "I'll sort loose files on your Desktop into folders "
            "(Images, Documents, Other, ...) by file type.\n\n"
            "Nothing gets deleted, only moved. Go ahead?"
        ):
            return
        buckets = {
            "Images": {".png", ".jpg", ".jpeg", ".gif", ".heic", ".webp", ".svg"},
            "Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".pages", ".key", ".ppt", ".pptx"},
            "Spreadsheets": {".xls", ".xlsx", ".csv", ".numbers"},
            "Archives": {".zip", ".tar", ".gz", ".dmg"},
            "Code": {".py", ".js", ".html", ".css", ".json", ".sh"},
        }
        moved = 0
        for item in DESKTOP.iterdir():
            if item.is_dir():
                continue
            ext = item.suffix.lower()
            bucket = next((b for b, exts in buckets.items() if ext in exts), "Other")
            dest_dir = DESKTOP / bucket
            dest_dir.mkdir(exist_ok=True)
            try:
                item.rename(dest_dir / item.name)
                moved += 1
            except OSError:
                pass
        self.say(f"tidied {moved} files!")
        messagebox.showinfo("Desktop Kitten", f"Done - moved {moved} file(s) into folders.")

    def find_old_downloads(self):
        if not DOWNLOADS.exists():
            messagebox.showinfo("Desktop Kitten", "Couldn't find your Downloads folder.")
            return
        cutoff = time.time() - 30 * 86400
        old = []
        for item in DOWNLOADS.iterdir():
            if item.is_file():
                try:
                    if item.stat().st_mtime < cutoff:
                        old.append(item.name)
                except OSError:
                    pass
        if not old:
            messagebox.showinfo("Desktop Kitten", "No files older than 30 days in Downloads.")
            return
        preview = "\n".join(old[:25])
        more = f"\n...and {len(old) - 25} more" if len(old) > 25 else ""
        messagebox.showinfo(
            "Desktop Kitten",
            f"{len(old)} file(s) in Downloads are 30+ days old:\n\n{preview}{more}\n\n"
            "(Just a report - I didn't touch anything.)"
        )

    def count_folder(self):
        folder = filedialog.askdirectory(title="Pick a folder for the cat to count")
        if not folder:
            return
        p = Path(folder)
        files = [f for f in p.rglob("*") if f.is_file()]
        total_bytes = sum(f.stat().st_size for f in files if f.exists())
        mb = total_bytes / (1024 * 1024)
        messagebox.showinfo(
            "Desktop Kitten",
            f"{p.name}\n\n{len(files)} file(s)\n{mb:.1f} MB total"
        )

    def run(self):
        log("starting main loop - the cat should be visible now")
        self.root.mainloop()
        log("main loop ended (window was closed)")


if __name__ == "__main__":
    try:
        DesktopPet().run()
    except Exception:
        import traceback
        print("\n--- Desktop Kitten crashed ---")
        traceback.print_exc()
        input("\nPress Enter to close...")
