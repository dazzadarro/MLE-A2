from __future__ import annotations

from math import atan2, cos, sin, pi
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "deck_assets"
OUT_PATH = OUT_DIR / "a2_mle_architecture_dashboard_theme.png"

W, H = 2400, 1350

COLORS = {
    "ink": "#071733",
    "muted": "#60708A",
    "line": "#D7DFEB",
    "canvas": "#F4F7FB",
    "surface": "#FFFFFF",
    "navy": "#061B37",
    "navy2": "#08264B",
    "blue": "#1267D8",
    "green": "#14834C",
    "amber": "#C67A00",
    "orange": "#F58200",
    "red": "#CF2E2E",
    "purple": "#6941C6",
    "soft_blue": "#EEF5FF",
    "soft_green": "#EAF7EF",
    "soft_amber": "#FFF7E8",
    "soft_red": "#FFF0F0",
}

FONT_DIR = Path("C:/Windows/Fonts")
FONT = str(FONT_DIR / "segoeui.ttf")
FONT_BOLD = str(FONT_DIR / "segoeuib.ttf")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def text_size(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for raw_line in text.split("\n"):
        words = raw_line.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if text_size(draw, candidate, fnt)[0] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    fnt: ImageFont.FreeTypeFont,
    fill: str,
    max_width: int,
    line_gap: int = 6,
    anchor: str = "la",
) -> int:
    x, y = xy
    lines = wrap_text(draw, text, fnt, max_width)
    line_h = int(fnt.size * 1.18)
    total_h = len(lines) * line_h + max(0, len(lines) - 1) * line_gap
    start_y = y - total_h // 2 if anchor == "lm" else y
    for idx, line in enumerate(lines):
        draw.text((x, start_y + idx * (line_h + line_gap)), line, font=fnt, fill=fill)
    return total_h


def rounded_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill: str = COLORS["surface"],
    outline: str = COLORS["line"],
    radius: int = 24,
    width: int = 2,
    shadow: bool = True,
) -> None:
    x1, y1, x2, y2 = box
    if shadow:
        draw.rounded_rectangle((x1 + 8, y1 + 10, x2 + 8, y2 + 10), radius=radius, fill="#DCE5F2")
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def pill(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    fill: str,
    outline: str,
    color: str,
    size: int = 24,
) -> None:
    draw.rounded_rectangle(box, radius=(box[3] - box[1]) // 2, fill=fill, outline=outline, width=2)
    fnt = font(size, True)
    tw, th = text_size(draw, text, fnt)
    draw.text(((box[0] + box[2] - tw) // 2, (box[1] + box[3] - th) // 2 - 2), text, font=fnt, fill=color)


def arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    color: str = "#31405A",
    width: int = 4,
    dashed: bool = False,
) -> None:
    sx, sy = start
    ex, ey = end
    if dashed:
        dash_len, gap = 16, 10
        dx, dy = ex - sx, ey - sy
        dist = (dx * dx + dy * dy) ** 0.5
        if dist == 0:
            return
        ux, uy = dx / dist, dy / dist
        pos = 0
        while pos < dist - 18:
            p1 = (sx + ux * pos, sy + uy * pos)
            p2 = (sx + ux * min(pos + dash_len, dist - 18), sy + uy * min(pos + dash_len, dist - 18))
            draw.line((p1, p2), fill=color, width=width)
            pos += dash_len + gap
    else:
        draw.line((start, end), fill=color, width=width)
    angle = atan2(ey - sy, ex - sx)
    head = 18
    p_a = (ex - head * cos(angle - pi / 6), ey - head * sin(angle - pi / 6))
    p_b = (ex - head * cos(angle + pi / 6), ey - head * sin(angle + pi / 6))
    draw.polygon([end, p_a, p_b], fill=color)


def cylinder(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill: str,
    outline: str,
    title: str,
    body: str,
    body_size: int = 20,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle((x1, y1 + 18, x2, y2), radius=18, fill=fill, outline=outline, width=2)
    draw.ellipse((x1, y1, x2, y1 + 42), fill=fill, outline=outline, width=2)
    draw.arc((x1, y2 - 42, x2, y2), 0, 180, fill=outline, width=2)
    f_title = font(25, True)
    f_body = font(body_size)
    tw, _ = text_size(draw, title, f_title)
    draw.text((x1 + (x2 - x1 - tw) // 2, y1 + 52), title, font=f_title, fill=COLORS["ink"])
    draw_wrapped(draw, (x1 + 22, y1 + 92), body, f_body, COLORS["muted"], x2 - x1 - 44, line_gap=4)


def small_store(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    body: str,
    fill: str = "#FFF6D9",
    outline: str = "#C99700",
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle((x1, y1 + 12, x2, y2), radius=12, fill=fill, outline=outline, width=2)
    draw.ellipse((x1, y1, x2, y1 + 32), fill=fill, outline=outline, width=2)
    draw.text((x1 + 18, y1 + 39), title, font=font(22, True), fill=COLORS["ink"])
    draw_wrapped(draw, (x1 + 18, y1 + 72), body, font(15), COLORS["muted"], x2 - x1 - 36, line_gap=2)


def process_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    body: str,
    accent: str,
    fill: str = COLORS["surface"],
) -> None:
    rounded_card(draw, box, fill=fill, outline=COLORS["line"], radius=18, shadow=False)
    x1, y1, x2, y2 = box
    draw.rounded_rectangle((x1, y1, x1 + 10, y2), radius=8, fill=accent)
    draw.text((x1 + 28, y1 + 18), title, font=font(27, True), fill=COLORS["ink"])
    draw_wrapped(draw, (x1 + 28, y1 + 58), body, font(20), COLORS["muted"], x2 - x1 - 56, line_gap=5)


def mini_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    body: str,
    accent: str,
    fill: str,
) -> None:
    rounded_card(draw, box, fill=fill, outline=COLORS["line"], radius=14, shadow=False)
    x1, y1, x2, y2 = box
    draw.rounded_rectangle((x1, y1, x1 + 8, y2), radius=7, fill=accent)
    draw.text((x1 + 18, y1 + 15), title, font=font(20, True), fill=COLORS["ink"])
    draw_wrapped(draw, (x1 + 18, y1 + 46), body, font(15), COLORS["muted"], x2 - x1 - 30, line_gap=2)


def draw_section_label(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, color: str) -> None:
    fnt = font(22, True)
    tw, th = text_size(draw, label.upper(), fnt)
    draw.rounded_rectangle((x, y, x + tw + 28, y + th + 18), radius=8, fill=color)
    draw.text((x + 14, y + 7), label.upper(), font=fnt, fill="#FFFFFF")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (W, H), COLORS["canvas"])
    draw = ImageDraw.Draw(img)

    # Top header, matching the dashboard's navy/gold identity.
    draw.rounded_rectangle((0, 0, W, 150), radius=0, fill=COLORS["navy"])
    draw.rectangle((0, 154, W, 162), fill="#D9A400")
    draw.ellipse((50, 37, 124, 111), outline="#C8D6EA", width=3)
    draw.text((74, 57), "ML", font=font(26, True), fill="#FFFFFF")
    draw.text((150, 34), "CS611 Assignment 2", font=font(28, True), fill="#9BB0CC")
    draw.text((150, 68), "Loan Default Model Lifecycle Architecture", font=font(44, True), fill="#FFFFFF")
    draw.text(
        (150, 120),
        "Medallion data pipeline -> governed champion -> monthly backfill inference -> monitoring dashboard",
        font=font(22),
        fill="#DDE8F7",
    )

    # Airflow orchestration control band.
    rounded_card(draw, (70, 198, 2330, 304), fill="#FFFFFF", outline="#BFD0E8", radius=20)
    draw.text((105, 215), "AIRFLOW ORCHESTRATION", font=font(24, True), fill=COLORS["navy"])
    draw_wrapped(
        draw,
        (105, 252),
        "Airflow controls the lifecycle, while the heavy logic stays in versioned scripts.",
        font(19),
        COLORS["muted"],
        620,
    )
    pill(draw, (790, 224, 1120, 278), "Manual DAG: Dec 2024", COLORS["soft_blue"], "#B8D3FF", COLORS["blue"], 20)
    pill(draw, (1148, 224, 1572, 278), "Backfill DAG: {{ ds }} Jan-Dec 2024", COLORS["soft_green"], "#8DD6AA", COLORS["green"], 20)
    pill(draw, (1600, 224, 2220, 278), "Frozen champion reused unless refresh is explicitly approved", COLORS["soft_amber"], "#F0D187", COLORS["amber"], 20)

    # Main lane containers.
    lane_y1, lane_y2 = 335, 1032
    rounded_card(draw, (70, lane_y1, 2330, lane_y2), fill="#FFFFFF", outline="#CBD5E1", radius=28)
    draw_section_label(draw, 102, 362, "Process Data", COLORS["orange"])
    draw_section_label(draw, 824, 362, "Develop Model", COLORS["purple"])
    draw_section_label(draw, 1442, 362, "Deploy Batch", "#A3135B")
    draw_section_label(draw, 1876, 362, "Monitor + Govern", "#149C8A")

    # Raw source card.
    process_box(
        draw,
        (105, 436, 375, 762),
        "Raw data",
        "4 CSV domains\nattributes\nfinancials\nclickstream\nLMS loan daily",
        COLORS["orange"],
        fill="#FFF8EC",
    )
    draw.text((132, 790), "Source checks: test -f", font=font(18, True), fill=COLORS["amber"])

    # Medallion stores.
    cylinder(draw, (425, 425, 630, 595), "#F2C07E", "#7A3D12", "Bronze", "Raw-like Parquet\npartitioned snapshots", body_size=18)
    cylinder(draw, (425, 635, 630, 805), "#DDE4EA", "#4D5963", "Silver", "Cleaned tables\nsource conformance\naudit log", body_size=17)
    cylinder(draw, (425, 845, 630, 1015), "#F2C94C", "#8A6400", "Gold", "feature_store\nlabel_store\nmodel features", body_size=17)
    arrow(draw, (375, 600), (425, 510), COLORS["ink"], 4)
    arrow(draw, (530, 598), (530, 635), COLORS["muted"], 3)
    arrow(draw, (530, 808), (530, 845), COLORS["muted"], 3)

    # Leakage boundary callout.
    rounded_card(draw, (675, 845, 1045, 1015), fill=COLORS["soft_red"], outline="#FFB5B5", radius=18, shadow=False)
    draw.text((700, 872), "Leakage boundary", font=font(24, True), fill=COLORS["red"])
    draw_wrapped(
        draw,
        (700, 913),
        "Repayment fields such as dpd, due_amt and balance create labels only. They are never model predictors.",
        font(19),
        COLORS["ink"],
        320,
        line_gap=4,
    )
    arrow(draw, (630, 930), (675, 930), COLORS["red"], 4, dashed=True)

    # Model development.
    process_box(
        draw,
        (720, 436, 1015, 598),
        "Candidate search",
        "36 candidates\n4 families x 3 variants x 3 feature budgets",
        COLORS["purple"],
        fill="#F6F0FF",
    )
    process_box(
        draw,
        (1060, 436, 1355, 598),
        "Governed selection",
        "P0 recall gate >= 0.70\nP1 PR-AUC ranking\nsimplicity penalty",
        COLORS["blue"],
        fill=COLORS["soft_blue"],
    )
    process_box(
        draw,
        (890, 645, 1240, 785),
        "Champion",
        "HGB Compact\nvalidation recall 0.769\nvalidation PR-AUC 0.654",
        COLORS["green"],
        fill=COLORS["soft_green"],
    )
    arrow(draw, (630, 930), (720, 520), COLORS["ink"], 4)
    arrow(draw, (1015, 517), (1060, 517), COLORS["ink"], 4)
    arrow(draw, (1208, 598), (1110, 645), COLORS["ink"], 4)

    # Model bank and artifacts.
    rounded_card(draw, (1285, 650, 1575, 820), fill="#FFFFFF", outline="#BFD0E8", radius=18)
    draw.text((1312, 678), "Model bank", font=font(26, True), fill=COLORS["navy"])
    draw_wrapped(
        draw,
        (1312, 720),
        "champion_model.pkl\nmodel_registry.json\nmodel_evaluation",
        font(21),
        COLORS["muted"],
        235,
        line_gap=5,
    )
    arrow(draw, (1240, 716), (1285, 716), COLORS["ink"], 4)

    # Deployment / inference.
    process_box(
        draw,
        (1620, 436, 1850, 598),
        "Resolve month",
        "snapshotdate from Airflow\n{{ ds }} or manual config",
        "#A3135B",
        fill="#FFF0F7",
    )
    process_box(
        draw,
        (1620, 650, 1850, 820),
        "Batch inference",
        "Load champion\napply frozen preprocessing\nscore selected month",
        "#A3135B",
        fill="#FFF0F7",
    )
    cylinder(
        draw,
        (1625, 840, 1855, 1022),
        "#F2C94C",
        "#8A6400",
        "Gold output",
        "model_predictions\ndefault_probability\npredicted_label\nmodel_version",
        body_size=16,
    )
    arrow(draw, (1575, 716), (1620, 716), COLORS["ink"], 4)
    arrow(draw, (1735, 598), (1735, 650), COLORS["ink"], 4)
    arrow(draw, (1738, 820), (1738, 840), COLORS["ink"], 4)

    # Monitoring and governance.
    process_box(
        draw,
        (1915, 430, 2230, 590),
        "Monitoring metrics",
        "Performance: P0 recall, P1 PR-AUC after labels mature\nStability: PSI score drift, CSI feature drift immediately",
        "#149C8A",
        fill="#E9FBF8",
    )
    small_store(
        draw,
        (1954, 665, 2190, 800),
        "Gold monitoring",
        "model_monitoring\nfeature_drift_monitoring\nP0/P1 + PSI/CSI",
    )
    process_box(
        draw,
        (1915, 855, 2215, 1022),
        "Dashboard + SOP",
        "dashboard port 8050\nreads Gold monitoring\ndetection-only review",
        COLORS["blue"],
        fill=COLORS["soft_blue"],
    )
    arrow(draw, (1855, 902), (1954, 735), COLORS["ink"], 4)
    arrow(draw, (2072, 590), (2072, 665), COLORS["ink"], 4)
    arrow(draw, (2072, 800), (2072, 855), COLORS["ink"], 4)
    # Bottom evidence band.
    rounded_card(draw, (70, 1070, 2330, 1282), fill="#FFFFFF", outline="#CBD5E1", radius=22)
    draw.text((105, 1100), "Key assignment evidence", font=font(26, True), fill=COLORS["navy"])

    evidence = [
        ("Gold predictions", "datamart/gold/model_predictions"),
        ("Gold monitoring", "model_monitoring + feature_drift_monitoring"),
        ("Version control", "model version stamped on each prediction"),
        ("Backfill control", "one Airflow run per month, Jan-Dec 2024"),
        ("Governance rule", "P0 eligibility, P1 winner, penalties for complexity"),
    ]
    x = 105
    for idx, (title, body) in enumerate(evidence):
        bw = 420 if idx < 4 else 450
        rounded_card(draw, (x, 1152, x + bw, 1248), fill=COLORS["soft_blue"] if idx % 2 == 0 else "#F8FAFC", outline="#D7DFEB", radius=14, shadow=False)
        draw.text((x + 22, 1171), title, font=font(21, True), fill=COLORS["ink"])
        draw_wrapped(draw, (x + 22, 1204), body, font(17), COLORS["muted"], bw - 44, line_gap=2)
        x += bw + 22

    # Footnote.
    draw.text(
        (105, 1305),
        "Diagram reflects actual project components: scripts/run_bronze.py, run_silver.py, run_gold.py, ensure_champion.py, run_inference.py and run_monitoring.py.",
        font=font(16),
        fill=COLORS["muted"],
    )

    img.save(OUT_PATH, quality=95)
    print(OUT_PATH)


if __name__ == "__main__":
    main()
