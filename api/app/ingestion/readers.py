"""Turn an uploaded statement file into a grid of strings.

Safety rules: the file type is decided from its content (not its name); size, row, column
and decompressed-size limits are enforced; XML is parsed with defusedxml (openpyxl uses it
automatically when installed); nothing is executed or rendered. The original bytes are never
stored.
"""

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal

MAX_ROWS = 20_000
MAX_COLS = 60
MAX_CELL = 500
MAX_XLSX_UNCOMPRESSED = 150 * 1024 * 1024
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class ReadError(ValueError):
    """A problem the user can act on; the message is shown to them."""


@dataclass
class Grid:
    adapter: str  # csv | xlsx | xls
    rows: list[list[str]]
    sheet_name: str | None = None


def _cell(v: object) -> str:
    """Normalise a spreadsheet cell to text without losing money precision or dates."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, datetime):
        return v.date().isoformat() if v.time() == time(0) else v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float):
        # repr gives the shortest string that round-trips, e.g. 25000.5 not 25000.499999
        d = Decimal(repr(v))
        return format(d.normalize(), "f") if d == d.to_integral() else format(d, "f")
    if isinstance(v, int):
        return str(v)
    return str(v).replace("\x00", "").strip()[:MAX_CELL]


def _trim(rows: list[list[str]]) -> list[list[str]]:
    out = []
    for r in rows:
        r = [c.strip()[:MAX_CELL] for c in r[:MAX_COLS]]
        while r and not r[-1]:
            r.pop()
        out.append(r)
    while out and not any(out[-1]):
        out.pop()
    if len(out) > MAX_ROWS:
        raise ReadError(
            f"This file has more than {MAX_ROWS:,} rows. Split it into smaller periods."
        )
    if not any(any(r) for r in out):
        raise ReadError("The file is empty.")
    return out


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def read_csv(data: bytes) -> Grid:
    text = _decode(data)
    sample = text[:20_000]
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = []
    for i, row in enumerate(csv.reader(io.StringIO(text), dialect)):
        if i > MAX_ROWS + 50:
            raise ReadError(
                f"This file has more than {MAX_ROWS:,} rows. Split it into smaller periods."
            )
        rows.append(row)
    return Grid("csv", _trim(rows))


def _pick_sheet(sheets: list[tuple[str, list[list[str]]]]) -> tuple[str, list[list[str]]]:
    non_empty = [(n, r) for n, r in sheets if any(any(c for c in row) for row in r)]
    if not non_empty:
        raise ReadError("The spreadsheet has no data.")
    return max(non_empty, key=lambda s: sum(1 for row in s[1] if any(row)))


def read_xlsx(data: bytes) -> Grid:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ReadError("This .xlsx file is damaged or not really an Excel file.") from exc
    total = sum(i.file_size for i in zf.infolist())
    if total > MAX_XLSX_UNCOMPRESSED:
        raise ReadError("This spreadsheet is too large once unpacked.")
    import openpyxl  # imported lazily: only needed for Excel uploads

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises many types for malformed files
        raise ReadError(
            "Could not read this Excel file. Try saving it again as .xlsx or CSV."
        ) from exc
    sheets = []
    try:
        for ws in wb.worksheets:
            if getattr(ws, "sheet_state", "visible") != "visible":
                continue
            rows: list[list[str]] = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i > MAX_ROWS + 50:
                    raise ReadError(f"This sheet has more than {MAX_ROWS:,} rows.")
                rows.append([_cell(v) for v in row[:MAX_COLS]])
            sheets.append((ws.title, rows))
    finally:
        wb.close()
    name, rows = _pick_sheet(sheets)
    return Grid("xlsx", _trim(rows), name[:100])


def read_xls(data: bytes) -> Grid:
    import xlrd

    try:
        book = xlrd.open_workbook(file_contents=data, on_demand=True)
    except Exception as exc:
        raise ReadError("Could not read this .xls file. Try saving it as .xlsx or CSV.") from exc
    sheets = []
    try:
        for idx in range(book.nsheets):
            sh = book.sheet_by_index(idx)
            if sh.visibility != 0:
                continue
            if sh.nrows > MAX_ROWS + 50:
                raise ReadError(f"This sheet has more than {MAX_ROWS:,} rows.")
            rows = []
            for r in range(sh.nrows):
                out = []
                for c in range(min(sh.ncols, MAX_COLS)):
                    cell = sh.cell(r, c)
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        out.append(_cell(xlrd.xldate_as_datetime(cell.value, book.datemode)))
                    else:
                        out.append(_cell(cell.value))
                rows.append(out)
            sheets.append((sh.name, rows))
    finally:
        book.release_resources()
    name, rows = _pick_sheet(sheets)
    return Grid("xls", _trim(rows), name[:100])


def read_any(data: bytes, filename: str) -> Grid:
    head = data[:512].lstrip()
    if data[:4] == b"PK\x03\x04":
        return read_xlsx(data)
    if data[:8] == OLE2_MAGIC:
        return read_xls(data)
    if head[:1] == b"<" or head[:5].lower() == b"<html":
        raise ReadError(
            "This file is a web page saved with a spreadsheet name (some banks do this). "
            "Open it in Excel and use Save As → .xlsx or CSV, then upload that."
        )
    if data[:5] == b"%PDF-":
        raise ReadError("PDF statements aren't supported yet. Download the CSV or Excel version.")
    if b"\x00" in data[:4096]:
        raise ReadError("This file type isn't supported. Upload a CSV, .xlsx or .xls statement.")
    return read_csv(data)
