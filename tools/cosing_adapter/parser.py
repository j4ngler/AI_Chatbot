from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup  # type: ignore

from .schemas import Substance


CAS_RE = re.compile(r"\b(\d{2,7}-\d{2}-\d)\b")
# EC inventory format (EU): 200-289-5 (3-3-1), khác CAS thường có nhóm giữa 2 chữ số.
EC_LIKE_STANDALONE = re.compile(r"^\d{2,3}-\d{2,3}-\d$")

# CoSIng result rows often link to substance detail pages (deep link for users).
_DEFAULT_DETAIL_BASE = "https://ec.europa.eu"


def _row_cosing_detail_url(row, base_url: str = _DEFAULT_DETAIL_BASE) -> Optional[str]:
    base = f"{base_url.rstrip('/')}/"
    for a in row.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        low = href.lower()
        if "cosing/details" in low or "/growth/tools-databases/cosing/" in low and "/details/" in low:
            return urljoin(base, href)
    return None


def _norm_cell(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s


def _maybe_cas(s: str) -> str:
    m = CAS_RE.search(s or "")
    return m.group(1) if m else _norm_cell(s)


def _header_map(headers: List[str]) -> Dict[str, int]:
    """
    Map expected column names to index, using fuzzy matching on header text.
    """
    joined = [h.lower() for h in headers]
    idx: Dict[str, int] = {}
    for i, h in enumerate(joined):
        if "substance" in h and "name" in h:
            idx["substance_name"] = i
        elif "inci" in h:
            idx["inci_name"] = i
        elif re.search(r"\bec\b|ec\s*#|ec\s*no|einecs|elincs", h):
            idx["ec"] = i
        elif "cas" in h:
            idx["cas"] = i
        elif "function" in h:
            idx["function"] = i
        elif "restriction" in h or "annex" in h:
            idx["restrictions"] = i
    return idx


def parse_cosing_results_table(
    html: str,
    reference_url: str,
    *,
    detail_base_url: str = _DEFAULT_DETAIL_BASE,
) -> List[Substance]:
    """
    Parse CoSIng advanced results table HTML -> list[Substance].

    Heuristics:
    - Identify the first table with a header row containing relevant keywords.
    - Then map columns either by header fuzzy matching or by positional fallbacks.
    - If a row contains a link to .../cosing/details/..., use that as ``reference_url`` so
      the user opens the substance page directly instead of the generic advanced search.
    """
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    if not tables:
        return []

    best_table = None
    best_score = -1
    for t in tables:
        headers = [th.get_text(" ", strip=True) for th in t.select("tr th")]
        if not headers:
            continue
        h_join = " ".join(h.lower() for h in headers)
        score = 0
        for kw in ["substance", "inci", "cas", "function", "restriction", "annex"]:
            if kw in h_join:
                score += 1
        if score > best_score:
            best_score = score
            best_table = t

    if best_table is None:
        return []

    # Extract headers
    header_cells = best_table.select("tr th")
    headers = [c.get_text(" ", strip=True) for c in header_cells]
    header_index = _header_map(headers)

    substances: List[Substance] = []
    rows = best_table.select("tr")[1:]  # skip header row
    for r in rows:
        cells = r.find_all("td")
        if not cells:
            continue
        values = [_norm_cell(c.get_text(" ", strip=True)) for c in cells]
        if not values:
            continue

        def get(field: str, fallback_pos: Optional[int] = None) -> str:
            if field in header_index and header_index[field] < len(values):
                return values[header_index[field]]
            if fallback_pos is not None and fallback_pos < len(values):
                return values[fallback_pos]
            return ""

        ncol = len(values)

        substance_name = get("substance_name", 0)
        inci_name = get("inci_name", 1)
        cas_raw = get("cas", 2)
        cas = _maybe_cas(cas_raw)

        ec = ""
        function = ""
        restrictions = ""

        # Bảng advanced thường 6 cột; một số view chỉ 5 cột (EC + Function gộp kiểu lệch header).
        if ncol >= 6:
            ec = _norm_cell(get("ec", 3))
            function = _norm_cell(get("function", 4))
            restrictions = _norm_cell(get("restrictions", 5))
        elif ncol == 5:
            v3 = _norm_cell(values[3])
            v4 = _norm_cell(values[4])
            if EC_LIKE_STANDALONE.match(v3):
                ec = v3
                if v4 and not EC_LIKE_STANDALONE.match(v4):
                    function = v4
                    restrictions = ""
                else:
                    function = ""
                    restrictions = v4
            else:
                function = _norm_cell(get("function", 3))
                restrictions = _norm_cell(get("restrictions", 4))
        else:
            function = _norm_cell(get("function", 3))
            restrictions = _norm_cell(get("restrictions", 4))

        # If the table uses a different column order, still try to salvage CAS.
        if not cas and any("cas" in (c or "").lower() for c in values):
            cas = _maybe_cas(" ".join(values))

        # An toàn: EC lọt vào cột function khi header lệch.
        if function and EC_LIKE_STANDALONE.match(function) and not ec:
            ec = function
            function = ""

        row_ref = _row_cosing_detail_url(r, detail_base_url) or reference_url
        substances.append(
            Substance(
                substance_name=substance_name,
                inci_name=inci_name,
                cas=cas,
                ec=ec,
                function=function,
                restrictions=restrictions,
                reference_url=row_ref,
            )
        )
    return substances


def parse_cosing_detail_page(html: str, reference_url: str) -> Dict[str, str]:
    """
    Parse CoSIng substance detail page.

    Returns a flat dict for the most visible fields used in smoke/UAT:
    - inci_name, description, cas, ec, regulation, annex_ref, functions, sccs_opinions

    Note: HTML on CoSIng can change; parsing here uses label/value heuristics.
    """
    soup = BeautifulSoup(html, "lxml")

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip())

    # Extract label/value table rows.
    # We look for rows with 2 cells where the first cell is a label.
    label_to_value: Dict[str, Any] = {}
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if len(cells) < 2:
            continue

        label = norm(cells[0].get_text(" ", strip=True)).lower()
        value_el = cells[1]

        # Skip non-data rows.
        if not label:
            continue

        value_text = norm(value_el.get_text(" ", strip=True))

        # Functions / SCCS opinions can be bullet lists; collect li when present.
        if "functions" in label:
            lis = [norm(li.get_text(" ", strip=True)) for li in value_el.find_all("li")]
            label_to_value["functions"] = ", ".join([x for x in lis if x])
            if not label_to_value["functions"]:
                label_to_value["functions"] = value_text
        elif "sccs opinions" in label or "sccs" in label:
            lis = [norm(li.get_text(" ", strip=True)) for li in value_el.find_all("li")]
            label_to_value["sccs_opinions"] = ", ".join([x for x in lis if x])
            if not label_to_value["sccs_opinions"]:
                label_to_value["sccs_opinions"] = value_text
        elif "inci name" in label or "inci/" in label:
            label_to_value["inci_name"] = value_text
        elif "description" in label:
            label_to_value["description"] = value_text
        elif label in ("cas #", "cas #".lower()) or "cas #" in label or "cas" == label:
            label_to_value["cas"] = value_text
        elif "ec #" in label or label == "ec #" or label.startswith("ec"):
            label_to_value["ec"] = value_text
        elif "regulation" in label or "cosmetics regulation" in label:
            label_to_value["regulation"] = value_text
        elif "annex" in label and "ref" in label:
            label_to_value["annex_ref"] = value_text
        elif "maximum" in label and ("concentration" in label or "conc" in label):
            label_to_value["max_concentration"] = value_text
        elif "glossary" in label and ("common" in label or "ingredient" in label):
            label_to_value["glossary_name"] = value_text

    # Some pages put Annex/Ref in the header section rather than label-value rows.
    # Fallback: search visible text patterns.
    page_text = norm(soup.get_text(" ", strip=True))
    if "annex_ref" not in label_to_value:
        m = re.search(r"\b([IVX]{1,5})\s*/\s*\d+\b", page_text)
        if m:
            label_to_value["annex_ref"] = m.group(0)

    if "max_concentration" not in label_to_value:
        m = re.search(
            r"maximum\s+concentration[^:]{0,120}:\s*([^\n]+?)(?:\n|$)",
            page_text,
            re.IGNORECASE,
        )
        if m:
            label_to_value["max_concentration"] = norm(m.group(1))

    # If SCCS opinions were not captured by table heuristics,
    # try a secondary strategy by locating the label text in the DOM.
    if not label_to_value.get("sccs_opinions"):
        try:
            label_string = soup.find(string=re.compile(r"sccs opinions", re.IGNORECASE))
            if label_string:
                container = label_string
                # Prefer searching within a local container.
                for parent_tag in ["tr", "table", "section", "div"]:
                    found = label_string.find_parent(parent_tag)
                    if found is not None:
                        container = found
                        break
                lis = [norm(li.get_text(" ", strip=True)) for li in container.find_all("li")]
                lis = [x for x in lis if x]
                if lis:
                    label_to_value["sccs_opinions"] = ", ".join(lis)
                else:
                    # Last fallback: use container text and keep only actual opinion items.
                    # Avoid matching the label text itself ("SCCS opinions").
                    t = norm(container.get_text(" ", strip=True))
                    opinions = [
                        x
                        for x in t.split(",")
                        if ("opinion" in x.lower()) and ("sccs" not in x.lower())
                    ]
                    if opinions:
                        label_to_value["sccs_opinions"] = ", ".join(opinions)
        except Exception:
            pass

    # Normalize Annex/Ref formats like "VI / 26" -> "VI/26"
    if label_to_value.get("annex_ref"):
        v = label_to_value["annex_ref"]
        v = re.sub(r"\s*/\s*", "/", v)
        v = re.sub(r"\s+", " ", v).strip()
        label_to_value["annex_ref"] = v

    out: Dict[str, str] = {
        "reference_url": reference_url,
        "inci_name": label_to_value.get("inci_name", ""),
        "description": label_to_value.get("description", ""),
        "cas": label_to_value.get("cas", ""),
        "ec": label_to_value.get("ec", ""),
        "regulation": label_to_value.get("regulation", ""),
        "annex_ref": label_to_value.get("annex_ref", ""),
        "functions": label_to_value.get("functions", ""),
        "sccs_opinions": label_to_value.get("sccs_opinions", ""),
        "max_concentration": label_to_value.get("max_concentration", ""),
        "glossary_name": label_to_value.get("glossary_name", ""),
    }
    return out

