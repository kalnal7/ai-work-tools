import io
import zlib

import pytest
from PIL import Image, ImageDraw, ImageFont

import document_reader as reader


def pdf_with_pages(count, last_image=None):
    """Small real PDF: text pages plus an optional raster final page."""
    objects = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for index in range(count):
        image = last_image if index == count - 1 else None
        image_ref = None
        if image is not None:
            image = image.convert("RGB")
            compressed = zlib.compress(image.tobytes())
            objects.append((f"<< /Type /XObject /Subtype /Image /Width {image.width} /Height {image.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(compressed)} >>\nstream\n".encode() + compressed + b"\nendstream"))
            image_ref = len(objects)
        stream = (b"q 600 0 0 800 0 0 cm /Im0 Do Q" if image is not None else
                  f"BT /F1 18 Tf 40 700 Td (Document page {index + 1}) Tj ET".encode())
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
        content_ref = len(objects)
        resources = f"/Font << /F1 3 0 R >>" + (f" /XObject << /Im0 {image_ref} 0 R >>" if image_ref else "")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << {resources} >> /Contents {content_ref} 0 R >>".encode())
        kids.append(f"{len(objects)} 0 R")
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = f"<< /Type /Pages /Count {count} /Kids [{' '.join(kids)}] >>".encode()
    data, offsets = bytearray(b"%PDF-1.4\n"), [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(data)


def test_real_pdf_page_limit_below_equal_above_and_preview_page_bounds():
    for count in (reader.MAX_DOCUMENT_PAGES - 1, reader.MAX_DOCUMENT_PAGES):
        assert reader.document_pages("pages.pdf", pdf_with_pages(count)) == count
    with pytest.raises(ValueError, match="최대 50페이지"):
        reader.document_pages("pages.pdf", pdf_with_pages(reader.MAX_DOCUMENT_PAGES + 1))
    data = pdf_with_pages(2)
    for page in (1, 2):
        image = reader.source_preview("pages.pdf", data, page)
        assert Image.open(io.BytesIO(image)).width > 100
    for page in (0, 3):
        with pytest.raises(ValueError, match="페이지 번호"):
            reader.source_preview("pages.pdf", data, page)


def test_mixed_pdf_reads_the_scanned_sixth_page_instead_of_stopping_at_five():
    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(r"C:\Windows\Fonts\malgun.ttf", 64)
    draw.text((100, 300), "품목: 보관 상자", fill="black", font=font)
    text = reader.extract_pdf(pdf_with_pages(6, image))
    assert "Document page 5" in text
    assert "보관 상자" in text
    assert text.recognition["pages"] == 6
    assert text.recognition["page_routes"] == ["pdf_text"] * 5 + ["local_ocr"]
    assert text.recognition["route"] == "mixed_pdf"
