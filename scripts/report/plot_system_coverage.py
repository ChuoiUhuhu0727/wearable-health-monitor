"""
Test-coverage map of the whole system, layer by layer.

WHY THIS EXISTS
    The prototype testing report covers the complete device, not one subsystem. A
    reader needs to see at a glance which layers of the system were actually put
    under test, which were only partly tested, and which carry no evidence in this
    repository at all. A table states that; a picture makes the gaps impossible to
    skim past.

OUTPUT
    paper/figures/system_test_coverage.png      (Vietnamese)
    paper/figures_en/system_test_coverage.png   (English)

USAGE
    python scripts/report/plot_system_coverage.py
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

C_INK = "#1F3B63"
C_FULL, C_PART, C_NONE = "#2E7D45", "#C2643B", "#8B96A5"
C_FULL_BG, C_PART_BG, C_NONE_BG = "#E8F3EC", "#FBEDE5", "#EDEFF2"

plt.rcParams.update({"figure.dpi": 130, "font.size": 10.5})

FULL, PART, NONE = "full", "part", "none"

# bottom of the stack first: physical foundation -> abstract
LAYERS = {
    "vi": [
        ("Cơ khí, vỏ và dây đeo", "Vỏ, độ vừa vặn, độ bám khi vận động, thử rơi", NONE,
         "Chưa kiểm thử"),
        ("Mạch in và nguồn điện", "Mạch in riêng, thời lượng pin, chất lượng tín hiệu I2C", PART,
         "Một phần"),
        ("Cảm biến và tiếp xúc da", "Hai cảm biến quang học, cảm biến chuyển động, phát hiện áp da", FULL,
         "Đã kiểm thử"),
        ("Firmware và lưu trữ", "Đa tác vụ, ghi flash, phân vùng bộ nhớ, giao thức phiên đo", FULL,
         "Đã kiểm thử"),
        ("Truyền dữ liệu", "Bluetooth theo dõi trực tiếp, quy trình rút dữ liệu về máy", PART,
         "Một phần"),
        ("Mô hình AI trên thiết bị", "Nhận diện hoạt động, ước lượng nhịp tim", FULL,
         "Đã kiểm thử"),
    ],
    "en": [
        ("Mechanics, case and strap", "Enclosure, fit, stability during movement, drop test", NONE,
         "Not tested"),
        ("Circuit board and power", "Custom board, battery life, I2C signal quality", PART,
         "Partial"),
        ("Sensors and skin contact", "Two optical sensors, motion sensor, contact detection", FULL,
         "Tested"),
        ("Firmware and storage", "Multitasking, flash logging, partitioning, session protocol", FULL,
         "Tested"),
        ("Data transport", "Bluetooth live monitoring, pulling data back to the laptop", PART,
         "Partial"),
        ("On-device AI model", "Activity recognition, heart rate estimation", FULL,
         "Tested"),
    ],
}

TITLE = {
    "vi": "Sáu tầng của hệ thống — tầng nào đã được đưa vào kiểm thử",
    "en": "The six layers of the system — which ones were put under test",
}
FOOT = {
    "vi": "Đọc từ dưới lên: tầng vật lý ở dưới, tầng phần mềm ở trên.",
    "en": "Read bottom-up: physical layers at the bottom, software layers on top.",
}

STYLE = {FULL: (C_FULL, C_FULL_BG), PART: (C_PART, C_PART_BG), NONE: (C_NONE, C_NONE_BG)}


def draw(lang, out_dir):
    layers = LAYERS[lang]
    fig, ax = plt.subplots(figsize=(11.4, 5.6))
    ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")

    h, gap = 1.28, 0.20
    y0 = 0.85
    for i, (name, detail, state, label) in enumerate(layers):
        y = y0 + i * (h + gap)
        edge, face = STYLE[state]
        ax.add_patch(FancyBboxPatch((0.35, y), 7.15, h,
                                    boxstyle="round,pad=0.012,rounding_size=0.02",
                                    facecolor=face, edgecolor=edge, linewidth=1.9))
        ax.text(0.72, y + h * 0.63, name, ha="left", va="center",
                fontsize=11.5, color=C_INK, fontweight="bold")
        ax.text(0.72, y + h * 0.26, detail, ha="left", va="center",
                fontsize=9.3, color="#4A5A70")

        ax.add_patch(FancyBboxPatch((7.72, y + h * 0.22), 1.95, h * 0.56,
                                    boxstyle="round,pad=0.012,rounding_size=0.03",
                                    facecolor=edge, edgecolor=edge, linewidth=1.4))
        ax.text(8.70, y + h * 0.50, label, ha="center", va="center",
                fontsize=10, color="white", fontweight="bold")

    ax.text(5.0, y0 + 6 * (h + gap) + 0.30, TITLE[lang], ha="center", va="center",
            fontsize=13, color=C_INK, fontweight="bold")
    ax.text(0.35, 0.30, FOOT[lang], ha="left", va="center",
            fontsize=9.3, color="#6B7787", style="italic")

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "system_test_coverage.png")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", path)


if __name__ == "__main__":
    draw("vi", "paper/figures")
    draw("en", "paper/figures_en")
