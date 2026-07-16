# Desktop Kitten 🐈‍⬛

A pixel-art black cat that lives on your screen: wanders, plays, sleeps,
watches you with its eyes, can be dragged, and does a few small real
file chores.

## What's new in this version

- **Eyes track your mouse** - live, every frame, not just when it's
  reacting to you.
- **No square background (experimental)** - instead of a solid color,
  the cat's window now screenshots whatever is behind it and uses that
  as its backdrop, so it blends in like a true floating sprite. This is
  a workaround, not real OS transparency (which turned out to be
  unreliable on this Mac's Tk build) - it re-captures the screen behind
  the cat every animation frame. On a 2011 MacBook this may look a
  little choppy, especially while it's walking fast or you're dragging
  it. **If it's too laggy or looks glitchy, open `desktop_pet.py`, find**
  **`EXPERIMENTAL_TRANSPARENCY = True` near the top, and change it to**
  **`False`** - that instantly reverts to the plain solid-lavender
  background, which is smooth and always reliable.

## What it does

- **Wanders**, sits, naps, stretches near the bottom of your screen.
- **Reacts to your mouse** - perks up and pounces/paws playfully when
  the cursor gets close, drifts curiously toward it from farther away.
- **Chase mode** - double-click the cat (or use the right-click menu)
  to make it actively follow your cursor. Double-click again to stop.
- **Left-click and drag** picks it up and moves it anywhere.
- **Plain left-click** pets it - purr + speech bubble.
- **Right-click** (or Control-click) opens its menu: tidy Desktop by
  file type (moves only, asks first, never deletes), find Downloads
  files older than 30 days, count files in any folder, open
  Desktop/Downloads in Finder, watch Desktop for new files, nap, quit.

## Setup (macOS)

Python 3.12 + Pillow, already set up, no Homebrew needed.

1. Put `desktop_pet.py` and `sprites.py` together in one folder.
2. Terminal:
   ```
   cd /path/to/that/folder
   python3 desktop_pet.py
   ```
3. It'll print `[kitten] ...` status lines the whole time (set
   `DEBUG = False` near the top once you don't need them).

### If it overlaps your Dock

Raise `BOTTOM_MARGIN` near the top of `desktop_pet.py`.

### Known limitation

Shows up as a running `python3` process in your Dock while active.
