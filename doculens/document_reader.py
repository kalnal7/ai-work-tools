"""Local document reading and original-page previews; no network calls at runtime."""
from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
MAX_DOCUMENT_PAGES = 50


class DocumentText(str):
    def __new__(cls, text, recognition=None):
        value = super().__new__(cls, text)
        value.recognition = recognition or {}
        return value


def find_tool(name):
    # Prefer the portable, release-bundled tools so installed system versions
    # cannot silently replace the tested OCR/PDF engines.
    bundled = ROOT / "tools"
    candidates = {
        "tesseract": (bundled / "tesseract" / "tesseract.exe",),
        "pdfinfo": (bundled / "poppler" / "Library" / "bin" / "pdfinfo.exe",
                    bundled / "poppler" / "bin" / "pdfinfo.exe"),
        "pdftotext": (bundled / "poppler" / "Library" / "bin" / "pdftotext.exe",
                      bundled / "poppler" / "bin" / "pdftotext.exe"),
        "pdftoppm": (bundled / "poppler" / "Library" / "bin" / "pdftoppm.exe",
                     bundled / "poppler" / "bin" / "pdftoppm.exe"),
    }
    for path in candidates.get(name, ()):
        if path.is_file():
            return str(path)
    found = shutil.which(name)
    if found:
        return found
    if name == "tesseract":
        for folder in (r"C:\Program Files\Tesseract-OCR", r"C:\Program Files (x86)\Tesseract-OCR"):
            path = Path(folder) / "tesseract.exe"
            if path.is_file():
                return str(path)
    return None


def _workspace_temp():
    work = ROOT / "_work"
    work.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="document_", dir=work)


def _run(arguments, timeout=60):
    result = subprocess.run(arguments, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout)
    if result.returncode:
        raise ValueError(result.stderr.strip()[:500] or "문서를 읽지 못했습니다.")
    return result.stdout


def _pdf_page_count(path):
    engine = find_tool("pdfinfo")
    if not engine:
        raise RuntimeError("PDF를 읽으려면 Poppler의 pdfinfo가 필요합니다.")
    text = _run([engine, str(path)])
    match = re.search(r"^Pages:\s*(\d+)", text, re.M)
    if not match or int(match[1]) < 1:
        raise ValueError("PDF 페이지 수를 확인할 수 없습니다.")
    count = int(match[1])
    if count > MAX_DOCUMENT_PAGES:
        raise ValueError(f"문서 한 개는 최대 {MAX_DOCUMENT_PAGES}페이지까지 처리합니다. PDF를 나눠 주세요.")
    return count


def model_directory():
    models = ROOT / "tools" / "tessdata"
    if all((models / (language + ".traineddata")).is_file() for language in ("kor", "eng")):
        return models
    return None


def _model_name(directory):
    return "tessdata_best" if directory else None


def _ocr_page(image):
    engine = find_tool("tesseract")
    if not engine:
        raise RuntimeError("Tesseract OCR과 한국어 언어 데이터를 설치해 주세요.")
    with _workspace_temp() as folder:
        path = Path(folder) / "page.png"
        processed = ImageOps.autocontrast(ImageOps.grayscale(ImageOps.exif_transpose(image)), cutoff=1)
        processed.convert("RGB").save(path)
        arguments = [engine, str(path), "stdout"]
        directory = model_directory()
        if directory:
            arguments.extend(["--tessdata-dir", str(directory)])
        arguments.extend(["-l", "kor+eng", "--oem", "1", "--psm", "6"])
        return _run(arguments, timeout=90).strip()


def ocr_image(data):
    with Image.open(io.BytesIO(data)) as source:
        count = getattr(source, "n_frames", 1)
        if count > MAX_DOCUMENT_PAGES:
            raise ValueError(f"문서 한 개는 최대 {MAX_DOCUMENT_PAGES}페이지까지 처리합니다.")
        texts = []
        for index in range(count):
            source.seek(index)
            texts.append(_ocr_page(source))
    return DocumentText("\n\f\n".join(texts), {
        "route": "local_ocr", "model": _model_name(model_directory()),
        "pages": count, "page_routes": ["local_ocr"] * count})


def extract_pdf(data):
    with _workspace_temp() as folder:
        path = Path(folder) / "source.pdf"
        path.write_bytes(data)
        count = _pdf_page_count(path)
        pages = [""] * count
        text_engine = find_tool("pdftotext")
        if text_engine:
            text = _run([text_engine, "-layout", "-enc", "UTF-8", str(path), "-"])
            split = text.split("\f")
            pages = [(split[index].strip() if index < len(split) else "") for index in range(count)]
        routes = []
        for index in range(count):
            if pages[index].strip():
                routes.append("pdf_text")
                continue
            renderer = find_tool("pdftoppm")
            if not renderer:
                raise RuntimeError("스캔 PDF를 읽으려면 Poppler의 pdftoppm이 필요합니다.")
            prefix = Path(folder) / "page"
            _run([renderer, "-f", str(index + 1), "-l", str(index + 1), "-singlefile",
                  "-r", "300", "-png", str(path), str(prefix)])
            with Image.open(prefix.with_suffix(".png")) as image:
                pages[index] = _ocr_page(image)
            routes.append("local_ocr")
        route = routes[0] if len(set(routes)) == 1 else "mixed_pdf"
        return DocumentText("\n\f\n".join(pages), {
            "route": route, "model": _model_name(model_directory()) if "local_ocr" in routes else None,
            "pages": count, "page_routes": routes})


def extract_text(name, data):
    return extract_pdf(data) if Path(name).suffix.lower() == ".pdf" else ocr_image(data)


def document_pages(name, data):
    if Path(name).suffix.lower() != ".pdf":
        with Image.open(io.BytesIO(data)) as image:
            return getattr(image, "n_frames", 1)
    with _workspace_temp() as folder:
        path = Path(folder) / "source.pdf"
        path.write_bytes(data)
        return _pdf_page_count(path)


def source_preview(name, data, page=1):
    """Render the actual uploaded page, never an OCR reconstruction."""
    count = document_pages(name, data)
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= count:
        raise ValueError("원본 페이지 번호가 범위를 벗어났습니다.")
    if Path(name).suffix.lower() == ".pdf":
        engine = find_tool("pdftoppm")
        if not engine:
            raise RuntimeError("원본 PDF 미리보기에 Poppler가 필요합니다.")
        with _workspace_temp() as folder:
            path, prefix = Path(folder) / "source.pdf", Path(folder) / "preview"
            path.write_bytes(data)
            _run([engine, "-f", str(page), "-l", str(page), "-singlefile",
                  "-scale-to", "1800", "-png", str(path), str(prefix)])
            return prefix.with_suffix(".png").read_bytes()
    with Image.open(io.BytesIO(data)) as source:
        source.seek(page - 1)
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((1800, 2400))
        stream = io.BytesIO()
        image.save(stream, "PNG")
        return stream.getvalue()
