"""
Explanatory diagrams for the weekly reports.

WHY THESE EXIST
    The weekly reports are read by an advisor who does not work in signal processing.
    A list of bullet points describing architecture decisions is hard to picture on a
    first read, however carefully each bullet is worded. These diagrams carry the shape
    of each decision so the text only has to explain the reasoning.

    They deliberately contain no jargon, no axis numbers and no signal plots -- they are
    boxes and arrows showing where data goes and what happens when something fails.

OUTPUT
    paper/weekly_reports/figures/

USAGE
    python scripts/report/plot_week_diagrams.py
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = "paper/weekly_reports/figures"

C_ACTIVE, C_IDLE = "#2E6F95", "#C9D2DE"
C_GOOD, C_BAD, C_INK = "#2E7D45", "#B3261E", "#1F3B63"
C_WARN_BG, C_GOOD_BG = "#FBEAE8", "#E8F3EC"
C_STATIC_WARM = "#C2643B"

plt.rcParams.update({"figure.dpi": 130, "font.size": 10.5})


def box(ax, x, y, w, h, text, face, edge=None, fontsize=10.5, weight="normal",
        textcolor="white"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02",
                                facecolor=face, edgecolor=edge or face, linewidth=1.6))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize,
            color=textcolor, fontweight=weight, linespacing=1.45)


def arrow(ax, x1, y1, x2, y2, color=C_INK, style="-|>", lw=1.8, ls="-"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, color=color,
                                 linewidth=lw, linestyle=ls, mutation_scale=17,
                                 shrinkA=2, shrinkB=2))


def blank_ax(figsize):
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")
    return fig, ax


# ------------------------------------------------------------------ Figure 1
def fig_project_pipeline():
    """Where this week sits in the project as a whole."""
    fig, ax = blank_ax((11, 3.5))
    stages = [
        ("1. Thu thập\ndữ liệu", C_ACTIVE, "TUẦN 5–8"),
        ("2. Làm sạch\n& gán nhãn", C_IDLE, "Tuần 8–9"),
        ("3. Huấn luyện\nmô hình AI", C_IDLE, "Tuần 9, 12"),
        ("4. Phân tích\n& báo cáo", C_IDLE, "Tuần 10–13"),
    ]
    w, h, gap = 2.05, 2.1, 0.55
    x0 = 0.5
    for i, (label, colour, when) in enumerate(stages):
        x = x0 + i * (w + gap)
        box(ax, x, 4.6, w, h, label, colour,
            fontsize=11, weight="bold",
            textcolor="white" if colour == C_ACTIVE else "#41506B")
        ax.text(x + w / 2, 4.25, when, ha="center", va="top", fontsize=9,
                color=C_ACTIVE if colour == C_ACTIVE else "#8A98AB",
                fontweight="bold" if colour == C_ACTIVE else "normal")
        if i < len(stages) - 1:
            arrow(ax, x + w + 0.08, 5.65, x + w + gap - 0.08, 5.65, color="#8A98AB")

    ax.text(5.0, 8.6, "Tuần 5 nằm ở bước đầu tiên của toàn dự án",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)
    ax.text(5.0, 7.85,
            "Chưa có dữ liệu đáng tin thì ba bước sau đều không thực hiện được",
            ha="center", fontsize=10.5, color="#55606D")

    ax.add_patch(FancyBboxPatch((0.5, 1.5), 9.05, 2.0,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor="#F4F7FA", edgecolor="#D6DEE9", linewidth=1.2))
    ax.text(5.0, 2.5,
            "Mỗi người tham gia chỉ đến đo MỘT lần duy nhất.\n"
            "Một buổi đo hỏng là mất vĩnh viễn dữ liệu của người đó — không đo lại được.",
            ha="center", va="center", fontsize=10.5, color="#41506B", linespacing=1.6)

    fig.tight_layout()
    p = f"{OUT}/week05_project_pipeline.png"
    fig.savefig(p); plt.close(fig)
    return p


# ------------------------------------------------------------------ Figure 2
def fig_flash_vs_wireless():
    """Why the device writes to its own memory first."""
    fig, ax = blank_ax((11, 5.2))
    ax.text(5.0, 9.5, "Dữ liệu đi đâu sau khi cảm biến đọc được?",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)

    box(ax, 0.35, 5.1, 1.9, 1.5, "Thiết bị\nđeo tay", C_INK, fontsize=10.5, weight="bold")

    # Đường bắt buộc
    ax.add_patch(FancyBboxPatch((2.9, 6.35), 6.75, 2.35,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor=C_GOOD_BG, edgecolor=C_GOOD, linewidth=1.5))
    ax.text(3.15, 8.35, "ĐƯỜNG CHÍNH — luôn luôn chạy", fontsize=9.5,
            fontweight="bold", color=C_GOOD, va="center")
    box(ax, 3.15, 6.7, 2.5, 1.25, "Ghi vào bộ nhớ\ntrong thiết bị", C_GOOD, fontsize=10)
    box(ax, 6.9, 6.7, 2.5, 1.25, "Sau buổi đo,\ncắm dây lấy về", C_GOOD, fontsize=10)
    arrow(ax, 5.75, 7.32, 6.8, 7.32, color=C_GOOD)
    arrow(ax, 2.3, 6.1, 3.1, 7.0, color=C_GOOD)

    # Đường phụ
    ax.add_patch(FancyBboxPatch((2.9, 3.15), 6.75, 2.35,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor="#F4F7FA", edgecolor="#B8C4D6", linewidth=1.5))
    ax.text(3.15, 5.15, "ĐƯỜNG PHỤ — có thì tốt, mất cũng không sao", fontsize=9.5,
            fontweight="bold", color="#6B7785", va="center")
    box(ax, 3.15, 3.5, 2.5, 1.25, "Gửi qua\nBluetooth", "#8A98AB", fontsize=10)
    box(ax, 6.9, 3.5, 2.5, 1.25, "Xem trực tiếp\ntrên máy tính", "#8A98AB", fontsize=10)
    arrow(ax, 5.75, 4.12, 6.8, 4.12, color="#8A98AB", ls=(0, (4, 2)))
    arrow(ax, 2.3, 5.6, 3.1, 4.4, color="#8A98AB", ls=(0, (4, 2)))
    ax.text(6.3, 2.72, "Bluetooth thỉnh thoảng mất sóng", ha="center", fontsize=9,
            color=C_BAD, style="italic")

    ax.add_patch(FancyBboxPatch((0.35, 0.35), 9.3, 1.75,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor=C_WARN_BG, edgecolor=C_BAD, linewidth=1.3))
    ax.text(5.0, 1.22,
            "Nếu dựa hẳn vào Bluetooth để lưu: một lần mất sóng giữa buổi đo\n"
            "là mất trắng dữ liệu của người tham gia hôm đó.",
            ha="center", va="center", fontsize=10.5, color="#7A2E28", linespacing=1.6)

    fig.tight_layout()
    p = f"{OUT}/week05_flash_vs_wireless.png"
    fig.savefig(p); plt.close(fig)
    return p


# ------------------------------------------------------------------ Figure 3
def fig_transport_pivot():
    """The decision to drop the intermediate machine."""
    fig, ax = blank_ax((11, 4.2))
    ax.text(5.0, 9.4, "Quyết định đổi cách truyền dữ liệu",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)

    # Trước
    ax.text(0.35, 7.9, "Kế hoạch ban đầu", fontsize=10.5, fontweight="bold",
            color="#8A98AB", va="center")
    for i, (lbl, x) in enumerate([("Thiết bị\nđeo tay", 0.35), ("Máy trung gian\n(Jetson)", 3.6),
                                  ("Máy tính", 7.0)]):
        box(ax, x, 5.9, 2.4, 1.35, lbl, C_IDLE, fontsize=10, textcolor="#41506B")
    arrow(ax, 2.85, 6.57, 3.5, 6.57, color="#8A98AB")
    arrow(ax, 6.1, 6.57, 6.9, 6.57, color="#8A98AB")
    ax.text(4.8, 5.35, "lỗi phần mềm mạng, sửa mãi không xong",
            ha="center", fontsize=9.5, color=C_BAD, style="italic")
    # Cắt ở đoạn nối phía sau máy trung gian, không vẽ đè lên tên hộp.
    ax.plot([6.28, 6.72], [6.35, 6.79], color=C_BAD, lw=2.8, zorder=6)
    ax.plot([6.28, 6.72], [6.79, 6.35], color=C_BAD, lw=2.8, zorder=6)

    # Sau
    ax.text(0.35, 3.9, "Đã đổi thành", fontsize=10.5, fontweight="bold",
            color=C_GOOD, va="center")
    box(ax, 0.35, 1.9, 2.4, 1.35, "Thiết bị\nđeo tay", C_INK, fontsize=10)
    box(ax, 7.0, 1.9, 2.4, 1.35, "Máy tính", C_ACTIVE, fontsize=10)
    arrow(ax, 2.85, 2.57, 6.9, 2.57, color=C_GOOD, lw=2.2)
    ax.text(4.9, 3.0, "Bluetooth — nối thẳng, bỏ máy trung gian",
            ha="center", fontsize=10, color=C_GOOD, fontweight="bold")
    ax.text(4.9, 1.45, "đã chứng minh chạy ổn định", ha="center", fontsize=9.5,
            color="#55606D", style="italic")

    fig.tight_layout()
    p = f"{OUT}/week05_transport_pivot.png"
    fig.savefig(p); plt.close(fig)
    return p


# ------------------------------------------------------------------ Week 6
def fig_protocol_timeline():
    """The measurement protocol, and the labelling bug it fixed."""
    fig, ax = blank_ax((11, 4.0))
    ax.text(5.0, 9.4, "Một buổi đo diễn ra như thế nào",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)

    acts = ["Nằm", "Ngồi", "Đứng", "Đi bộ", "Chạy"]
    x = 1.75
    box(ax, 0.35, 5.6, 1.25, 1.5, "Chuẩn bị\n15 giây", "#8A98AB", fontsize=9.5)
    for a in acts:
        box(ax, x, 5.6, 1.42, 1.5, f"{a}\n90 giây", C_ACTIVE, fontsize=9.5)
        x += 1.42
        if a != "Chạy":
            ax.add_patch(FancyBboxPatch((x, 5.95), 0.2, 0.8,
                                        boxstyle="round,pad=0.005,rounding_size=0.01",
                                        facecolor="#E3E9F1", edgecolor="#E3E9F1"))
            x += 0.2
    ax.text(5.6, 5.15, "khoảng đệm giữa các động tác (nhạt màu) — bị loại khỏi phân tích",
            ha="center", fontsize=9, color="#6B7785", style="italic")

    ax.add_patch(FancyBboxPatch((0.35, 2.7), 4.4, 1.95,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor=C_WARN_BG, edgecolor=C_BAD, linewidth=1.3))
    ax.text(2.55, 4.25, "Trước khi sửa", ha="center", fontsize=10, fontweight="bold",
            color=C_BAD)
    ax.text(2.55, 3.4, "Máy ghi ngay khi vừa bật.\nNgười chưa kịp nằm xuống,\n"
                       "máy đã gắn nhãn \"đang nằm\".",
            ha="center", va="center", fontsize=9.8, color="#7A2E28", linespacing=1.5)

    ax.add_patch(FancyBboxPatch((5.25, 2.7), 4.4, 1.95,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor=C_GOOD_BG, edgecolor=C_GOOD, linewidth=1.3))
    ax.text(7.45, 4.25, "Sau khi sửa", ha="center", fontsize=10, fontweight="bold",
            color=C_GOOD)
    ax.text(7.45, 3.4, "Chờ 15 giây cho vào tư thế,\nmáy tính nhắc bằng âm thanh\n"
                       "mỗi khi cần đổi động tác.",
            ha="center", va="center", fontsize=9.8, color="#1E5C33", linespacing=1.5)

    ax.text(5.0, 1.55, "Nhãn sai ngay từ giây đầu tiên sẽ theo dữ liệu đó suốt cả dự án — "
                       "AI học từ nhãn, không học từ sự thật.",
            ha="center", fontsize=10, color="#41506B", style="italic")
    fig.tight_layout()
    p = f"{OUT}/week06_protocol_timeline.png"
    fig.savefig(p); plt.close(fig); return p


# ------------------------------------------------------------------ Week 7
def fig_two_channels():
    """Why a second sensor was added at the fingertip."""
    fig, ax = blank_ax((11, 4.0))
    ax.text(5.0, 9.4, "Vì sao cần gắn thêm cảm biến thứ hai ở đầu ngón tay",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)

    box(ax, 0.5, 5.4, 3.9, 2.5,
        "CẢM BIẾN 1 — CỔ TAY\n\nĐây là thứ sản phẩm thật sẽ dùng.\n"
        "Nhưng cử động tay làm nhiễu rất mạnh.",
        C_ACTIVE, fontsize=10)
    box(ax, 5.6, 5.4, 3.9, 2.5,
        "CẢM BIẾN 2 — ĐẦU NGÓN TAY\n\nChỉ dùng khi nghiên cứu, không có\n"
        "trong sản phẩm. Ít nhiễu hơn nhiều.",
        C_GOOD, fontsize=10)

    arrow(ax, 2.45, 5.25, 3.9, 3.9, color=C_ACTIVE)
    arrow(ax, 7.55, 5.25, 6.1, 3.9, color=C_GOOD)
    box(ax, 3.4, 2.5, 3.2, 1.3, "So sánh hai bên\nvới nhau", C_INK, fontsize=10.5,
        weight="bold")

    ax.text(5.0, 1.65,
            "Cảm biến 2 đóng vai \"đáp án đúng\" để chấm điểm cảm biến 1.\n"
            "Không có đáp án thì không biết cách lọc nhiễu nào tốt hơn cách nào.",
            ha="center", fontsize=10.2, color="#41506B", linespacing=1.6)
    fig.tight_layout()
    p = f"{OUT}/week07_two_channels.png"
    fig.savefig(p); plt.close(fig); return p


# ------------------------------------------------------------------ Week 8
def fig_quality_gate():
    """The automatic rule that separated real sessions from bench tests."""
    fig, ax = blank_ax((11, 3.8))
    ax.text(5.0, 9.3, "Lọc ra những buổi đo không có người đeo",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)

    box(ax, 0.4, 5.2, 2.3, 1.9, "21 buổi đo\nđã thu được", "#8A98AB", fontsize=10.5,
        weight="bold")
    box(ax, 3.5, 5.2, 3.0, 1.9,
        "Quy tắc tự động:\nlúc chạy phải rung mạnh\nhơn lúc nằm ít nhất 3 lần",
        C_INK, fontsize=9.8)
    arrow(ax, 2.75, 6.15, 3.45, 6.15)

    box(ax, 7.35, 6.55, 2.3, 1.15, "15 buổi\nHỢP LỆ", C_GOOD, fontsize=10.5, weight="bold")
    box(ax, 7.35, 4.75, 2.3, 1.15, "6 buổi\nBỊ LOẠI", C_BAD, fontsize=10.5, weight="bold")
    arrow(ax, 6.55, 6.4, 7.3, 7.1, color=C_GOOD)
    arrow(ax, 6.55, 5.9, 7.3, 5.3, color=C_BAD)

    ax.add_patch(FancyBboxPatch((0.4, 1.1), 9.25, 3.05,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor=C_WARN_BG, edgecolor=C_BAD, linewidth=1.3))
    ax.text(5.0, 2.6,
            "6 buổi bị loại là những lần thử thiết bị — máy nằm yên trên bàn, không ai đeo.\n"
            "Chúng vượt qua MỌI kiểm tra tự động trước đó: đủ số nhãn, đủ số dòng, không báo lỗi.\n"
            "Chỉ lộ ra khi vẽ dạng sóng lên nhìn và hỏi: lúc \"chạy\" sao lại phẳng như lúc nằm?",
            ha="center", va="center", fontsize=10, color="#7A2E28", linespacing=1.7)
    fig.tight_layout()
    p = f"{OUT}/week08_quality_gate.png"
    fig.savefig(p); plt.close(fig); return p


# ------------------------------------------------------------------ Week 9
def fig_logocv():
    """How the model is evaluated on people it has never seen."""
    fig, ax = blank_ax((11, 5.0))
    ax.text(5.0, 9.5, "Cách chấm điểm AI: luôn kiểm tra trên người chưa từng gặp",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)

    for r, (label, held) in enumerate([("Vòng 1", 0), ("Vòng 2", 1), ("Vòng 18", 17)]):
        y = 7.2 - r * 1.55
        ax.text(0.35, y + 0.42, label, fontsize=10, fontweight="bold", color=C_INK,
                va="center")
        for i in range(18):
            x = 1.7 + i * 0.45
            is_test = (i == held)
            ax.add_patch(FancyBboxPatch((x, y), 0.36, 0.85,
                                        boxstyle="round,pad=0.006,rounding_size=0.012",
                                        facecolor=C_BAD if is_test else C_IDLE,
                                        edgecolor="none"))
        if r == 2:
            ax.text(1.7 + 8 * 0.45, y + 1.35, ". . .   lặp lại cho đủ 18 vòng   . . .",
                    ha="center", fontsize=9.5, color="#6B7785", style="italic")

    ax.add_patch(FancyBboxPatch((1.7, 2.35), 1.0, 0.55,
                                boxstyle="round,pad=0.006,rounding_size=0.012",
                                facecolor=C_IDLE, edgecolor="none"))
    ax.text(2.9, 2.62, "17 người dùng để DẠY", fontsize=10, va="center", color="#41506B")
    ax.add_patch(FancyBboxPatch((6.0, 2.35), 1.0, 0.55,
                                boxstyle="round,pad=0.006,rounding_size=0.012",
                                facecolor=C_BAD, edgecolor="none"))
    ax.text(7.2, 2.62, "1 người dùng để CHẤM", fontsize=10, va="center", color="#41506B")

    ax.add_patch(FancyBboxPatch((0.35, 0.3), 9.3, 1.7,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor="#F4F7FA", edgecolor="#D6DEE9", linewidth=1.2))
    ax.text(5.0, 1.15,
            "Nếu trộn chung dữ liệu của cùng một người vào cả phần dạy lẫn phần chấm,\n"
            "AI chỉ cần \"nhớ mặt\" người đó là được điểm cao — điểm đẹp nhưng vô nghĩa.",
            ha="center", va="center", fontsize=10.2, color="#41506B", linespacing=1.6)
    fig.tight_layout()
    p = f"{OUT}/week09_logocv.png"
    fig.savefig(p); plt.close(fig); return p


# ------------------------------------------------------------------ Week 10
def fig_filter_setup():
    """The three-filter comparison, laid out."""
    fig, ax = blank_ax((11, 4.0))
    ax.text(5.0, 9.4, "Bố trí thí nghiệm so sánh ba cách lọc nhiễu",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)

    box(ax, 0.35, 6.6, 2.5, 1.3, "Tín hiệu tim\nđo ở cổ tay", C_ACTIVE, fontsize=9.8)
    box(ax, 0.35, 4.7, 2.5, 1.3, "Cử động tay\n(cảm biến chuyển động)", "#8A98AB",
        fontsize=9.8)

    for i, (name, y) in enumerate([("Cách 1: NLMS", 7.3), ("Cách 2: RLS", 6.0),
                                   ("Cách 3: Wiener", 4.7)]):
        box(ax, 3.7, y - 0.45, 2.3, 0.95, name, C_INK, fontsize=9.8)
        arrow(ax, 2.95, 7.25 if i == 0 else (6.0 if i == 1 else 5.35), 3.65, y,
              color="#8A98AB")

    box(ax, 6.9, 5.7, 2.7, 1.6, "So với nhịp tim\nđo ở đầu ngón tay\n(đáp án đúng)",
        C_GOOD, fontsize=9.8)
    for y in (7.3, 6.0, 4.7):
        arrow(ax, 6.05, y, 6.85, 6.5, color="#8A98AB")

    ax.add_patch(FancyBboxPatch((0.35, 1.3), 9.3, 2.75,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor="#F4F7FA", edgecolor="#D6DEE9", linewidth=1.2))
    ax.text(5.0, 3.35, "Nguyên tắc của cả ba cách", ha="center", fontsize=10.5,
            fontweight="bold", color=C_INK)
    ax.text(5.0, 2.3,
            "Tín hiệu ở cổ tay = nhịp tim thật + nhiễu do cử động.\n"
            "Cả ba cách đều dùng cảm biến chuyển động để đoán phần nhiễu, rồi TRỪ nó đi.\n"
            "Chúng chỉ khác nhau ở cách đoán phần nhiễu đó.",
            ha="center", va="center", fontsize=10, color="#41506B", linespacing=1.7)
    fig.tight_layout()
    p = f"{OUT}/week10_filter_setup.png"
    fig.savefig(p); plt.close(fig); return p


# ------------------------------------------------------------------ Week 11
def fig_train_to_device():
    """Getting a trained model onto the chip -- and the step that was missed."""
    fig, ax = blank_ax((11, 3.6))
    ax.text(5.0, 9.2, "Đưa AI đã học từ máy tính lên con chip đeo tay",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)

    steps = [("Huấn luyện\ntrên máy tính", C_ACTIVE), ("Dịch sang mã\nchip hiểu được", C_ACTIVE),
             ("Nạp vào\nthiết bị", C_ACTIVE)]
    x = 0.7
    for i, (lbl, c) in enumerate(steps):
        box(ax, x, 5.3, 2.5, 1.7, lbl, c, fontsize=10)
        if i < 2:
            arrow(ax, x + 2.55, 6.15, x + 3.15, 6.15)
        x += 3.15

    ax.plot([6.3, 6.3], [5.1, 4.35], color=C_BAD, lw=1.6, ls=(0, (3, 2)))
    ax.text(6.3, 4.05, "bước bị quên", ha="center", fontsize=9.5, color=C_BAD,
            fontweight="bold")

    ax.add_patch(FancyBboxPatch((0.4, 0.9), 9.2, 2.85,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor=C_WARN_BG, edgecolor=C_BAD, linewidth=1.3))
    ax.text(5.0, 3.05, "Lỗi phát hiện được tuần này", ha="center", fontsize=10.5,
            fontweight="bold", color=C_BAD)
    ax.text(5.0, 1.95,
            "Model mới đã được dịch sang mã chip xong, nhưng chương trình trên thiết bị\n"
            "vẫn đang gọi model CŨ — vì chưa ai nối hai phần đó lại với nhau.\n"
            "Từng phần đều đúng, chỉ thiếu bước cắm chúng vào nhau.",
            ha="center", va="center", fontsize=10, color="#7A2E28", linespacing=1.7)
    fig.tight_layout()
    p = f"{OUT}/week11_train_to_device.png"
    fig.savefig(p); plt.close(fig); return p


# ------------------------------------------------------------------ Week 12
def fig_regroup():
    """Merging the three static postures into one class."""
    fig, ax = blank_ax((11, 3.8))
    ax.text(5.0, 9.3, "Gộp ba tư thế tĩnh thành một nhóm",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)

    ax.text(2.0, 8.1, "5 lớp — độ chính xác 54.8%", ha="center", fontsize=10.5,
            fontweight="bold", color=C_BAD)
    for i, a in enumerate(["Nằm", "Ngồi", "Đứng", "Đi bộ", "Chạy"]):
        c = C_STATIC_WARM if i < 3 else C_ACTIVE
        box(ax, 0.5, 6.6 - i * 1.15, 3.0, 0.95, a, c, fontsize=10)

    ax.text(8.0, 8.1, "3 lớp — độ chính xác 85.3%", ha="center", fontsize=10.5,
            fontweight="bold", color=C_GOOD)
    box(ax, 6.5, 4.3, 3.0, 3.25, "NGHỈ\n(gộp cả ba tư thế tĩnh)", C_STATIC_WARM,
        fontsize=10.5, weight="bold")
    box(ax, 6.5, 3.0, 3.0, 0.95, "Đi bộ", C_ACTIVE, fontsize=10)
    box(ax, 6.5, 1.85, 3.0, 0.95, "Chạy", C_ACTIVE, fontsize=10)

    for i in range(3):
        arrow(ax, 3.6, 7.05 - i * 1.15, 6.4, 5.9, color=C_STATIC_WARM, lw=1.4)
    arrow(ax, 3.6, 3.6, 6.4, 3.47, color=C_ACTIVE, lw=1.4)
    arrow(ax, 3.6, 2.45, 6.4, 2.32, color=C_ACTIVE, lw=1.4)

    ax.text(5.0, 0.85,
            "Không phải chọn cách chia nào ra số đẹp hơn — ba tư thế tĩnh đã được chứng minh\n"
            "là KHÔNG THỂ phân biệt bằng bộ cảm biến hiện tại, nên gộp lại cho đúng thực tế.",
            ha="center", fontsize=10, color="#41506B", linespacing=1.6)
    fig.tight_layout()
    p = f"{OUT}/week12_regroup.png"
    fig.savefig(p); plt.close(fig); return p


# ------------------------------------------------------------------ Week 13
def fig_octave_error():
    """Why the machine read exactly half the true heart rate."""
    import numpy as np
    fig, axes = plt.subplots(2, 1, figsize=(11, 4.6))

    fs, dur, rr = 400, 6.0, 0.385          # rr = 0.385 s giữa hai nhịp -> 156 nhịp/phút
    t = np.linspace(0, dur, int(fs * dur))
    beats = np.arange(0.20, dur, rr)
    sig = np.zeros_like(t)
    for i, b in enumerate(beats):
        height = 1.0 if i % 2 == 0 else 0.42   # cao - thap xen ke
        sig += height * np.exp(-((t - b) / 0.055) ** 2)

    axes[0].plot(t, sig, color=C_INK, lw=1.7)
    axes[0].plot(beats, [1.0 if i % 2 == 0 else 0.42 for i in range(len(beats))],
                 "v", color=C_GOOD, ms=7, clip_on=False)
    axes[0].set_title("Sóng nhịp tim thật khi chạy — đỉnh cao và đỉnh thấp xen kẽ nhau",
                      fontsize=11.5, fontweight="bold", loc="left")
    axes[0].text(dur / 2, 1.34,
                 "mỗi tam giác xanh là một nhịp tim thật  —  156 nhịp/phút",
                 ha="center", fontsize=9.8, color=C_GOOD)

    axes[1].plot(t, sig, color="#C9D2DE", lw=1.5)
    axes[1].plot(beats[::2], [1.0] * len(beats[::2]), "v", color=C_BAD, ms=8,
                 clip_on=False)
    for b in beats[::2]:
        axes[1].axvline(b, color=C_BAD, lw=1.0, ls=(0, (3, 3)), alpha=0.75)
    axes[1].set_title("Máy chỉ đếm những đỉnh CAO — vì mẫu hình lặp lại sau mỗi hai nhịp",
                      fontsize=11.5, fontweight="bold", loc="left", color=C_BAD)
    axes[1].text(dur / 2, 1.34, "nên máy báo 77 nhịp/phút  —  đúng một nửa sự thật",
                 ha="center", fontsize=9.8, color=C_BAD, fontweight="bold")
    axes[1].set_xlabel("giây")

    for a in axes:
        a.set_ylim(-0.05, 1.55); a.set_xlim(0, dur); a.set_yticks([])
        a.spines["left"].set_visible(False); a.grid(False)
    fig.tight_layout()
    p = f"{OUT}/week13_octave_error.png"
    fig.savefig(p); plt.close(fig); return p


def fig_two_layers():
    """The smoothing layer protecting a wrong measurement."""
    fig, ax = blank_ax((11, 3.6))
    ax.text(5.0, 9.2, "Vì sao lỗi này sống sót nhiều tuần mà không ai thấy",
            ha="center", fontsize=13, fontweight="bold", color=C_INK)

    box(ax, 0.4, 5.6, 3.5, 2.1,
        "TẦNG ĐO\nĐọc 8 giây sóng,\ncho ra một con số", C_ACTIVE, fontsize=10)
    box(ax, 6.1, 5.6, 3.5, 2.1,
        "TẦNG LÀM MƯỢT\nGạt bỏ những con số\nnhảy vọt bất thường", "#8A98AB", fontsize=10)
    arrow(ax, 3.95, 6.65, 6.05, 6.65)
    ax.text(5.0, 7.05, "77, 77, 77, ...", ha="center", fontsize=10, color=C_BAD,
            fontweight="bold")
    ax.text(5.0, 6.1, "rất đều nên được tin ngay", ha="center", fontsize=9,
            color="#6B7785", style="italic")

    ax.add_patch(FancyBboxPatch((0.4, 1.0), 9.2, 3.9,
                                boxstyle="round,pad=0.02,rounding_size=0.03",
                                facecolor=C_WARN_BG, edgecolor=C_BAD, linewidth=1.3))
    ax.text(5.0, 4.2, "Nghịch lý", ha="center", fontsize=10.5, fontweight="bold",
            color=C_BAD)
    ax.text(5.0, 2.6,
            "Lỗi nằm ở tầng ĐO, nhưng bộ chặn lại nằm ở tầng LÀM MƯỢT.\n"
            "Khi tầng đo thỉnh thoảng bắt đúng 156, tầng làm mượt lại GẠT ĐI\n"
            "vì cho rằng nhịp tim không thể nhảy nhiều đến thế.\n\n"
            "Hệ thống đã chủ động bảo vệ con số sai.",
            ha="center", va="center", fontsize=10, color="#7A2E28", linespacing=1.7)
    fig.tight_layout()
    p = f"{OUT}/week13_two_layers.png"
    fig.savefig(p); plt.close(fig); return p


WEEK_FIGS = [fig_protocol_timeline, fig_two_channels, fig_quality_gate, fig_logocv,
             fig_filter_setup, fig_train_to_device, fig_regroup, fig_octave_error,
             fig_two_layers]



def main():
    os.makedirs(OUT, exist_ok=True)
    paths = [fig_project_pipeline(), fig_flash_vs_wireless(), fig_transport_pivot()]
    paths += [f() for f in WEEK_FIGS]
    print("Đã lưu:")
    for p in paths:
        print(f"  {p}")


if __name__ == "__main__":
    main()
