"""Procedural Tkinter HUD graphics used by the JARVIS visualizer."""

from __future__ import annotations

import math
import tkinter as tk


GRID = "#10264a"
GRID_BRIGHT = "#1b4778"
CYAN = "#61caff"
BLUE = "#4c84ff"
GREEN = "#53e0a0"
RED = "#ff627f"
MUTED_DARK = "#627d9b"
VIOLET = "#526ce0"
TEXT = "#dbeaff"
LIGHT = "#c5e7ff"
MUTED = "#8ea9ca"


def _polyline(points: list[tuple[float, float]]) -> list[float]:
    return [coordinate for point in points for coordinate in point]


def _draw_globe(canvas: tk.Canvas, cx: float, cy: float, radius: float, phase: float) -> None:
    """Draw a layered, rotating-looking Earth hologram with native Canvas shapes."""
    shades = ("#0b1d3d", "#102b54", "#153765", "#1a477a", "#205991", "#2671a8", "#2e85bd")
    for index, shade in enumerate(shades):
        scale = 1.0 - index * 0.075
        offset = radius * 0.18 * (1.0 - scale)
        canvas.create_oval(
            cx - radius * scale - offset, cy - radius * scale - offset,
            cx + radius * scale - offset, cy + radius * scale - offset,
            fill=shade, outline="",
        )
    land = "#347fb2"
    edge = "#79d0ff"
    for shape in (
        ((-.72, -.26), (-.58, -.58), (-.24, -.50), (-.10, -.30), (-.28, -.12), (-.38, .16), (-.61, .12)),
        ((-.28, .12), (-.08, .18), (-.12, .42), (-.23, .73), (-.37, .39)),
        ((-.05, -.47), (.25, -.55), (.52, -.43), (.76, -.19), (.59, -.04), (.31, -.10), (.20, .08), (.02, -.04)),
        ((.11, .03), (.39, .04), (.33, .27), (.19, .53), (.06, .31)),
        ((.45, .22), (.66, .18), (.73, .29), (.60, .39), (.47, .34)),
    ):
        points = [coordinate for x, y in shape for coordinate in (cx + x * radius, cy + y * radius)]
        canvas.create_polygon(points, fill=land, outline=edge, width=1, smooth=True)
    for width_scale, height_scale in ((.88, .30), (.88, .55)):
        canvas.create_oval(cx - radius * width_scale, cy - radius * height_scale,
                           cx + radius * width_scale, cy + radius * height_scale,
                           outline="#49bde1", width=1, dash=(3, 4))
    meridian = .42 + .12 * math.sin(phase / 13)
    canvas.create_oval(cx - radius * meridian, cy - radius * .95,
                       cx + radius * meridian, cy + radius * .95,
                       outline="#55cceb", width=1, dash=(3, 5))
    canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                       outline="#94f3ff", width=2)
    core_font = max(12, int(radius * .30))
    canvas.create_text(cx + 1, cy + radius * .12 + 1, text="JARVIS", fill="#06142b",
                       font=("Segoe UI", core_font, "bold"))
    canvas.create_text(cx, cy + radius * .12, text="JARVIS", fill="#e5fbff",
                       font=("Segoe UI", core_font, "bold"))


def draw_hud(
    canvas: tk.Canvas,
    *,
    phase: int,
    center_y: float,
    core_radius: float,
    mode: str = "READY",
    logo: tk.PhotoImage | None = None,
    cpu_load: float | None = None,
    cpu_history: tuple[float, ...] = (),
    animated: bool = True,
    details: bool = False,
    hero: bool = False,
    quality: str = "Balanced",
) -> None:
    """Draw a responsive, state-aware HUD using native Canvas primitives."""
    canvas.delete("all")
    width = max(canvas.winfo_width(), 360)
    height = max(canvas.winfo_height(), 120)
    cx = width / 2
    cy = center_y
    ui_scale = min(2.25, max(1.0, width / 1360))
    tick = phase / 12 if animated else 0.0
    radians = math.radians(tick * 3)
    color = (
        GREEN if mode == "LISTENING" else
        BLUE if mode == "THINKING" else
        VIOLET if mode == "SPEAKING" else
        RED if mode == "ERROR" else
        MUTED_DARK if mode == "OFFLINE" else CYAN
    )

    # A small procedural city gives the home dashboard depth without external
    # rendering dependencies. Building heights and window positions are fixed.
    if details or hero:
        horizon = height * 0.72
        skyline = (
            (0.00, .18, .25), (.07, .08, .55), (.13, .12, .32),
            (.23, .09, .48), (.31, .12, .28), (.40, .10, .42),
            (.50, .13, .30), (.60, .10, .50), (.70, .12, .33),
            (.80, .08, .57), (.88, .12, .34), (.96, .12, .48),
        )
        for index, (fraction, building_width, building_height) in enumerate(skyline):
            left = fraction * width
            right = min(width, left + building_width * width)
            top = horizon - building_height * height * .25
            canvas.create_rectangle(left, top, right, height, fill="#0b1c3a", outline="#193b68")
            for column in range(2):
                wx = left + (column + .55) * (right - left) / 2
                for row in range(3):
                    wy = top + 8 + row * 10
                    if wy < height - 12 and (row + column + index) % 3 != 0:
                        canvas.create_rectangle(wx, wy, wx + 2, wy + 4, fill="#17608a", outline="")
        canvas.create_line(0, horizon, width, horizon, fill="#17608a", width=1)
        for rx, ry in ((width * .38, height * .075), (width * .26, height * .045)):
            canvas.create_oval(cx - rx, horizon - ry, cx + rx, horizon + ry,
                               outline="#12496a", width=1)
        if hero:
            floor_y = height * .89
            for rx, ry, stroke, thickness in (
                (width * .39, height * .075, "#12527a", 2),
                (width * .30, height * .055, "#1b83ad", 2),
                (width * .20, height * .035, "#38c9ee", 1),
            ):
                canvas.create_oval(cx - rx, floor_y - ry, cx + rx, floor_y + ry,
                                   outline=stroke, width=thickness)
            for offset in (-.28, -.15, .15, .28):
                canvas.create_line(cx + width * offset, floor_y,
                                   cx + width * offset * .38, horizon,
                                   fill="#123c5c", width=1)

    # Blueprint grid with brighter registration marks at the canvas edges.
    grid_x = max(30, int(width / 72))
    grid_y = max(24, int(height / 34))
    for x in range(15, width, grid_x):
        canvas.create_line(x, 0, x, height, fill=GRID, width=1)
    for y in range(12, height, grid_y):
        canvas.create_line(0, y, width, y, fill=GRID, width=1)
    if hero:
        star_count = 54 if quality == "High" else 36 if quality == "Balanced" else 22
        for index in range(star_count):
            star_x = (index * 173 + 41) % width
            star_y = (index * 47 + 19) % max(1, int(height * .72))
            blink = (index % 4 == 0) and animated and (phase // 6) % 2 == 0
            star_color = "#61caff" if blink else "#4779a8"
            canvas.create_oval(star_x, star_y, star_x + 1.5, star_y + 1.5,
                               fill=star_color, outline="")
    corner = 12
    for x, direction in ((8, 1), (width - 8, -1)):
        for y, vertical in ((8, 1), (height - 8, -1)):
            canvas.create_line(x, y, x + direction * corner, y, fill=GRID_BRIGHT, width=1)
            canvas.create_line(x, y, x, y + vertical * corner, fill=GRID_BRIGHT, width=1)

    outer = core_radius * 1.62
    # Soft halo rings add depth without image filters or extra dependencies.
    for halo_radius, halo_color, halo_width in (
        (core_radius * 1.12, "#173765", max(4, int(8 * ui_scale))),
        (core_radius * 1.08, "#1c5285", max(2, int(3 * ui_scale))),
        (core_radius * 1.03, "#46aeea", 1),
    ):
        canvas.create_oval(
            cx - halo_radius, cy - halo_radius,
            cx + halo_radius, cy + halo_radius,
            outline=halo_color, width=halo_width,
        )

    # Rotating segmented rings and a fine dashed instrument ring.
    for radius, offset, extent, line, thickness in (
        (outer, -tick * 4, 40, color, 2),
        (outer, 105 + tick * 2.3, 58, CYAN, 1),
        (outer * 0.87, 35 - tick * 1.4, 72, "#3288c4", 1),
    ):
        for segment in range(3):
            start = offset + segment * 120
            canvas.create_arc(
                cx - radius, cy - radius, cx + radius, cy + radius,
                start=start, extent=extent, style="arc", outline=line,
                width=thickness,
            )
    canvas.create_oval(
        cx - outer * 0.76, cy - outer * 0.76,
        cx + outer * 0.76, cy + outer * 0.76,
        outline="#1e4f70", width=1, dash=(2, 5),
    )

    # Calibrated radial ticks, with larger marks every sixth division.
    tick_count = 24 if quality == "Low" else 80 if quality == "High" else 40
    for index in range(tick_count):
        angle = index * (math.tau / tick_count) - math.pi / 2 + radians * 0.3
        major = index % (6 if quality != "Low" else 4) == 0
        start_r = outer * (0.90 if major else 0.94)
        end_r = outer * 0.99
        canvas.create_line(
            cx + math.cos(angle) * start_r,
            cy + math.sin(angle) * start_r,
            cx + math.cos(angle) * end_r,
            cy + math.sin(angle) * end_r,
            fill=CYAN if major else "#285477",
            width=2 if major else 1,
        )

    # Two tilted orbital tracks with moving probes.
    orbit_steps = 32 if quality == "Low" else 96 if quality == "High" else 48
    for index, (rx, ry, rotation, speed) in enumerate((
        (outer * 1.10, outer * 0.33, -24, 1.7),
        (outer * 0.38, outer * 1.04, 24, -1.2),
    )):
        theta = math.radians(rotation)
        points: list[tuple[float, float]] = []
        for step in range(orbit_steps + 1):
            angle = math.tau * step / orbit_steps
            px, py = rx * math.cos(angle), ry * math.sin(angle)
            points.append((cx + px * math.cos(theta) - py * math.sin(theta),
                           cy + px * math.sin(theta) + py * math.cos(theta)))
        canvas.create_line(*_polyline(points), fill="#1b4667", width=1, smooth=True)
        probe_angle = radians * speed + index * 2.4
        px, py = rx * math.cos(probe_angle), ry * math.sin(probe_angle)
        probe_x = cx + px * math.cos(theta) - py * math.sin(theta)
        probe_y = cy + px * math.sin(theta) + py * math.cos(theta)
        probe_size = 3 if index == 0 else 2
        canvas.create_oval(
            probe_x - probe_size * 2.5, probe_y - probe_size * 2.5,
            probe_x + probe_size * 2.5, probe_y + probe_size * 2.5,
            fill="#1e688f", outline="",
        )
        canvas.create_oval(
            probe_x - probe_size * 1.5, probe_y - probe_size * 1.5,
            probe_x + probe_size * 1.5, probe_y + probe_size * 1.5,
            fill="#2589bc", outline="",
        )
        canvas.create_oval(
            probe_x - probe_size * 0.65, probe_y - probe_size * 0.65,
            probe_x + probe_size * 0.65, probe_y + probe_size * 0.65,
            fill=color if index == 0 else LIGHT, outline="",
        )

    # Four pulsing signal nodes and a central crosshair.
    pulse = 1.0 + (0.35 * math.sin(tick / 2) if animated else 0.0)
    for index, angle in enumerate((0.0, math.pi / 2, math.pi, math.pi * 1.5)):
        node_x = cx + math.cos(angle + radians * 0.25) * outer * 1.13
        node_y = cy + math.sin(angle + radians * 0.25) * outer * 1.13
        size = (3.1 if index % 2 == 0 else 2.1) * pulse
        canvas.create_oval(node_x - size, node_y - size, node_x + size, node_y + size,
                           fill=color if index == 0 else "#2589bc", outline="")
        if index == 0:
            canvas.create_oval(node_x - size * 2.6, node_y - size * 2.6,
                               node_x + size * 2.6, node_y + size * 2.6,
                               outline="#45bfe9", width=1)
    canvas.create_line(cx - core_radius * 1.18, cy, cx - core_radius * 0.98, cy, fill="#228bbd")
    canvas.create_line(cx + core_radius * 0.98, cy, cx + core_radius * 1.18, cy, fill="#228bbd")
    canvas.create_line(cx, cy - core_radius * 1.18, cx, cy - core_radius * 0.98, fill="#228bbd")
    canvas.create_line(cx, cy + core_radius * 0.98, cx, cy + core_radius * 1.18, fill="#228bbd")

    # The existing JARVIS artwork sits above these rings as the visual core.
    canvas.create_oval(
        cx - core_radius, cy - core_radius,
        cx + core_radius, cy + core_radius,
        fill="#0b1c3a", outline=color, width=2,
    )
    canvas.create_oval(
        cx - core_radius * 0.84, cy - core_radius * 0.84,
        cx + core_radius * 0.84, cy + core_radius * 0.84,
        outline="#267da8", width=1,
    )
    canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill=TEXT, outline="")
    if hero:
        _draw_globe(canvas, cx, cy, core_radius * .87, tick)
    elif logo is not None:
        canvas.create_image(cx, cy, image=logo, anchor="center")

    # A narrow, triple-pass light sweep glides across the JARVIS core.
    sweep_y = cy + math.sin(tick * 0.35) * core_radius * 0.56 if animated else cy
    sweep_left, sweep_right = cx - core_radius * 0.58, cx + core_radius * 0.58
    canvas.create_line(sweep_left, sweep_y, sweep_right, sweep_y,
                       fill="#174b6a", width=8, capstyle="round")
    canvas.create_line(sweep_left, sweep_y, sweep_right, sweep_y,
                       fill="#43c8ef", width=3, capstyle="round")
    canvas.create_line(sweep_left, sweep_y, sweep_right, sweep_y,
                       fill=LIGHT, width=1, capstyle="round")

    # Live load trace along the lower rail; use real CPU data when available.
    rail_y = height - (20 if details else 10)
    rail_left, rail_right = width * 0.16, width * 0.84
    canvas.create_line(rail_left, rail_y, rail_right, rail_y, fill="#173751", width=1)
    samples = tuple(max(0.0, min(100.0, value)) for value in cpu_history[-48:])
    if len(samples) == 1:
        samples = (samples[0], samples[0])
    if len(samples) > 1:
        trace = []
        for index, sample in enumerate(samples):
            x = rail_left + (rail_right - rail_left) * index / (len(samples) - 1)
            y = rail_y - (sample / 100.0) * (height * .16)
            trace.extend((x, y))
        canvas.create_line(*trace, fill=color, width=2, smooth=True)
        if animated:
            last_x, last_y = trace[-2:]
            pulse_size = 2.2 + .8 * math.sin(tick / 2)
            canvas.create_oval(last_x - pulse_size, last_y - pulse_size,
                               last_x + pulse_size, last_y + pulse_size,
                               fill=LIGHT, outline=color)
    if details:
        label_y = min(height - 42, cy + outer + 11)
        canvas.create_text(16, label_y, text="J.A.R.V.I.S. / CORE 01", anchor="w",
                           fill=TEXT, font=("Segoe UI", 8, "bold"))
        load_label = f"CPU {cpu_load:02.0f}%" if cpu_load is not None else "CPU —"
        canvas.create_text(width - 16, label_y, text=f"{load_label}  ·  {mode}", anchor="e",
                           fill=MUTED, font=("Segoe UI", 8, "bold"))
    else:
        canvas.create_text(rail_left - 5, rail_y, text="CPU", anchor="e",
                           fill=MUTED, font=("Segoe UI", 7, "bold"))
