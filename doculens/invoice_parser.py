"""Label-based invoice extraction. Unsupported or ambiguous amounts stay flagged."""
from __future__ import annotations

import re

from product_workflow import review_invoice


ALIASES = {
    "상호명": ("상호명", "상호", "공급자상호", "공급자", "거래처"),
    "사업자번호": ("사업자등록번호", "사업자번호", "등록번호"),
    "작성일": ("작성일자", "작성일", "발행일", "거래일자", "거래일"),
    "품목": ("품목명", "품목", "품명"),
    "공급가액": ("공급가액", "공급가"),
    "부가세": ("부가가치세", "부가세", "세액"),
    "합계": ("합계금액", "총합계", "청구금액", "총액", "합계"),
}
_LABEL_PARTS = []
for field, labels in ALIASES.items():
    expression = "|".join(r"[ \t]*".join(map(re.escape, label)) for label in labels)
    _LABEL_PARTS.append(f"(?P<f{len(_LABEL_PARTS)}>{expression})(?=[ \t:：]|$)")
LABEL = re.compile("|".join(_LABEL_PARTS))
FIELD_NAMES = list(ALIASES)
MONEY_FIELDS = ("공급가액", "부가세", "합계")


def _labelled_values(text):
    lines = [line.strip(" \t:：") for line in text.splitlines() if line.strip()]
    found = {}
    for position, line in enumerate(lines):
        matches = list(LABEL.finditer(line))
        for index, match in enumerate(matches):
            field = FIELD_NAMES[int(match.lastgroup[1:])]
            end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
            value = line[match.end():end].strip(" \t:：|")
            if not value and position + 1 < len(lines) and not LABEL.search(lines[position + 1]):
                value = lines[position + 1].strip(" \t:：|")
            if field == "상호명" and re.match(r"(?:서명|날인)\b", value):
                continue
            if field == "품목" and re.match(r"(?:규격|수량|단가|금액)(?:\s|\||$)", value):
                # A simple line-item table: keep descriptions, not its numeric columns.
                items = []
                for row in lines[position + 1:]:
                    if LABEL.search(row):
                        break
                    columns = re.split(r"\t+| {2,}|\s*\|\s*", row)
                    if len(columns) > 1 and columns[0] and not re.fullmatch(r"[\d,\.]+", columns[0]):
                        items.append(columns[0])
                value = "; ".join(items)
            if value:
                found.setdefault(field, []).append(value)
    return found


def _money(raw):
    value = re.sub(r"\s", "", raw)
    value = re.sub(r"^(?:₩|KRW)", "", value, flags=re.I)
    value = re.sub(r"(?:원|KRW)$", "", value, flags=re.I)
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,3}(?:\.\d{3})+)", value):
        return None
    return int(value.replace(",", "").replace(".", ""))


def parse_invoice(text, filename="문서"):
    values = _labelled_values(str(text))
    clean = str(text)
    business = re.search(r"\b\d{3}\s*[-–]?\s*\d{2}\s*[-–]?\s*\d{5}\b", clean)
    date = re.search(r"\b20\d{2}[./-]\s?\d{1,2}[./-]\s?\d{1,2}\b", clean)
    row = {"파일명": filename, "상호명": (values.get("상호명") or [""])[0],
           "사업자번호": re.sub(r"\s", "", business[0]) if business else "",
           "작성일": date[0].replace(" ", "") if date else "",
           "품목": "; ".join(dict.fromkeys(values.get("품목", []))),
           "원문": str(text), "_invalid_money_fields": [],
           "_recognition": dict(getattr(text, "recognition", {}))}
    for field in MONEY_FIELDS:
        candidates = values.get(field, [])
        parsed = [_money(raw) for raw in candidates]
        # Conflicting totals and malformed OCR are not resolved by guessing.
        if candidates and (None in parsed or len(set(parsed)) != 1):
            row[field] = None
            row["_invalid_money_fields"].append(field)
        else:
            row[field] = parsed[0] if parsed else None
    return review_invoice(row)
