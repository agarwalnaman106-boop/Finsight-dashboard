"""Parsers: Screener.in export, generic Excel/CSV, text lines (annual-report PDFs, OCR)."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import datetime, date

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# Canonical line items (Screener naming is used as the canonical schema)
# ----------------------------------------------------------------------------
PL_ITEMS = [
    "Sales", "Raw Material Cost", "Change in Inventory", "Power and Fuel",
    "Other Mfr. Exp", "Employee Cost", "Selling and admin", "Other Expenses",
    "Other Income", "Depreciation", "Interest", "Profit before tax", "Tax",
    "Net profit", "Dividend Amount",
]
BS_ITEMS = [
    "Equity Share Capital", "Reserves", "Borrowings", "Other Liabilities",
    "Total Liabilities", "Net Block", "Capital Work in Progress", "Investments",
    "Other Assets", "Total Assets", "Receivables", "Inventory", "Cash & Bank",
    "No. of Equity Shares",
]
CF_ITEMS = [
    "Cash from Operating Activity", "Cash from Investing Activity",
    "Cash from Financing Activity", "Net Cash Flow",
]
STATEMENT_OF = {**{i: "pl" for i in PL_ITEMS}, **{i: "bs" for i in BS_ITEMS}, **{i: "cf" for i in CF_ITEMS}}

# Ordered: specific patterns first.
ALIASES: list[tuple[str, str]] = [
    ("Profit before tax", r"profit\s*(/\(loss\)\s*)?before\s*(exceptional.*)?tax|^pbt$|profit before income tax"),
    ("Net profit", r"^net profit|profit after tax|^pat$|profit\s*(/\(loss\))?\s*for the (year|period)|profit/\(loss\) for|net income|profit attributable"),
    ("Tax", r"^tax(es)?( expense)?s?$|^total tax|income tax expense|tax expense|provision for tax"),
    ("Other Income", r"other income"),
    ("Sales", r"^(net )?sales$|revenue from operations|^total revenue$|^revenue$|net revenue|turnover|total income from operations"),
    ("Raw Material Cost", r"raw material|cost of materials|cost of goods sold|^cogs$|purchases? of stock"),
    ("Change in Inventory", r"changes? in inventor"),
    ("Power and Fuel", r"power (and|&) fuel"),
    ("Other Mfr. Exp", r"other mfr|manufacturing exp"),
    ("Employee Cost", r"employee|staff cost|personnel|salaries"),
    ("Selling and admin", r"selling|administrat"),
    ("Other Expenses", r"^other expenses?$"),
    ("Depreciation", r"depreciation|amorti[sz]ation"),
    ("Interest", r"^interest( expense)?$|finance costs?|interest expense|interest and finance"),
    ("Dividend Amount", r"^dividend( amount| paid)?$|dividends? paid"),
    ("Equity Share Capital", r"equity share capital|^share capital"),
    ("Reserves", r"^reserves|other equity|reserves and surplus"),
    ("Borrowings", r"^borrowings?$|total borrowings|total debt|^debt$"),
    ("Total Liabilities", r"^total liabilities$|total equity and liabilities|^total equity & liabilities"),
    ("Total Assets", r"^total assets$"),
    ("Other Liabilities", r"^other liabilities$"),
    ("Net Block", r"net block|property,? plant|fixed assets"),
    ("Capital Work in Progress", r"capital work|^cwip$"),
    ("Investments", r"^(non-?current )?investments?$"),
    ("Other Assets", r"^other assets$"),
    ("Receivables", r"receivable|debtors"),
    ("Inventory", r"^inventor(y|ies)$"),
    ("Cash & Bank", r"cash (and|&) (bank|cash equivalents)|cash and cash equivalents|^cash & bank"),
    ("No. of Equity Shares", r"no\.? of equity shares|number of (equity )?shares"),
    ("Cash from Operating Activity", r"operating activit|cash from operat"),
    ("Cash from Investing Activity", r"investing activit"),
    ("Cash from Financing Activity", r"financing activit"),
    ("Net Cash Flow", r"net cash flow|net (increase|decrease)|net change in cash"),
]
_ALIAS_RX = [(k, re.compile(p, re.I)) for k, p in ALIASES]


def canonical(label: str) -> str | None:
    s = re.sub(r"\s+", " ", str(label)).strip().strip(":").strip()
    s = re.sub(r"^\(?[a-z]\)\s*", "", s, flags=re.I)  # (a) prefixes
    for key, rx in _ALIAS_RX:
        if rx.search(s):
            return key
    return None


# ----------------------------------------------------------------------------
# Company container
# ----------------------------------------------------------------------------
@dataclass
class Company:
    name: str = "Company"
    meta: dict = field(default_factory=dict)  # current_price, market_cap, face_value, shares_cr
    pl: pd.DataFrame = field(default_factory=pd.DataFrame)   # rows=items, cols=periods
    bs: pd.DataFrame = field(default_factory=pd.DataFrame)
    cf: pd.DataFrame = field(default_factory=pd.DataFrame)
    price: pd.Series = field(default_factory=pd.Series)
    quarters: pd.DataFrame = field(default_factory=pd.DataFrame)
    sources: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    @property
    def periods(self) -> list:
        cols = []
        for df in (self.pl, self.bs, self.cf):
            for c in df.columns:
                if c not in cols:
                    cols.append(c)
        return sorted(cols, key=period_sort_key)

    def empty(self) -> bool:
        return self.pl.empty and self.bs.empty and self.cf.empty

    def tables(self) -> dict:
        return {"Profit & Loss": self.pl, "Balance Sheet": self.bs, "Cash Flow": self.cf}


def period_label(v) -> str:
    """datetime / year-ish value -> FY24 / Sep 24 / FY2024 style label."""
    if isinstance(v, (datetime, date, pd.Timestamp)):
        d = pd.Timestamp(v)
        return f"FY{d.year % 100:02d}" if d.month == 3 else d.strftime("%b %y")
    s = str(v).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return period_label(datetime(int(m[1]), int(m[2]), int(m[3])))
    m = re.fullmatch(r"(?:(?:FY|F\.Y\.?)\s*)?(20\d{2}|19\d{2})\s*[-–/]\s*(\d{2}|\d{4})", s, re.I)
    if m:
        return f"FY{int(m[2]) % 100:02d}"
    m = re.search(r"(?:FY|F\.Y\.?)\s*'?(\d{2,4})(?:\s*[-–/]\s*(\d{2,4}))?", s, re.I)
    if m:
        a, b = m[1], m[2]
        yr = int(b if b else a)
        if b and len(b) == 2:
            yr = int(b)
        elif len(a) == 4 and not b:
            yr = int(a)
        elif b and len(b) == 4:
            yr = int(b)
        return f"FY{yr % 100:02d}"
    m = re.search(r"(Mar|Jun|Sep|Dec|March|June|September|December)[a-z]*[\s,\-]*(?:\d{1,2}[,\s\-]+)?(\d{2,4})", s, re.I)
    if m:
        mon = m[1][:3].title()
        y = int(m[2]) % 100
        return f"FY{y:02d}" if mon == "Mar" else f"{mon} {y:02d}"
    m = re.fullmatch(r"(19|20)\d{2}", s)
    if m:
        return f"FY{int(s) % 100:02d}"
    return s


def period_sort_key(p: str):
    m = re.match(r"FY(\d{2})", str(p))
    if m:
        return (int(m[1]), 3)
    m = re.match(r"([A-Za-z]{3}) (\d{2})", str(p))
    if m:
        mon = {"Mar": 3, "Jun": 6, "Sep": 9, "Dec": 12}.get(m[1], 12)
        return (int(m[2]), mon)
    return (999, 0)


def _num(x):
    if x is None:
        return np.nan
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    s = str(x).strip().replace(",", "").replace("₹", "").replace("Rs.", "").replace("$", "")
    if s in ("", "-", "–", "—", "nil", "Nil", "NA", "N/A", "n/a"):
        return np.nan
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = s.replace("%", "")
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return np.nan


def _is_dateish(v) -> bool:
    if isinstance(v, (datetime, date, pd.Timestamp)):
        return True
    s = str(v).strip()
    return bool(re.search(r"(19|20)\d{2}", s)) and len(s) <= 40 and not re.search(r"[a-z]{6,}\s+[a-z]{4,}", s, re.I)


def _frame(rows: dict, cols: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, index=cols).T
    df = df.apply(pd.to_numeric, errors="coerce")
    df = df.loc[:, ~df.columns.duplicated(keep="last")]
    return df


# ----------------------------------------------------------------------------
# Screener.in "Data Sheet"
# ----------------------------------------------------------------------------
def parse_screener(data: bytes) -> Company | None:
    """Parse the Excel export from screener.in (sheet 'Data Sheet'). Returns None if not that format."""
    import openpyxl
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    except Exception:
        return None
    ws = None
    for name in wb.sheetnames:
        if name.strip().lower() == "data sheet":
            ws = wb[name]
    if ws is None:
        return None
    rows = [[c for c in r] for r in ws.iter_rows(values_only=True)]
    co = Company(sources=["Screener.in Excel"])
    section = None
    dates: dict[str, list] = {}
    data_rows: dict[str, dict] = {"PL": {}, "Q": {}, "BS": {}, "CF": {}}
    price_vals = None
    derived: dict = {}
    seen_total = 0
    for r in rows:
        if not r or r[0] is None:
            continue
        label = str(r[0]).strip()
        up = label.upper().rstrip(":")
        vals = list(r[1:])
        if up == "COMPANY NAME":
            co.name = str(vals[0]).strip() if vals and vals[0] else co.name
            continue
        if up.startswith("META"):
            section = "META"
            continue
        if up in ("PROFIT & LOSS", "PROFIT AND LOSS"):
            section = "PL"; seen_total = 0; continue
        if up == "QUARTERS":
            section = "Q"; continue
        if up == "BALANCE SHEET":
            section = "BS"; seen_total = 0; continue
        if up == "CASH FLOW":
            section = "CF"; continue
        if up == "DERIVED":
            section = "DERIVED"; continue
        if up == "PRICE":
            section = "PRICE"
            nums = [_num(v) for v in vals]
            if any(not np.isnan(n) for n in nums):
                price_vals = nums
            continue
        if section == "META":
            v = vals[0] if vals else None
            key = up.lower()
            if "number of shares" in key:
                co.meta["shares_raw"] = _num(v)
            elif "face value" in key:
                co.meta["face_value"] = _num(v)
            elif "current price" in key:
                co.meta["current_price"] = _num(v)
            elif "market cap" in key:
                co.meta["market_cap"] = _num(v)
            continue
        if up == "REPORT DATE":
            dates[section] = [period_label(v) if v is not None and v != "" else None for v in vals]
            continue
        if section in ("PL", "Q", "BS", "CF"):
            if section == "BS" and up == "TOTAL":
                seen_total += 1
                label = "Total Liabilities" if seen_total == 1 else "Total Assets"
            data_rows[section][label] = [_num(v) for v in vals]
        elif section == "DERIVED":
            derived[label] = [_num(v) for v in vals]
        elif section == "PRICE" and price_vals is None:
            nums = [_num(v) for v in vals]
            if any(not np.isnan(n) for n in nums):
                price_vals = nums

    def build(sec):
        cols = dates.get(sec) or []
        keep = [i for i, c in enumerate(cols) if c]
        if not keep:
            return pd.DataFrame()
        labels = [cols[i] for i in keep]
        d = {}
        for item, vs in data_rows[sec].items():
            vs = (vs + [np.nan] * len(cols))[: len(cols)]
            d[item] = [vs[i] for i in keep]
        return _frame(d, labels)

    co.pl, co.bs, co.cf, co.quarters = build("PL"), build("BS"), build("CF"), build("Q")
    if price_vals is not None and dates.get("PL"):
        cols = dates["PL"]
        pv = (price_vals + [np.nan] * len(cols))[: len(cols)]
        co.price = pd.Series({c: v for c, v in zip(cols, pv) if c}, dtype=float)
    adj = derived.get("Adjusted Equity Shares in Cr")
    if adj and dates.get("BS"):
        cols = dates["BS"]
        adj = (adj + [np.nan] * len(cols))[: len(cols)]
        co.meta["adj_shares_series"] = {c: v for c, v in zip(cols, adj) if c and not np.isnan(v)}
    co = normalise_shares(co)
    if co.pl.empty and co.bs.empty:
        return None
    return co


def normalise_shares(co: Company) -> Company:
    """Bring share counts to Crores (Screener stores absolute numbers in 'No. of Equity Shares')."""
    if "No. of Equity Shares" in co.bs.index:
        s = co.bs.loc["No. of Equity Shares"]
        if s.dropna().abs().max() > 1e5:
            co.bs.loc["No. of Equity Shares"] = s / 1e7
    raw = co.meta.get("shares_raw")
    if raw and not np.isnan(raw):
        co.meta["shares_cr"] = raw / 1e7 if raw > 1e5 else raw
    if "shares_cr" not in co.meta:
        if "No. of Equity Shares" in co.bs.index:
            s = co.bs.loc["No. of Equity Shares"].dropna()
            if len(s):
                co.meta["shares_cr"] = float(s.iloc[-1])
    return co


# ----------------------------------------------------------------------------
# Generic Excel / CSV
# ----------------------------------------------------------------------------
def _read_grid(data: bytes, filename: str) -> list[tuple[str, list[list]]]:
    name = filename.lower()
    if name.endswith((".csv", ".txt")):
        for enc in ("utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(io.BytesIO(data), header=None, encoding=enc, sep=None, engine="python")
                break
            except Exception:
                df = None
        if df is None:
            return []
        return [("csv", df.where(df.notna(), None).values.tolist())]
    if name.endswith(".tsv"):
        df = pd.read_csv(io.BytesIO(data), header=None, sep="\t")
        return [("tsv", df.where(df.notna(), None).values.tolist())]
    xl = pd.ExcelFile(io.BytesIO(data))
    out = []
    for sh in xl.sheet_names:
        df = xl.parse(sh, header=None)
        out.append((sh, df.where(df.notna(), None).values.tolist()))
    return out


def parse_generic(data: bytes, filename: str) -> Company:
    """Parse any Excel/CSV where column A holds line-item names and a header row holds years/dates.

    Also supports 'long' layout (one row per period, items as columns) by auto-transposing.
    """
    co = Company(sources=[f"Upload: {filename}"])
    pl, bs, cf, extra = {}, {}, {}, {}
    cols_union: list[str] = []
    for sheet, grid in _read_grid(data, filename):
        if not grid:
            continue
        grid = [list(r) for r in grid]
        hdr_idx, hdr_cols = None, None
        for i, r in enumerate(grid[:40]):
            cells = [(j, c) for j, c in enumerate(r) if j > 0 and c is not None and _is_dateish(c)]
            if len(cells) >= 2:
                hdr_idx, hdr_cols = i, cells
                break
        if hdr_idx is None:
            # maybe transposed: first column holds periods
            first_col = [(i, r[0]) for i, r in enumerate(grid[:60]) if r and r[0] is not None and _is_dateish(r[0])]
            if len(first_col) >= 2:
                head_row = None
                for i in range(first_col[0][0] - 1, -1, -1):
                    if any(c is not None for c in grid[i]):
                        head_row = i
                        break
                if head_row is not None:
                    heads = grid[head_row]
                    t = [[heads[j] if j < len(heads) else None] + [grid[i][j] if j < len(grid[i]) else None for i, _ in first_col]
                         for j in range(1, len(heads))]
                    pers = [period_label(v) for _, v in first_col]
                    grid = [[None] + pers] + t
                    hdr_idx = 0
                    hdr_cols = [(j, c) for j, c in enumerate(grid[0]) if j > 0]
        if hdr_idx is None:
            continue
        labels = {j: period_label(c) for j, c in hdr_cols}
        for lab in labels.values():
            if lab not in cols_union:
                cols_union.append(lab)
        for r in grid[hdr_idx + 1:]:
            if not r or r[0] is None:
                continue
            name = str(r[0]).strip()
            vals = {labels[j]: _num(r[j]) for j in labels if j < len(r)}
            if all(np.isnan(v) for v in vals.values()):
                continue
            key = canonical(name)
            if key is None:
                extra[name] = vals
                continue
            tgt = {"pl": pl, "bs": bs, "cf": cf}[STATEMENT_OF[key]]
            if key not in tgt:  # first match wins
                tgt[key] = vals
    cols_union = sorted(cols_union, key=period_sort_key)
    co.pl = _frame(pl, cols_union) if pl else pd.DataFrame()
    co.bs = _frame(bs, cols_union) if bs else pd.DataFrame()
    co.cf = _frame(cf, cols_union) if cf else pd.DataFrame()
    for df_name in ("pl", "bs", "cf"):
        df = getattr(co, df_name)
        if not df.empty:
            setattr(co, df_name, _frame({k: df.loc[k].to_dict() for k in df.index}, cols_union).dropna(axis=1, how="all"))
    if extra:
        co.notes.append("Unmapped rows kept aside: " + ", ".join(list(extra)[:12]) + ("…" if len(extra) > 12 else ""))
    return normalise_shares(co)


def parse_any(data: bytes, filename: str) -> Company:
    """Try the Screener layout first, then the generic parser."""
    if filename.lower().endswith((".xlsx", ".xlsm", ".xls")):
        try:
            co = parse_screener(data)
        except Exception:
            co = None
        if co is not None:
            if co.name == "Company":
                co.name = filename.rsplit(".", 1)[0]
            return co
    co = parse_generic(data, filename)
    if co.name == "Company":
        co.name = filename.rsplit(".", 1)[0]
    return co


# ----------------------------------------------------------------------------
# Text lines (PDF text / OCR) -> line items
# ----------------------------------------------------------------------------
_NUM_TOKEN = re.compile(r"\(?-?[\d]{1,3}(?:,\d{2,3})*(?:\.\d+)?\)?|\(?-?\d+(?:\.\d+)?\)?|(?<!\w)[-–—](?!\w)")


def parse_number_token(t: str) -> float:
    t = t.strip()
    if t in ("-", "–", "—"):
        return 0.0
    return _num(t)


UNIT_FACTORS = {  # multiply by this to get ₹ Crore
    "₹ crore": 1.0, "₹ lakh": 0.01, "₹ million": 0.1, "₹ thousand": 0.0001, "₹ (absolute)": 1e-7,
    "$ million": 1.0, "$ billion": 1000.0, "$ thousand": 0.001,
}


def detect_unit(text: str) -> str:
    t = text[:20000].lower()
    if re.search(r"(₹|rs\.?|inr)?\s*(in|\()\s*crores?|\bcrore", t):
        return "₹ crore"
    if re.search(r"lakhs?|lacs?", t):
        return "₹ lakh"
    if re.search(r"in millions?|\bmillion", t):
        return "₹ million"
    if re.search(r"in thousands?", t):
        return "₹ thousand"
    return "₹ crore"


def extract_line_items(lines: list[str], max_cols: int = 2) -> pd.DataFrame:
    """Turn lines like 'Revenue from operations 12 1,23,456.78 1,10,000.00' into rows.

    Returns DataFrame[label, mapped_to, v1, v2, ...] where v1 is usually the latest year.
    """
    out = []
    for raw in lines:
        line = re.sub(r"\s{2,}", "  ", raw.replace(" ", " ").replace("\xa0", " ")).strip()
        if len(line) < 6 or not re.search(r"[A-Za-z]{3}", line):
            continue
        # split at first numeric token after the label
        m = re.search(r"\s(\(?-?\d[\d,]*\.?\d*\)?|[-–—])(\s|$)", line)
        if not m:
            continue
        label = line[: m.start()].strip(" :.-")
        rest = line[m.start():]
        toks = [t for t in re.findall(r"\(?-?\d[\d,]*\.?\d*\)?|(?<=\s)[-–—](?=\s|$)", " " + rest)]
        vals = [parse_number_token(t) for t in toks]
        vals = [v for v in vals if not np.isnan(v)]
        if not vals or len(label) < 3:
            continue
        # drop a leading 'note number' column when more numbers than expected
        if len(vals) >= max_cols + 1 and abs(vals[0]) < 100 and float(vals[0]).is_integer():
            vals = vals[1:]
        vals = vals[:max_cols]
        if all(1990 <= abs(v) <= 2100 and float(v).is_integer() for v in vals) or re.fullmatch(r"(?i)(march|particulars.*|note)", label):
            continue  # column-heading rows such as 'Year ended 2025 2024'
        key = canonical(label)
        out.append({"label": label, "mapped_to": key or "", **{f"v{i+1}": v for i, v in enumerate(vals)}})
    df = pd.DataFrame(out)
    if not df.empty:
        df = df.drop_duplicates(subset=["label", "v1"], keep="first").reset_index(drop=True)
    for i in range(max_cols):
        if f"v{i+1}" not in df.columns:
            df[f"v{i+1}"] = np.nan
    return df


def lines_to_company(df: pd.DataFrame, period_labels: list[str], factor: float, name: str, source: str) -> Company:
    """Convert an (edited) extraction table to a Company. period_labels[i] names column v{i+1}."""
    co = Company(name=name, sources=[source])
    rows = {"pl": {}, "bs": {}, "cf": {}}
    for _, r in df.iterrows():
        key = r.get("mapped_to")
        if not key or key not in STATEMENT_OF:
            continue
        is_count = key == "No. of Equity Shares"
        vals = {}
        for i, p in enumerate(period_labels):
            v = r.get(f"v{i+1}")
            if v is not None and not pd.isna(v):
                vals[p] = float(v) if is_count else float(v) * factor
        if vals and key not in rows[STATEMENT_OF[key]]:
            rows[STATEMENT_OF[key]][key] = vals
    cols = sorted(period_labels, key=period_sort_key)
    for k in rows:
        setattr(co, k, _frame(rows[k], cols) if rows[k] else pd.DataFrame())
    return co


def merge_company(base: Company, new: Company, overwrite: bool = True) -> Company:
    """Overlay `new` on `base` (new values win when overwrite=True)."""
    out = Company(name=base.name if base.name != "Company" else new.name, meta={**base.meta, **new.meta},
                  price=base.price if not base.price.empty else new.price,
                  quarters=base.quarters, sources=list(dict.fromkeys(base.sources + new.sources)),
                  notes=base.notes + new.notes)
    for attr in ("pl", "bs", "cf"):
        a, b = getattr(base, attr), getattr(new, attr)
        if a.empty:
            merged = b
        elif b.empty:
            merged = a
        else:
            merged = (b.combine_first(a) if overwrite else a.combine_first(b))
            merged = merged[sorted(merged.columns, key=period_sort_key)]
        setattr(out, attr, merged)
    return out
