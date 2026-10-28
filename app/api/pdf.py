"""Printable checklist PDF (fpdf2, offline, core fonts)."""

from __future__ import annotations

from fpdf import FPDF

from app.core.checklist import Checklist

_REPL = {"—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "•": "-", "₹": "Rs "}


def _t(s: str) -> str:
    for a, b in _REPL.items():
        s = s.replace(a, b)
    return s.encode("latin-1", "replace").decode("latin-1")


def checklist_pdf(cl: Checklist, family_name: str) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.multi_cell(0, 9, _t(f"If something happens: {cl.scenario_label}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 12)
    pdf.multi_cell(0, 7, _t(f"{family_name} - for {cl.subject_name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_fill_color(255, 244, 214)
    pdf.set_font("Helvetica", "I", 10)
    pdf.multi_cell(0, 6, _t("DEMO with synthetic data. " + cl.disclaimer), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    for s in cl.steps:
        pdf.set_font("Helvetica", "B", 12)
        flag = "  [BLOCKED]" if s.blocked else ""
        pdf.multi_cell(0, 7, _t(f"{s.order}. {s.text}{flag}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5.5, _t("Who acts: " + ", ".join(s.actors)), new_x="LMARGIN", new_y="NEXT")
        if s.required_documents:
            pdf.multi_cell(0, 5.5, _t("Documents: " + "; ".join(s.required_documents)), new_x="LMARGIN", new_y="NEXT")
        for n in s.notes:
            pdf.multi_cell(0, 5.5, _t("Note: " + n), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    return bytes(pdf.output())
