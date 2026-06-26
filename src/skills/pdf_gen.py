"""
PDF generation for Pixel Assistant.
Requires: pip install fpdf2

Usage (internal): generate_pdf(title, sections, theme, out_dir) -> Path
"""
import subprocess
import sys
from pathlib import Path

try:
    from fpdf import FPDF
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "fpdf2", "-q"])
    from fpdf import FPDF


# ── Themes ─────────────────────────────────────────────────────────────────────

THEMES = {
    "dark": {
        "bg":       (15, 20, 40),
        "title":    (64, 128, 255),
        "heading":  (64, 128, 255),
        "body":     (220, 235, 255),
        "accent":   (64, 128, 255),
    },
    "light": {
        "bg":       (255, 255, 255),
        "title":    (26, 26, 46),
        "heading":  (40, 120, 200),
        "body":     (33, 33, 33),
        "accent":   (40, 120, 200),
    },
    "corporate": {
        "bg":       (245, 247, 250),
        "title":    (0, 51, 102),
        "heading":  (0, 102, 204),
        "body":     (34, 34, 34),
        "accent":   (0, 102, 204),
    },
    "modern": {
        "bg":       (30, 32, 48),
        "title":    (0, 229, 255),
        "heading":  (0, 229, 255),
        "body":     (224, 224, 224),
        "accent":   (0, 229, 255),
    },
    "warm": {
        "bg":       (255, 248, 240),
        "title":    (139, 69, 19),
        "heading":  (210, 105, 30),
        "body":     (59, 26, 0),
        "accent":   (210, 105, 30),
    },
}


class _ThemedPDF(FPDF):
    def __init__(self, theme_name: str, doc_title: str):
        super().__init__()
        self.t = THEMES.get(theme_name, THEMES["light"])
        self.doc_title = doc_title
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        r, g, b = self.t["bg"]
        self.set_fill_color(r, g, b)
        self.rect(0, 0, 210, 297, "F")

    def footer(self):
        self.set_y(-12)
        r, g, b = self.t["body"]
        self.set_text_color(r, g, b)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def generate_pdf(
    title: str,
    sections: list[dict],   # [{"heading": str, "bullets": [str]}]
    theme: str = "light",
    out_dir: Path = None,
) -> Path:
    """
    sections = [{"heading": "Introduction", "bullets": ["Point 1", ...]}, ...]
    Returns path to the saved .pdf file.
    """
    pdf = _ThemedPDF(theme, title)
    t   = THEMES.get(theme, THEMES["light"])

    pdf.add_page()

    # ── Cover ─────────────────────────────────────────────────────────────
    # background already applied in header()

    # Title
    r, g, b = t["title"]
    pdf.set_text_color(r, g, b)
    pdf.set_font("Helvetica", "B", 32)
    pdf.ln(40)
    pdf.multi_cell(0, 12, title, align="C")

    # Accent rule
    ra, ga, ba = t["accent"]
    pdf.set_draw_color(ra, ga, ba)
    pdf.set_line_width(0.8)
    pdf.ln(4)
    pdf.line(40, pdf.get_y(), 170, pdf.get_y())

    # ── Sections ──────────────────────────────────────────────────────────
    for section in sections:
        pdf.add_page()

        # Section heading
        rh, gh, bh = t["heading"]
        pdf.set_text_color(rh, gh, bh)
        pdf.set_font("Helvetica", "B", 20)
        pdf.ln(6)
        pdf.multi_cell(0, 10, section.get("heading", ""), align="L")

        # Accent line
        pdf.set_draw_color(ra, ga, ba)
        pdf.set_line_width(0.5)
        pdf.line(10, pdf.get_y() + 1, 200, pdf.get_y() + 1)
        pdf.ln(6)

        # Bullets
        rb, gb, bb = t["body"]
        pdf.set_text_color(rb, gb, bb)
        pdf.set_font("Helvetica", size=13)
        for bullet in section.get("bullets", []):
            pdf.set_x(14)
            pdf.multi_cell(0, 8, f"\u2022  {bullet}", align="L")
            pdf.ln(2)

    if out_dir is None:
        out_dir = Path(__file__).parent.parent.parent / "generated"
    out_dir.mkdir(exist_ok=True)

    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)[:40]
    out_path   = out_dir / f"{safe_title}_{theme}.pdf"
    pdf.output(str(out_path))
    return out_path
