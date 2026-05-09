"""
UWB Tag Live Visualizer  — v4 (fixed room bounds + clamped tag)
==================================================
On launch, asks for the 3 anchor positions before starting.
Press Enter on each field, then click Start.

Requirements:
    pip install matplotlib numpy
Usage:
    python visualizer.py
"""

import socket
import threading
import time
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.widgets as widgets
from matplotlib.animation import FuncAnimation
from collections import deque

# ─── Defaults (pre-filled in the calibration screen) ─────────────────────────
DEFAULT_ANCHORS = {
    1: (0.0, 0.0),
    2: (3.5, 0.0),
    3: (0.0, 3.5),
}

UDP_PORT     = 5005
TRAIL_LENGTH = 80
PAD          = 0.0          # no padding — axes start exactly at room bounds

ANCHOR_COLORS = {1: "#e74c3c", 2: "#3498db", 3: "#2ecc71"}
TAG_COLOR     = "#f39c12"

# ─── Smoothing ────────────────────────────────────────────────────────────────
SMOOTH_ALPHA = 0.25
UPDATE_MS    = 50

# ─── Will be filled after calibration ────────────────────────────────────────
ANCHOR_POSITIONS = {}

# ─── Shared state ─────────────────────────────────────────────────────────────
state = {
    "distances":    {1: None, 2: None, 3: None},
    "tag_pos":      None,
    "smoothed_pos": None,
    "trail":        deque(maxlen=TRAIL_LENGTH),
    "last_update":  0.0,
    "packets":      0,
}
lock = threading.Lock()


# ─── Trilateration ────────────────────────────────────────────────────────────

def trilaterate(d1, d2, d3):
    (x1, y1) = ANCHOR_POSITIONS[1]
    (x2, y2) = ANCHOR_POSITIONS[2]
    (x3, y3) = ANCHOR_POSITIONS[3]
    A = np.array([
        [2*(x2-x1), 2*(y2-y1)],
        [2*(x3-x1), 2*(y3-y1)],
    ])
    b = np.array([
        d1**2 - d2**2 - x1**2 + x2**2 - y1**2 + y2**2,
        d1**2 - d3**2 - x1**2 + x3**2 - y1**2 + y3**2,
    ])
    try:
        if abs(np.linalg.det(A)) < 1e-10:
            return None
        pos = np.linalg.solve(A, b)
        return float(pos[0]), float(pos[1])
    except Exception:
        return None


# ─── UDP listener ─────────────────────────────────────────────────────────────

def udp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", UDP_PORT))
    sock.settimeout(1.0)
    print(f"[UDP] Listening on 0.0.0.0:{UDP_PORT} ...")

    while True:
        try:
            data, _ = sock.recvfrom(256)
            msg = data.decode("utf-8").strip()

            if msg.startswith("TAG:"):
                parts = msg[4:].split(",")
                if len(parts) == 3:
                    try:
                        d1, d2, d3 = float(parts[0]), float(parts[1]), float(parts[2])
                        pos = trilaterate(d1, d2, d3)
                        with lock:
                            state["distances"][1] = d1
                            state["distances"][2] = d2
                            state["distances"][3] = d3
                            state["packets"] += 1
                            if pos:
                                state["tag_pos"] = pos
                                sp = state["smoothed_pos"]
                                if sp is None:
                                    state["smoothed_pos"] = pos
                                else:
                                    state["smoothed_pos"] = (
                                        SMOOTH_ALPHA * pos[0] + (1 - SMOOTH_ALPHA) * sp[0],
                                        SMOOTH_ALPHA * pos[1] + (1 - SMOOTH_ALPHA) * sp[1],
                                    )
                                # Clamp to room bounds so tag never renders outside
                                _ax_vals = [p[0] for p in ANCHOR_POSITIONS.values()]
                                _ay_vals = [p[1] for p in ANCHOR_POSITIONS.values()]
                                cx = float(np.clip(state["smoothed_pos"][0], min(_ax_vals), max(_ax_vals)))
                                cy = float(np.clip(state["smoothed_pos"][1], min(_ay_vals), max(_ay_vals)))
                                state["smoothed_pos"] = (cx, cy)
                                state["trail"].append(state["smoothed_pos"])
                                state["last_update"] = time.time()
                        if pos:
                            print(f"  TAG raw=({pos[0]:.2f},{pos[1]:.2f}) "
                                  f"smooth=({state['smoothed_pos'][0]:.2f},"
                                  f"{state['smoothed_pos'][1]:.2f}) m")
                    except ValueError:
                        pass

            elif msg.startswith("A") and ":" in msg:
                try:
                    aid  = int(msg[1])
                    dist = float(msg.split(":")[1])
                    if aid in (1, 2, 3):
                        with lock:
                            state["distances"][aid] = dist
                except (ValueError, IndexError):
                    pass

        except socket.timeout:
            continue
        except Exception as e:
            print(f"[UDP error] {e}")


# ─── Calibration screen ───────────────────────────────────────────────────────

def show_calibration():
    fig_cal = plt.figure(figsize=(6, 6))
    fig_cal.patch.set_facecolor("#1a1a2e")
    fig_cal.canvas.manager.set_window_title("UWB Visualizer — Calibration")

    ax = fig_cal.add_axes([0, 0, 1, 1])
    ax.set_facecolor("#1a1a2e")
    ax.axis("off")

    ax.text(0.5, 0.93, "UWB Anchor Calibration",
            transform=ax.transAxes, color="white",
            fontsize=15, fontweight="bold", ha="center", va="top")
    ax.text(0.5, 0.87,
            "Enter each anchor's position (meters from your room corner).\n"
            "A1 is always the origin — keep it at 0, 0.",
            transform=ax.transAxes, color="#aaaaaa",
            fontsize=9, ha="center", va="top")

    for label, xpos in [("Anchor", 0.08), ("X (m)", 0.42), ("Y (m)", 0.68)]:
        ax.text(xpos, 0.76, label,
                transform=ax.transAxes, color="#888888",
                fontsize=9, va="top")

    box_specs = {
        1: (0.40, 0.66, 0.66, 0.66),
        2: (0.40, 0.54, 0.66, 0.54),
        3: (0.40, 0.42, 0.66, 0.42),
    }

    text_boxes = {}
    w, h = 0.20, 0.06

    for aid in (1, 2, 3):
        xl, yl, xr, yr = box_specs[aid]

        ax.text(0.08, yl + 0.03, f"Anchor {aid}",
                transform=ax.transAxes, color=ANCHOR_COLORS[aid],
                fontsize=11, va="center", fontweight="bold")

        ax_xbox = fig_cal.add_axes([xl, yl, w, h])
        tb_x = widgets.TextBox(ax_xbox, "", initial=str(DEFAULT_ANCHORS[aid][0]),
                               color="#16213e", hovercolor="#1e2d4a",
                               label_pad=0.01)
        tb_x.label.set_color("white")
        tb_x.text_disp.set_color("white")

        ax_ybox = fig_cal.add_axes([xr, yr, w, h])
        tb_y = widgets.TextBox(ax_ybox, "", initial=str(DEFAULT_ANCHORS[aid][1]),
                               color="#16213e", hovercolor="#1e2d4a",
                               label_pad=0.01)
        tb_y.label.set_color("white")
        tb_y.text_disp.set_color("white")

        text_boxes[aid] = (tb_x, tb_y)

    ax.axhline(0.35, color="#333355", linewidth=0.8, xmin=0.05, xmax=0.95)

    ax_preview = fig_cal.add_axes([0.1, 0.09, 0.80, 0.22])
    ax_preview.set_facecolor("#16213e")
    ax_preview.tick_params(colors="#555566", labelsize=7)
    for spine in ax_preview.spines.values():
        spine.set_edgecolor("#333355")
    ax_preview.set_title("Anchor layout preview", color="#888888",
                          fontsize=8, pad=4)
    preview_dots = {}
    preview_labels = {}
    for aid in (1, 2, 3):
        x, y = DEFAULT_ANCHORS[aid]
        dot, = ax_preview.plot(x, y, "^", markersize=10,
                               color=ANCHOR_COLORS[aid],
                               markeredgecolor="white", markeredgewidth=0.8)
        lbl  = ax_preview.annotate(f" A{aid}", (x, y),
                                   color=ANCHOR_COLORS[aid], fontsize=7)
        preview_dots[aid]   = dot
        preview_labels[aid] = lbl
    ax_preview.set_xlim(-1, 11)
    ax_preview.set_ylim(-1, 11)
    ax_preview.grid(True, color="#2a2a4a", linewidth=0.4)

    result = {"started": False}

    def refresh_preview(_=None):
        for aid in (1, 2, 3):
            try:
                x = float(text_boxes[aid][0].text)
                y = float(text_boxes[aid][1].text)
                preview_dots[aid].set_data([x], [y])
                preview_labels[aid].set_position((x, y))
            except ValueError:
                pass
        fig_cal.canvas.draw_idle()

    for aid in (1, 2, 3):
        text_boxes[aid][0].on_submit(refresh_preview)
        text_boxes[aid][1].on_submit(refresh_preview)

    ax_btn = fig_cal.add_axes([0.35, 0.01, 0.30, 0.07])
    btn_start = widgets.Button(ax_btn, "▶  Start Visualizer",
                               color="#1a6b3a", hovercolor="#218a4a")
    btn_start.label.set_color("white")
    btn_start.label.set_fontsize(10)

    def on_start(_):
        ok = True
        for aid in (1, 2, 3):
            try:
                x = float(text_boxes[aid][0].text)
                y = float(text_boxes[aid][1].text)
                ANCHOR_POSITIONS[aid] = (x, y)
            except ValueError:
                print(f"[Calibration] Invalid value for Anchor {aid} — check input")
                ok = False
        if ok:
            result["started"] = True
            plt.close(fig_cal)

    btn_start.on_clicked(on_start)

    plt.show()
    return result["started"]


# ─── Live plot ────────────────────────────────────────────────────────────────

def show_visualizer():
    _ax = [p[0] for p in ANCHOR_POSITIONS.values()]
    _ay = [p[1] for p in ANCHOR_POSITIONS.values()]

    # Fixed room bounds — never change during runtime
    X_MIN = min(_ax) - PAD
    X_MAX = max(_ax) + PAD
    Y_MIN = min(_ay) - PAD
    Y_MAX = max(_ay) + PAD
    ROOM_XLIM = (X_MIN, X_MAX)
    ROOM_YLIM = (Y_MIN, Y_MAX)

    fig, ax = plt.subplots(figsize=(9, 7))
    fig.patch.set_facecolor("#1a1a2e")
    fig.canvas.manager.set_window_title("UWB Tag — Live Position")
    ax.set_facecolor("#16213e")
    ax.set_xlim(*ROOM_XLIM)
    ax.set_ylim(*ROOM_YLIM)
    ax.set_xlabel("X (meters)", color="white")
    ax.set_ylabel("Y (meters)", color="white")
    ax.tick_params(colors="white")
    ax.set_title("UWB Tag — Live Position", color="white", fontsize=14, pad=10)
    for spine in ax.spines.values():
        spine.set_edgecolor("#444")
    ax.grid(True, color="#2a2a4a", linewidth=0.5)

    # Draw room boundary rectangle
    room_w = max(_ax) - min(_ax)
    room_h = max(_ay) - min(_ay)
    room_rect = plt.Rectangle(
        (min(_ax), min(_ay)), room_w, room_h,
        linewidth=1.5, edgecolor="#4a4a8a", facecolor="#1c2340",
        linestyle="-", zorder=1
    )
    ax.add_patch(room_rect)

    # Static anchors
    for aid, (ax_, ay_) in ANCHOR_POSITIONS.items():
        ax.plot(ax_, ay_, "^", markersize=15, color=ANCHOR_COLORS[aid],
                markeredgecolor="white", markeredgewidth=1.2, zorder=5)
        ax.annotate(f"  A{aid}  ({ax_:.2f}, {ay_:.2f} m)",
                    (ax_, ay_), color=ANCHOR_COLORS[aid], fontsize=9, zorder=6)

    trail_line, = ax.plot([], [], "-", color=TAG_COLOR, alpha=0.35,
                          linewidth=2, zorder=3)
    tag_dot,    = ax.plot([], [], "o", color=TAG_COLOR, markersize=14,
                          markeredgecolor="white", markeredgewidth=1.5, zorder=10)
    tag_label   = ax.annotate("", xy=(0, 0), color="white", fontsize=9,
                               xytext=(12, 6), textcoords="offset points", zorder=11)

    circles = {}
    for aid in (1, 2, 3):
        c = plt.Circle(ANCHOR_POSITIONS[aid], 0, fill=False,
                       color=ANCHOR_COLORS[aid], linestyle="--",
                       linewidth=1.0, alpha=0.4, zorder=2)
        ax.add_patch(c)
        circles[aid] = c

    status = ax.text(0.02, 0.97, "Waiting for UDP packets…",
                     transform=ax.transAxes, color="#aaaaaa",
                     fontsize=9, va="top", family="monospace")

    patches = [mpatches.Patch(color=ANCHOR_COLORS[i], label=f"Anchor {i}") for i in (1, 2, 3)]
    patches.append(mpatches.Patch(color=TAG_COLOR, label="Tag"))
    ax.legend(handles=patches, loc="lower right",
              facecolor="#1a1a2e", edgecolor="#444",
              labelcolor="white", fontsize=9)

    plt.tight_layout()

    def update(_frame):
        with lock:
            pos     = state["smoothed_pos"]
            raw_pos = state["tag_pos"]
            dists   = dict(state["distances"])
            trail   = list(state["trail"])
            age     = time.time() - state["last_update"]
            packets = state["packets"]

        if len(trail) > 1:
            xs, ys = zip(*trail)
            trail_line.set_data(xs, ys)
        else:
            trail_line.set_data([], [])

        if pos:
            tag_dot.set_data([pos[0]], [pos[1]])
            tag_dot.set_alpha(1.0 if age < 2.0 else max(0.2, 1.0 - (age - 2) * 0.15))
            tag_label.set_position((pos[0], pos[1]))
            tag_label.set_text(f"  ({pos[0]:.2f}, {pos[1]:.2f}) m")
        else:
            tag_dot.set_data([], [])
            tag_label.set_text("")

        # Always lock axes to room bounds — never auto-expand
        ax.set_xlim(*ROOM_XLIM)
        ax.set_ylim(*ROOM_YLIM)

        for aid in (1, 2, 3):
            d = dists.get(aid)
            circles[aid].set_radius(d if d and d > 0 else 0)

        d1s = f"{dists[1]:.2f}" if dists[1] else "---"
        d2s = f"{dists[2]:.2f}" if dists[2] else "---"
        d3s = f"{dists[3]:.2f}" if dists[3] else "---"
        pos_str = f"({pos[0]:.2f}, {pos[1]:.2f}) m" if pos else "computing…"
        raw_str = f"({raw_pos[0]:.2f}, {raw_pos[1]:.2f}) m" if raw_pos else "---"
        status.set_text(
            f"d1={d1s}m   d2={d2s}m   d3={d3s}m\n"
            f"Position (smooth) : {pos_str}\n"
            f"Position (raw)    : {raw_str}\n"
            f"Packets: {packets}    Last update: {age:.1f}s ago"
        )

        return trail_line, tag_dot, tag_label, status, *circles.values()

    ani = FuncAnimation(fig, update, interval=UPDATE_MS,
                        blit=True, cache_frame_data=False)
    plt.show()
    print("\n[Done] Window closed.")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    started = show_calibration()
    if not started:
        print("Calibration cancelled — exiting.")
        return

    print("\n=== Calibration done ===")
    for aid, pos in ANCHOR_POSITIONS.items():
        print(f"  Anchor {aid}: ({pos[0]:.2f}, {pos[1]:.2f}) m")

    t = threading.Thread(target=udp_listener, daemon=True)
    t.start()

    show_visualizer()


if __name__ == "__main__":
    main()