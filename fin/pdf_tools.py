"""Annual-report PDF reading: page text, section detection, key facts, statement line items, OCR."""
from __future__ import annotations

import io
import re
from collections import Counter

import pandas as pd

from .parsers import canonical, extract_line_items, detect_unit

SECTION_PATTERNS = {
    "Chairman's message": r"chair(man|person)['’]?s?\s+(message|statement|letter|speech|address)|message from the chair|letter to (the )?(shareholders|stakeholders)",
    "Business overview": r"business overview|company overview|about (us|the company)|who we are|corporate overview|our business",
    "Management discussion & analysis": r"management['’]?s?\s+discussion\s+(and|&)\s+analysis|\bmd&a\b",
    "Directors' report": r"(board|directors)['’]?s?\s+report",
    "Risk management": r"risk\s+management|risks?\s+(and|&)\s+(concerns|mitigation)|principal risks|key risks",
    "Corporate governance": r"corporate governance",
    "Sustainability / BRSR": r"business responsibility|sustainability report|\bbrsr\b|\besg\b",
    "CSR": r"corporate social responsibility|\bcsr\b",
    "Auditor's report": r"independent auditor['’]?s?\s+report",
    "Balance sheet": r"^\s*(consolidated |standalone )?balance sheet",
    "Profit & loss": r"statement of profit\s*(and|&)\s*loss|profit and loss account|income statement",
    "Cash flow": r"cash\s*flow\s*statement|statement of cash flows?",
}

STOP = set("""a an the and or of to in on for with by from as at is are was were be been being it its this that these those
which who whom their our we us you your they them he she his her not no nor but if then than so such into over under
also may can could would should will shall have has had do does did per about during across between within without
more most less other any all each both year years company limited ltd""".split())


def extract_pages(data: bytes, max_pages: int = 600) -> list[str]:
    """Fast text extraction with pypdfium2 (falls back to pdfplumber)."""
    pages: list[str] = []
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(io.BytesIO(data))
        for i in range(min(len(pdf), max_pages)):
            tp = pdf[i].get_textpage()
            pages.append(tp.get_text_range() or "")
        return pages
    except Exception:
        pass
    import pdfplumber
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for i, pg in enumerate(pdf.pages[:max_pages]):
            pages.append(pg.extract_text() or "")
    return pages


def find_sections(pages: list[str]) -> dict[str, dict]:
    """Locate the best page for each heading. Returns {name: {start, end, text}}."""
    n = len(pages)
    cands: dict[str, list[int]] = {k: [] for k in SECTION_PATTERNS}
    for pi, txt in enumerate(pages):
        head_lines = [ln.strip() for ln in txt.splitlines()[:8] if ln.strip()]
        for name, pat in SECTION_PATTERNS.items():
            rx = re.compile(pat, re.I)
            hit = any(len(ln) < 90 and rx.search(ln) for ln in head_lines)
            if hit:
                cands[name].append(pi)
    chosen: dict[str, int] = {}
    for name, pgs in cands.items():
        if not pgs:
            continue
        # skip contents pages (lots of dotted leaders / page numbers) and very short pages
        def score(pi):
            t = pages[pi]
            toc_pen = 1500 if len(re.findall(r"\.{4,}|\s\d{1,3}\s*$", t, re.M)) > 12 else 0
            return len(t) - toc_pen
        chosen[name] = max(pgs, key=score)
    order = sorted(chosen.items(), key=lambda kv: kv[1])
    out = {}
    starts = [p for _, p in order]
    for i, (name, start) in enumerate(order):
        nxt = [p for p in starts if p > start]
        end = min(nxt[0] if nxt else n, start + 14)
        out[name] = {"start": start + 1, "end": end, "text": "\n".join(pages[start:end])}
    return out


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9“\"'])", text)
    return [s.strip() for s in parts if 40 <= len(s.strip()) <= 420]


def summarise(text: str, n: int = 5) -> list[str]:
    """Frequency-based extractive summary (no external model)."""
    sents = split_sentences(text)
    if len(sents) <= n:
        return sents
    words = [w for w in re.findall(r"[a-z][a-z\-]{2,}", text.lower()) if w not in STOP]
    freq = Counter(words)
    top = max(freq.values()) if freq else 1
    scored = []
    for i, s in enumerate(sents):
        ws = [w for w in re.findall(r"[a-z][a-z\-]{2,}", s.lower()) if w not in STOP]
        if not ws:
            continue
        sc = sum(freq[w] / top for w in ws) / (len(ws) ** 0.6)
        if re.search(r"\d", s):
            sc *= 1.1
        scored.append((sc, i, s))
    best = sorted(scored, reverse=True)[:n]
    return [s for _, _, s in sorted(best, key=lambda x: x[1])]


THEMES = {
    "Outlook & guidance": r"outlook|expect|going forward|next (financial )?year|guidance|anticipate|we (plan|aim|intend)",
    "Strategy & growth": r"strateg|expansion|capacity|new (plant|facility|product)|acquisition|market share|diversif",
    "Risks": r"\brisk|volatil|uncertain|headwind|competition|regulat|disruption|concentration",
    "Capital allocation": r"dividend|capex|capital expenditure|buyback|borrowing|deleverag|debt|invest",
    "People & ESG": r"employee|talent|safety|sustainab|emission|carbon|csr|diversity|governance",
    "Segments & customers": r"segment|customer|export|geograph|vertical|order book|portfolio",
}


def theme_sentences(text: str, per_theme: int = 3) -> dict[str, list[str]]:
    sents = split_sentences(text)
    out, used = {}, set()
    for theme, pat in THEMES.items():
        rx = re.compile(pat, re.I)
        hits = [s for s in sents if rx.search(s) and s not in used]
        hits.sort(key=lambda s: (-(1 if re.search(r"\d", s) else 0), -len(s)))
        if hits:
            out[theme] = hits[:per_theme]
            used.update(hits[:per_theme])
    return out


def key_facts(text: str) -> list[tuple[str, str]]:
    """Regex-mined facts that typically appear in an annual report."""
    facts: list[tuple[str, str]] = []
    text = re.sub(r"\s+", " ", text)

    def grab(label, pattern, fmt=lambda m: m.group(0), flags=re.I):
        m = re.search(pattern, text, flags)
        if m:
            facts.append((label, fmt(m)))

    grab("Employees", r"([\d,]{3,})\s+(permanent\s+|full[- ]time\s+)?employees", lambda m: m.group(1) + " employees")
    grab("Manufacturing plants", r"(\d{1,3})\s+(manufacturing\s+)?(plants|facilities|factories)", lambda m: m.group(0))
    grab("Export share", r"exports?\s+(contribute[sd]?|account[s]? for|represent[s]?)\s+(about|around|approximately)?\s*(\d+(\.\d+)?)\s*(%|percent|per cent)",
         lambda m: m.group(0))
    grab("Countries served", r"(\d{2,3})\s*\+?\s*countries", lambda m: m.group(0))
    grab("Dividend per share", r"dividend of\s*(₹|rs\.?|inr)\s*([\d.]+)\s*per", lambda m: f"₹{m.group(2)} per share")
    grab("Credit rating", r"(CRISIL|ICRA|CARE|India Ratings|Fitch|Moody'?s|S&P)\s+[A-Z]{1,3}[+\-]?(\s*/\s*(Stable|Positive|Negative))?",
         lambda m: m.group(0), flags=0)
    grab("Board size", r"board comprises\s+(\d+)\s+directors[^.]*", lambda m: m.group(0))
    grab("Customer concentration", r"top\s+(\d+|five|ten|three)\s+customers[^.]*?(\d+(\.\d+)?)\s*(%|percent|per cent)[^.]*", lambda m: m.group(0))
    grab("Guidance", r"(revenue|sales|volume)\s+growth\s+of\s+[\d.\- ]+(to\s+[\d.]+)?\s*(%|percent|per cent)", lambda m: m.group(0))
    return facts


def statement_lines(pages: list[str], sections: dict) -> tuple[list[str], str]:
    """Lines from pages that look like the three primary statements, plus a detected unit."""
    keys = [k for k in ("Balance sheet", "Profit & loss", "Cash flow") if k in sections]
    lines, blob = [], ""
    seen: set = set()
    for k in keys:
        s = sections[k]
        # statements are short; take the start page plus the following page
        for pi in range(s["start"] - 1, min(s["start"] + 1, len(pages))):
            if pi in seen:
                continue
            seen.add(pi)
            blob += pages[pi] + "\n"
            lines += [ln for ln in pages[pi].splitlines()]
    if not lines:  # fall back to scanning every page for statement-like lines
        for pg in pages:
            if re.search(r"total (assets|equity and liabilities)|profit before tax|operating activities", pg, re.I):
                lines += pg.splitlines()
                blob += pg + "\n"
    return lines, detect_unit(blob)


def detect_year_labels(pages: list[str]) -> list[str]:
    """Look for 'March 31, 2025' / 'FY 2024-25' style column headings in statement pages."""
    from .parsers import period_label
    txt = "\n".join(pages)
    found = re.findall(r"(?:March|Mar)\s*\.?\s*31\s*,?\s*(20\d{2})", txt, re.I)
    if found:
        yrs = sorted(set(found), reverse=True)[:2]
        return [period_label(y) for y in yrs]
    found = re.findall(r"20\d{2}\s*[-–]\s*(\d{2,4})", txt)
    if found:
        yrs = sorted(set(int(y) % 100 for y in found), reverse=True)[:2]
        return [f"FY{y:02d}" for y in yrs]
    found = re.findall(r"year ended\s+(20\d{2})", txt, re.I)
    if found:
        yrs = sorted(set(found), reverse=True)[:2]
        return [period_label(y) for y in yrs]
    return []


# ----------------------------------------------------------------------------
# OCR for screenshots
# ----------------------------------------------------------------------------
def ocr_image(data: bytes) -> tuple[list[str], str | None]:
    """OCR an image into text lines. Returns (lines, error_message)."""
    try:
        from PIL import Image, ImageOps
        import pytesseract
    except Exception as e:  # pragma: no cover
        return [], f"OCR libraries missing: {e}"
    try:
        img = Image.open(io.BytesIO(data)).convert("L")
        if img.width < 1600:
            scale = 1600 / img.width
            img = img.resize((int(img.width * scale), int(img.height * scale)))
        img = ImageOps.autocontrast(img)
        txt = pytesseract.image_to_string(img, config="--psm 6")
        return [ln for ln in txt.splitlines() if ln.strip()], None
    except Exception as e:
        msg = str(e)
        if "tesseract" in msg.lower():
            msg = ("Tesseract OCR is not installed or not on PATH. Install it (Windows: "
                   "https://github.com/UB-Mannheim/tesseract/wiki) and restart, or set its path in Settings. "
                   f"Details: {e}")
        return [], msg


def lines_to_items(lines: list[str]) -> pd.DataFrame:
    return extract_line_items(lines)
