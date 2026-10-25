"""Small reusable product contract: real work, one request, recoverable results.

No Streamlit dependency. A download callback may run on another thread; page state
is only updated by the page itself. Each input selection gets a new job identity.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import math
import threading
import time


def input_key(files):
    digest = hashlib.sha256()
    for name, data in files:
        name = str(name).encode("utf-8")
        digest.update(len(name).to_bytes(4, "big")); digest.update(name)
        digest.update(len(data).to_bytes(8, "big")); digest.update(data)
    return digest.hexdigest()


class DownloadJob:
    """Serialize duplicate clicks, cache successful bytes, keep real progress."""

    def __init__(self, key):
        self.key = key
        self._lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._data = None
        self._state = {"status":"idle", "done":0, "total":0, "label":"",
                       "elapsed":0., "report":None, "error":None, "files":{}}

    def snapshot(self):
        with self._lock:
            return deepcopy(self._state)

    def request(self):
        with self._lock:
            if self._data is None and self._state["status"] != "running":
                self._state.update(status="queued", error=None)

    def progress(self, done, total, label):
        if not 0 <= done <= total or total <= 0:
            raise ValueError("Invalid workflow progress")
        with self._lock:
            self._state.update(done=done, total=total, label=str(label))

    def mark_file(self, index, status, pages=None):
        """Per-file status for the page: waiting, reading, done or failed."""
        if status not in {"reading", "done", "failed"} or not isinstance(index, int) or index < 0:
            raise ValueError("Invalid file status")
        with self._lock:
            entry = self._state["files"].setdefault(index, {})
            if entry.get("status") == "failed" and status == "done":
                return
            entry["status"] = status
            if pages is not None:
                entry["pages"] = int(pages)

    def run(self, work):
        with self._run_lock:
            if self._data is not None:
                return self._data
            started = time.perf_counter()
            with self._lock:
                self._state.update(status="running", error=None, done=0, files={})
            try:
                data, report = work(self.progress)
                if not isinstance(data, bytes) or not data:
                    raise ValueError("저장할 결과가 없습니다. 입력 파일을 확인해 주세요.")
                with self._lock:
                    self._data = data
                    self._state.update(status="ready", report=deepcopy(report),
                                       elapsed=time.perf_counter()-started)
                return data
            except Exception as exc:
                with self._lock:
                    self._state.update(status="failed", error=str(exc)[:600],
                                       elapsed=time.perf_counter()-started)
                raise


def review_invoice(original):
    """Recompute checks and amounts from the currently edited data."""
    row = dict(original)
    if "_extraction_failed" not in row and str(row.get("확인", "")).startswith("인식 실패"):
        row["_extraction_failed"] = True
        row["_extraction_reason"] = str(row["확인"])
    messages = []
    money_fields = ("공급가액", "부가세", "합계")
    invalid_fields = set(row.get("_invalid_money_fields", ()))
    for field in money_fields:
        value = row.get(field)
        if field in invalid_fields:
            row[field] = None
            messages.append(f"{field} 형식 확인")
            continue
        if value is None or value == "":
            row[field] = None
            messages.append(f"{field} 누락")
            continue
        try:
            if isinstance(value, bool):
                raise ValueError()
            number = Decimal(str(value).replace(",", "").strip())
            if not number.is_finite() or number < 0 or number != number.to_integral_value():
                raise ValueError()
            row[field] = int(number)
        except (ValueError, TypeError, InvalidOperation):
            row[field] = None
            invalid_fields.add(field)
            messages.append(f"{field} 형식 확인")
    row["_invalid_money_fields"] = [field for field in money_fields if field in invalid_fields]
    if all(row.get(k) is not None for k in ("공급가액", "부가세", "합계")):
        if row["공급가액"] + row["부가세"] != row["합계"]:
            messages.append("금액 재확인")
    if not str(row.get("상호명") or "").strip():
        messages.append("상호명 누락")
    if not str(row.get("품목") or "").strip():
        messages.append("품목 누락")
    if row.get("_extraction_failed") and not row.get("_manual_review_complete"):
        messages.insert(0, str(row.get("_extraction_reason") or "인식 실패"))
    row["확인"] = " · ".join(dict.fromkeys(messages)) or "합계 확인"
    return row


def invoice_summary(rows):
    checked = [review_invoice(row) for row in rows]
    return {"rows":checked, "count":len(checked),
            "total":sum(row.get("합계") or 0 for row in checked),
            "vat":sum(row.get("부가세") or 0 for row in checked),
            "needs_review":sum(row["확인"] != "합계 확인" for row in checked)}


def review_worklist(rows):
    """Return actionable field issues keyed by stable document identity."""
    result = []
    for position, source in enumerate(rows):
        row = review_invoice(source)
        document_id = str(row.get("_document_id") or f"row-{position}")
        reasons = []
        invalid_fields = set(row.get("_invalid_money_fields", ()))
        for field in ("상호명", "사업자번호", "작성일", "품목", "공급가액", "부가세", "합계"):
            value = row.get(field)
            if field in {"상호명", "품목", "공급가액", "부가세", "합계"} and field not in invalid_fields and (value is None or not str(value).strip()):
                reason = f"{field} 누락"
                if reason not in reasons:
                    reasons.append(reason)
        for field in row.get("_invalid_money_fields", ()):
            reason = f"{field} 형식 확인"
            if reason not in reasons: reasons.append(reason)
        for message in row["확인"].split(" · "):
            if message.endswith("형식 확인") and message not in reasons:
                reasons.append(message)
        if all(row.get(field) is not None for field in ("공급가액", "부가세", "합계")) and row["공급가액"] + row["부가세"] != row["합계"]:
            reasons.append("금액 불일치")
        if row.get("_extraction_failed") and not row.get("_manual_review_complete"):
            reasons.insert(0, str(row.get("_extraction_reason") or "문서 인식 실패"))
        for reason in dict.fromkeys(reasons):
            field = "합계" if reason == "금액 불일치" else (reason.split(" ", 1)[0] if reason.split(" ", 1)[0] in FIELDS_FOR_REVIEW else "문서")
            result.append({"document_id":document_id, "row_index":row.get("_row_index", position),
                           "filename":row.get("파일명", "문서"), "field":field, "reason":reason})
    return result


FIELDS_FOR_REVIEW = {"상호명", "사업자번호", "작성일", "품목", "공급가액", "부가세", "합계"}


def process_invoices(files, extract, parse, export, progress=lambda *args: None):
    """One bad document keeps its place and never discards other valid work."""
    rows, errors, seen = [], [], {}
    for index, (name, data) in enumerate(files):
        progress(index, len(files), name)
        fingerprint = hashlib.sha256(data).hexdigest()
        document_id = hashlib.sha256(f"{index}:{name}:{fingerprint}".encode("utf-8")).hexdigest()[:24]
        try:
            text = seen.get(fingerprint)
            if text is None:
                text = extract(name, data)
                if not text.strip():
                    raise ValueError("글자를 읽지 못했습니다. 더 선명한 원본을 넣어 주세요.")
                seen[fingerprint] = text
            row = parse(text, name)
            row.update(_row_index=index, _document_id=document_id, _input_fingerprint=fingerprint,
                       _extraction_failed=False)
            rows.append(review_invoice(row))
        except Exception as exc:
            message = str(exc).splitlines()[0][:180] or "원본 파일을 확인해 주세요."
            errors.append({"file":name, "message":message})
            rows.append(review_invoice({"파일명":name, "원문":"", "_row_index":index,
                "_document_id":document_id, "_input_fingerprint":fingerprint,
                "_extraction_failed":True, "_extraction_reason":"인식 실패 · "+message}))
        progress(index+1, len(files), name)
    if not rows or len(errors) == len(files):
        raise ValueError("읽을 수 있는 문서가 없습니다. PDF가 열리는지 확인하거나 선명한 이미지로 다시 넣어 주세요.")
    summary = invoice_summary(rows)
    return export(summary["rows"]), {**summary, "errors":errors, "input_files":len(files)}
