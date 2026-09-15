"""
English-labelled versions of the weekly report diagrams.

Mirrors plot_week_diagrams.py one figure for one. The drawing helpers are imported from
that module so both languages stay visually identical -- only the wording differs.

OUTPUT
    paper/weekly_reports_en/figures_en/

USAGE
    python scripts/report/plot_week_diagrams_en.py
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch

import plot_week_diagrams as vi
from plot_week_diagrams import (C_ACTIVE, C_BAD, C_GOOD, C_GOOD_BG, C_IDLE, C_INK,
                                C_STATIC_WARM, C_WARN_BG, arrow, blank_ax, box)

OUT = "paper/weekly_reports_en/figures_en"
plt.rcParams.update({"figure.dpi": 130, "font.size": 10.5})


def fig_project_pipeline():
    fig, ax = blank_ax((11, 3.5))
    stages = [("1. Collect\nthe data", C_ACTIVE, "WEEKS 5-8"),
              ("2. Clean\n& label", C_IDLE, "Weeks 8-9"),
              ("3. Train the\nAI model", C_IDLE, "Weeks 9, 12"),
              ("4. Analyse\n& report", C_IDLE, "Weeks 10-13")]
    w, h, gap, x0 = 2.05, 2.1, 0.55, 0.5
    for i, (label, colour, when) in enumerate(stages):
        x = x0 + i * (w + gap)
        box(ax, x, 4.6, w, h, label, colour, fontsize=11, weight="bold",
            textcolor="white" if colour == C_ACTIVE else "#41506B")
        ax.text(x + w / 2, 4.25, when, ha="center", va="top", fontsize=9,
                color=C_ACTIVE if colour == C_ACTIVE else "#8A98AB",
                fontweight="bold" if colour == C_ACTIVE else "normal")
        if i < 3:
            arrow(ax, x + w + 0.08, 5.65, x + w + gap - 0.08, 5.65, color="#8A98AB")
    ax.text(5.0, 8.6, "Week 5 sits at the very first step of the project",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)
    ax.text(5.0, 7.85, "Without trustworthy data, none of the three later steps can happen",
            ha="center", fontsize=10.5, color="#55606D")
    ax.add_patch(FancyBboxPatch((0.5, 1.5), 9.05, 2.0,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor="#F4F7FA", edgecolor="#D6DEE9", linewidth=1.2))
    ax.text(5.0, 2.5, "Each participant comes in for a measurement session ONCE.\n"
                      "A failed session means that person's data is lost for good.",
            ha="center", va="center", fontsize=10.5, color="#41506B", linespacing=1.6)
    fig.tight_layout(); p = f"{OUT}/week05_project_pipeline.png"
    fig.savefig(p); plt.close(fig); return p


def fig_flash_vs_wireless():
    fig, ax = blank_ax((11, 5.2))
    ax.text(5.0, 9.5, "Where does the data go once the sensor reads it?",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)
    box(ax, 0.35, 5.1, 1.9, 1.5, "Wrist\ndevice", C_INK, fontsize=10.5, weight="bold")

    ax.add_patch(FancyBboxPatch((2.9, 6.35), 6.75, 2.35,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor=C_GOOD_BG, edgecolor=C_GOOD, linewidth=1.5))
    ax.text(3.15, 8.35, "MAIN PATH - always runs", fontsize=9.5, fontweight="bold",
            color=C_GOOD, va="center")
    box(ax, 3.15, 6.7, 2.5, 1.25, "Write to memory\ninside the device", C_GOOD, fontsize=10)
    box(ax, 6.9, 6.7, 2.5, 1.25, "After the session,\nplug in and collect", C_GOOD, fontsize=10)
    arrow(ax, 5.75, 7.32, 6.8, 7.32, color=C_GOOD)
    arrow(ax, 2.3, 6.1, 3.1, 7.0, color=C_GOOD)

    ax.add_patch(FancyBboxPatch((2.9, 3.15), 6.75, 2.35,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor="#F4F7FA", edgecolor="#B8C4D6", linewidth=1.5))
    ax.text(3.15, 5.15, "SIDE PATH - nice to have, safe to lose", fontsize=9.5,
            fontweight="bold", color="#6B7785", va="center")
    box(ax, 3.15, 3.5, 2.5, 1.25, "Send over\nBluetooth", "#8A98AB", fontsize=10)
    box(ax, 6.9, 3.5, 2.5, 1.25, "Watch live\non a laptop", "#8A98AB", fontsize=10)
    arrow(ax, 5.75, 4.12, 6.8, 4.12, color="#8A98AB", ls=(0, (4, 2)))
    arrow(ax, 2.3, 5.6, 3.1, 4.4, color="#8A98AB", ls=(0, (4, 2)))
    ax.text(6.3, 2.72, "Bluetooth drops out from time to time", ha="center", fontsize=9,
            color=C_BAD, style="italic")

    ax.add_patch(FancyBboxPatch((0.35, 0.35), 9.3, 1.75,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor=C_WARN_BG, edgecolor=C_BAD, linewidth=1.3))
    ax.text(5.0, 1.22, "If Bluetooth were the only place data was stored, one dropout\n"
                       "mid-session would lose that participant's data entirely.",
            ha="center", va="center", fontsize=10.5, color="#7A2E28", linespacing=1.6)
    fig.tight_layout(); p = f"{OUT}/week05_flash_vs_wireless.png"
    fig.savefig(p); plt.close(fig); return p


def fig_transport_pivot():
    fig, ax = blank_ax((11, 4.2))
    ax.text(5.0, 9.4, "Changing how the data gets to the laptop",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)
    ax.text(0.35, 7.9, "Original plan", fontsize=10.5, fontweight="bold",
            color="#8A98AB", va="center")
    for lbl, x in [("Wrist\ndevice", 0.35), ("Middle machine\n(Jetson)", 3.6),
                   ("Laptop", 7.0)]:
        box(ax, x, 5.9, 2.4, 1.35, lbl, C_IDLE, fontsize=10, textcolor="#41506B")
    arrow(ax, 2.85, 6.57, 3.5, 6.57, color="#8A98AB")
    arrow(ax, 6.1, 6.57, 6.9, 6.57, color="#8A98AB")
    ax.text(4.8, 5.35, "networking software kept failing", ha="center", fontsize=9.5,
            color=C_BAD, style="italic")
    ax.plot([6.28, 6.72], [6.35, 6.79], color=C_BAD, lw=2.8, zorder=6)
    ax.plot([6.28, 6.72], [6.79, 6.35], color=C_BAD, lw=2.8, zorder=6)

    ax.text(0.35, 3.9, "Changed to", fontsize=10.5, fontweight="bold", color=C_GOOD,
            va="center")
    box(ax, 0.35, 1.9, 2.4, 1.35, "Wrist\ndevice", C_INK, fontsize=10)
    box(ax, 7.0, 1.9, 2.4, 1.35, "Laptop", C_ACTIVE, fontsize=10)
    arrow(ax, 2.85, 2.57, 6.9, 2.57, color=C_GOOD, lw=2.2)
    ax.text(4.9, 3.0, "Bluetooth - direct, no middle machine", ha="center", fontsize=10,
            color=C_GOOD, fontweight="bold")
    ax.text(4.9, 1.45, "already proven stable", ha="center", fontsize=9.5,
            color="#55606D", style="italic")
    fig.tight_layout(); p = f"{OUT}/week05_transport_pivot.png"
    fig.savefig(p); plt.close(fig); return p


def fig_protocol_timeline():
    fig, ax = blank_ax((11, 4.0))
    ax.text(5.0, 9.4, "What one measurement session looks like",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)
    x = 1.75
    box(ax, 0.35, 5.6, 1.25, 1.5, "Get ready\n15 sec", "#8A98AB", fontsize=9.5)
    for a in ["Lying", "Sitting", "Standing", "Walking", "Running"]:
        box(ax, x, 5.6, 1.42, 1.5, f"{a}\n90 sec", C_ACTIVE, fontsize=9.5)
        x += 1.42
        if a != "Running":
            ax.add_patch(FancyBboxPatch((x, 5.95), 0.2, 0.8,
                                        boxstyle="round,pad=0.005,rounding_size=0.01",
                                        facecolor="#E3E9F1", edgecolor="#E3E9F1"))
            x += 0.2
    ax.text(5.6, 5.15, "the pale gaps are changeover time - excluded from all analysis",
            ha="center", fontsize=9, color="#6B7785", style="italic")

    ax.add_patch(FancyBboxPatch((0.35, 2.7), 4.4, 1.95,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor=C_WARN_BG, edgecolor=C_BAD, linewidth=1.3))
    ax.text(2.55, 4.25, "Before the fix", ha="center", fontsize=10, fontweight="bold",
            color=C_BAD)
    ax.text(2.55, 3.4, "Recording started at power-on.\nThe person had not lain down yet,\n"
                       "but the label already said \"lying\".",
            ha="center", va="center", fontsize=9.8, color="#7A2E28", linespacing=1.5)

    ax.add_patch(FancyBboxPatch((5.25, 2.7), 4.4, 1.95,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor=C_GOOD_BG, edgecolor=C_GOOD, linewidth=1.3))
    ax.text(7.45, 4.25, "After the fix", ha="center", fontsize=10, fontweight="bold",
            color=C_GOOD)
    ax.text(7.45, 3.4, "15 seconds to get into position,\nand the laptop plays a sound\n"
                       "each time it is time to change.",
            ha="center", va="center", fontsize=9.8, color="#1E5C33", linespacing=1.5)

    ax.text(5.0, 1.55, "A label that is wrong in the first seconds stays wrong forever - "
                       "the AI learns from labels, not from the truth.",
            ha="center", fontsize=10, color="#41506B", style="italic")
    fig.tight_layout(); p = f"{OUT}/week06_protocol_timeline.png"
    fig.savefig(p); plt.close(fig); return p


def fig_two_channels():
    fig, ax = blank_ax((11, 4.0))
    ax.text(5.0, 9.4, "Why a second sensor was added at the fingertip",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)
    box(ax, 0.5, 5.4, 3.9, 2.5,
        "SENSOR 1 - WRIST\n\nThis is what the real product uses.\n"
        "But arm movement disturbs it badly.", C_ACTIVE, fontsize=10)
    box(ax, 5.6, 5.4, 3.9, 2.5,
        "SENSOR 2 - FINGERTIP\n\nResearch only, not part of the\n"
        "product. Far less disturbed.", C_GOOD, fontsize=10)
    arrow(ax, 2.45, 5.25, 3.9, 3.9, color=C_ACTIVE)
    arrow(ax, 7.55, 5.25, 6.1, 3.9, color=C_GOOD)
    box(ax, 3.4, 2.5, 3.2, 1.3, "Compare the two\nagainst each other", C_INK,
        fontsize=10.5, weight="bold")
    ax.text(5.0, 1.65, "Sensor 2 acts as the \"right answer\" used to mark sensor 1.\n"
                       "Without an answer key there is no way to tell which filter is better.",
            ha="center", fontsize=10.2, color="#41506B", linespacing=1.6)
    fig.tight_layout(); p = f"{OUT}/week07_two_channels.png"
    fig.savefig(p); plt.close(fig); return p


def fig_quality_gate():
    fig, ax = blank_ax((11, 3.8))
    ax.text(5.0, 9.3, "Filtering out sessions where nobody wore the device",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)
    box(ax, 0.4, 5.2, 2.3, 1.9, "21 recorded\nsessions", "#8A98AB", fontsize=10.5,
        weight="bold")
    box(ax, 3.5, 5.2, 3.0, 1.9,
        "Automatic rule:\nrunning must shake at least\n3x more than lying still",
        C_INK, fontsize=9.8)
    arrow(ax, 2.75, 6.15, 3.45, 6.15)
    box(ax, 7.35, 6.55, 2.3, 1.15, "15 sessions\nVALID", C_GOOD, fontsize=10.5,
        weight="bold")
    box(ax, 7.35, 4.75, 2.3, 1.15, "6 sessions\nREJECTED", C_BAD, fontsize=10.5,
        weight="bold")
    arrow(ax, 6.55, 6.4, 7.3, 7.1, color=C_GOOD)
    arrow(ax, 6.55, 5.9, 7.3, 5.3, color=C_BAD)
    ax.add_patch(FancyBboxPatch((0.4, 1.1), 9.25, 3.05,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor=C_WARN_BG, edgecolor=C_BAD, linewidth=1.3))
    ax.text(5.0, 2.6,
            "The 6 rejected sessions were equipment tests - the device lay on a table, nobody wore it.\n"
            "They passed EVERY automatic check: right number of labels, right number of rows, no errors.\n"
            "They only showed up when someone plotted the signal and asked: why is \"running\" as flat as lying?",
            ha="center", va="center", fontsize=10, color="#7A2E28", linespacing=1.7)
    fig.tight_layout(); p = f"{OUT}/week08_quality_gate.png"
    fig.savefig(p); plt.close(fig); return p


def fig_logocv():
    fig, ax = blank_ax((11, 5.0))
    ax.text(5.0, 9.5, "How the AI is marked: always tested on someone it has never seen",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)
    for r, (label, held) in enumerate([("Round 1", 0), ("Round 2", 1), ("Round 18", 17)]):
        y = 7.2 - r * 1.55
        ax.text(0.35, y + 0.42, label, fontsize=10, fontweight="bold", color=C_INK,
                va="center")
        for i in range(18):
            ax.add_patch(FancyBboxPatch((1.7 + i * 0.45, y), 0.36, 0.85,
                                        boxstyle="round,pad=0.006,rounding_size=0.012",
                                        facecolor=C_BAD if i == held else C_IDLE,
                                        edgecolor="none"))
        if r == 2:
            ax.text(1.7 + 8 * 0.45, y + 1.35, ". . .   repeated for all 18 rounds   . . .",
                    ha="center", fontsize=9.5, color="#6B7785", style="italic")
    ax.add_patch(FancyBboxPatch((1.7, 2.35), 1.0, 0.55,
                                boxstyle="round,pad=0.006,rounding_size=0.012",
                                facecolor=C_IDLE, edgecolor="none"))
    ax.text(2.9, 2.62, "17 people used to TEACH", fontsize=10, va="center", color="#41506B")
    ax.add_patch(FancyBboxPatch((6.0, 2.35), 1.0, 0.55,
                                boxstyle="round,pad=0.006,rounding_size=0.012",
                                facecolor=C_BAD, edgecolor="none"))
    ax.text(7.2, 2.62, "1 person used to MARK", fontsize=10, va="center", color="#41506B")
    ax.add_patch(FancyBboxPatch((0.35, 0.3), 9.3, 1.7,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor="#F4F7FA", edgecolor="#D6DEE9", linewidth=1.2))
    ax.text(5.0, 1.15, "If one person's data went into both the teaching and the marking set,\n"
                       "the AI could score well just by recognising them - a pretty but meaningless number.",
            ha="center", va="center", fontsize=10.2, color="#41506B", linespacing=1.6)
    fig.tight_layout(); p = f"{OUT}/week09_logocv.png"
    fig.savefig(p); plt.close(fig); return p


def fig_filter_setup():
    fig, ax = blank_ax((11, 4.0))
    ax.text(5.0, 9.4, "How the three filters were compared",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)
    box(ax, 0.35, 6.6, 2.5, 1.3, "Heart signal\nread at the wrist", C_ACTIVE, fontsize=9.8)
    box(ax, 0.35, 4.7, 2.5, 1.3, "Arm movement\n(motion sensor)", "#8A98AB", fontsize=9.8)
    for i, (name, y) in enumerate([("Method 1: NLMS", 7.3), ("Method 2: RLS", 6.0),
                                   ("Method 3: Wiener", 4.7)]):
        box(ax, 3.7, y - 0.45, 2.3, 0.95, name, C_INK, fontsize=9.8)
        arrow(ax, 2.95, 7.25 if i == 0 else (6.0 if i == 1 else 5.35), 3.65, y,
              color="#8A98AB")
    box(ax, 6.9, 5.7, 2.7, 1.6, "Compare against\nthe fingertip reading\n(the right answer)",
        C_GOOD, fontsize=9.8)
    for y in (7.3, 6.0, 4.7):
        arrow(ax, 6.05, y, 6.85, 6.5, color="#8A98AB")
    ax.add_patch(FancyBboxPatch((0.35, 1.3), 9.3, 2.75,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor="#F4F7FA", edgecolor="#D6DEE9", linewidth=1.2))
    ax.text(5.0, 3.35, "What all three have in common", ha="center", fontsize=10.5,
            fontweight="bold", color=C_INK)
    ax.text(5.0, 2.3, "The wrist signal = the real heartbeat + noise from arm movement.\n"
                      "All three use the motion sensor to guess the noise, then SUBTRACT it.\n"
                      "They differ only in how they make that guess.",
            ha="center", va="center", fontsize=10, color="#41506B", linespacing=1.7)
    fig.tight_layout(); p = f"{OUT}/week10_filter_setup.png"
    fig.savefig(p); plt.close(fig); return p


def fig_train_to_device():
    fig, ax = blank_ax((11, 3.6))
    ax.text(5.0, 9.2, "Getting the trained AI from a laptop onto the wrist chip",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)
    x = 0.7
    for i, lbl in enumerate(["Train it\non a laptop", "Translate to code\nthe chip reads",
                             "Load it onto\nthe device"]):
        box(ax, x, 5.3, 2.5, 1.7, lbl, C_ACTIVE, fontsize=10)
        if i < 2:
            arrow(ax, x + 2.55, 6.15, x + 3.15, 6.15)
        x += 3.15
    ax.plot([6.3, 6.3], [5.1, 4.35], color=C_BAD, lw=1.6, ls=(0, (3, 2)))
    ax.text(6.3, 4.05, "the missed step", ha="center", fontsize=9.5, color=C_BAD,
            fontweight="bold")
    ax.add_patch(FancyBboxPatch((0.4, 0.9), 9.2, 2.85,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor=C_WARN_BG, edgecolor=C_BAD, linewidth=1.3))
    ax.text(5.0, 3.05, "The bug found this week", ha="center", fontsize=10.5,
            fontweight="bold", color=C_BAD)
    ax.text(5.0, 1.95, "The new model had been translated to chip code, but the program on the\n"
                       "device was still calling the OLD model - nobody had connected the two.\n"
                       "Each piece was correct on its own; only the wiring was missing.",
            ha="center", va="center", fontsize=10, color="#7A2E28", linespacing=1.7)
    fig.tight_layout(); p = f"{OUT}/week11_train_to_device.png"
    fig.savefig(p); plt.close(fig); return p


def fig_regroup():
    fig, ax = blank_ax((11, 3.8))
    ax.text(5.0, 9.3, "Merging the three still postures into one group",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)
    ax.text(2.0, 8.1, "5 classes - 54.8% accuracy", ha="center", fontsize=10.5,
            fontweight="bold", color=C_BAD)
    for i, a in enumerate(["Lying", "Sitting", "Standing", "Walking", "Running"]):
        box(ax, 0.5, 6.6 - i * 1.15, 3.0, 0.95, a,
            C_STATIC_WARM if i < 3 else C_ACTIVE, fontsize=10)
    ax.text(8.0, 8.1, "3 classes - 85.3% accuracy", ha="center", fontsize=10.5,
            fontweight="bold", color=C_GOOD)
    box(ax, 6.5, 4.3, 3.0, 3.25, "AT REST\n(all three still postures)", C_STATIC_WARM,
        fontsize=10.5, weight="bold")
    box(ax, 6.5, 3.0, 3.0, 0.95, "Walking", C_ACTIVE, fontsize=10)
    box(ax, 6.5, 1.85, 3.0, 0.95, "Running", C_ACTIVE, fontsize=10)
    for i in range(3):
        arrow(ax, 3.6, 7.05 - i * 1.15, 6.4, 5.9, color=C_STATIC_WARM, lw=1.4)
    arrow(ax, 3.6, 3.6, 6.4, 3.47, color=C_ACTIVE, lw=1.4)
    arrow(ax, 3.6, 2.45, 6.4, 2.32, color=C_ACTIVE, lw=1.4)
    ax.text(5.0, 0.85, "This is not picking whichever split scores best - the three still postures were\n"
                       "PROVEN impossible to separate with this sensor, so they are merged to match reality.",
            ha="center", fontsize=10, color="#41506B", linespacing=1.6)
    fig.tight_layout(); p = f"{OUT}/week12_regroup.png"
    fig.savefig(p); plt.close(fig); return p


def fig_octave_error():
    fig, axes = plt.subplots(2, 1, figsize=(11, 4.6))
    fs, dur, rr = 400, 6.0, 0.385
    t = np.linspace(0, dur, int(fs * dur))
    beats = np.arange(0.20, dur, rr)
    sig = np.zeros_like(t)
    for i, b in enumerate(beats):
        sig += (1.0 if i % 2 == 0 else 0.42) * np.exp(-((t - b) / 0.055) ** 2)

    axes[0].plot(t, sig, color=C_INK, lw=1.7)
    axes[0].plot(beats, [1.0 if i % 2 == 0 else 0.42 for i in range(len(beats))],
                 "v", color=C_GOOD, ms=7, clip_on=False)
    axes[0].set_title("The real pulse while running - tall and short peaks alternate",
                      fontsize=11.5, fontweight="bold", loc="left")
    axes[0].text(dur / 2, 1.34, "each green marker is one real heartbeat  -  156 beats per minute",
                 ha="center", fontsize=9.8, color=C_GOOD)

    axes[1].plot(t, sig, color="#C9D2DE", lw=1.5)
    axes[1].plot(beats[::2], [1.0] * len(beats[::2]), "v", color=C_BAD, ms=8, clip_on=False)
    for b in beats[::2]:
        axes[1].axvline(b, color=C_BAD, lw=1.0, ls=(0, (3, 3)), alpha=0.75)
    axes[1].set_title("The machine counts only the tall peaks - the pattern repeats every two beats",
                      fontsize=11.5, fontweight="bold", loc="left", color=C_BAD)
    axes[1].text(dur / 2, 1.34, "so it reports 77 beats per minute  -  exactly half the truth",
                 ha="center", fontsize=9.8, color=C_BAD, fontweight="bold")
    axes[1].set_xlabel("seconds")
    for a in axes:
        a.set_ylim(-0.05, 1.55); a.set_xlim(0, dur); a.set_yticks([])
        a.spines["left"].set_visible(False); a.grid(False)
    fig.tight_layout(); p = f"{OUT}/week13_octave_error.png"
    fig.savefig(p); plt.close(fig); return p


def fig_two_layers():
    fig, ax = blank_ax((11, 3.6))
    ax.text(5.0, 9.2, "Why this bug survived for weeks unnoticed",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)
    box(ax, 0.4, 5.6, 3.5, 2.1, "MEASUREMENT LAYER\nReads 8 seconds of signal,\n"
                                "produces one number", C_ACTIVE, fontsize=10)
    box(ax, 6.1, 5.6, 3.5, 2.1, "SMOOTHING LAYER\nRejects numbers that\njump implausibly",
        "#8A98AB", fontsize=10)
    arrow(ax, 3.95, 6.65, 6.05, 6.65)
    ax.text(5.0, 7.05, "77, 77, 77, ...", ha="center", fontsize=10, color=C_BAD,
            fontweight="bold")
    ax.text(5.0, 6.1, "so steady it is trusted immediately", ha="center", fontsize=9,
            color="#6B7785", style="italic")
    ax.add_patch(FancyBboxPatch((0.4, 1.0), 9.2, 3.9,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor=C_WARN_BG, edgecolor=C_BAD, linewidth=1.3))
    ax.text(5.0, 4.2, "The paradox", ha="center", fontsize=10.5, fontweight="bold",
            color=C_BAD)
    ax.text(5.0, 2.6, "The bug is in the MEASUREMENT layer, but the guard sits in the SMOOTHING layer.\n"
                      "When the measurement layer occasionally got 156 right, the smoothing layer\n"
                      "REJECTED it, believing a heart rate cannot jump that far.\n\n"
                      "The system actively protected the wrong number.",
            ha="center", va="center", fontsize=10, color="#7A2E28", linespacing=1.7)
    fig.tight_layout(); p = f"{OUT}/week13_two_layers.png"
    fig.savefig(p); plt.close(fig); return p


def main():
    os.makedirs(OUT, exist_ok=True)
    figs = [fig_project_pipeline, fig_flash_vs_wireless, fig_transport_pivot,
            fig_protocol_timeline, fig_two_channels, fig_quality_gate, fig_logocv,
            fig_filter_setup, fig_train_to_device, fig_regroup, fig_octave_error,
            fig_two_layers]
    print("Saved:")
    for f in figs:
        print(f"  {f()}")


if __name__ == "__main__":
    main()
