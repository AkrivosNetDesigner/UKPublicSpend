"""Minimal ODS reader (stdlib only): sheet name -> list of rows of values."""
import zipfile
import xml.etree.ElementTree as ET

NS = {
    "t": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "o": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "x": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}
T = "{%s}" % NS["t"]
O = "{%s}" % NS["o"]


def _cell_value(c):
    vt = c.get(O + "value-type")
    if vt in ("float", "percentage", "currency"):
        return float(c.get(O + "value"))
    if vt == "date":
        return c.get(O + "date-value")
    if vt is None:
        return None
    txt = "".join("".join(p.itertext()) for p in c.findall("x:p", NS)).strip()
    return txt or None


def read_ods(path, max_repeat=200):
    root = ET.fromstring(zipfile.ZipFile(path).read("content.xml"))
    sheets = {}
    for tbl in root.iter(T + "table"):
        rows = []
        for r in tbl.iter(T + "table-row"):
            vals = []
            for c in r:
                if c.tag not in (T + "table-cell", T + "covered-table-cell"):
                    continue
                v = _cell_value(c)
                vals.extend([v] * min(int(c.get(T + "number-columns-repeated", 1)), max_repeat))
            while vals and vals[-1] is None:
                vals.pop()
            rep = int(r.get(T + "number-rows-repeated", 1))
            if vals or rep == 1:
                rows.extend([vals] * min(rep, 1 if not vals else max_repeat))
        sheets[tbl.get(T + "name")] = rows
    return sheets
