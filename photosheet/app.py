"""PHOTOSHEET — 로컬 사진대지. 순수 처리 함수는 pytest에서도 그대로 사용합니다."""
from __future__ import annotations

import base64
import hashlib
import html
import io
import math
import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from statistics import median

from PIL import Image, ImageOps, UnidentifiedImageError
from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.pagebreak import Break
from openpyxl.worksheet.page import PageMargins
from openpyxl.utils.units import pixels_to_EMU

ROOT = Path(__file__).resolve().parent
MAX_FILES = 200
MAX_BYTES = 15 * 1024 * 1024
PAGE_W, PAGE_H, HEADER_H, CAPTION_H = 720, 1000, 100, 74
CATEGORIES = ('전', '중', '후', '기타')


class PhotoError(ValueError):
    pass


@dataclass(frozen=True)
class Photo:
    name: str
    jpeg: bytes
    width: int
    height: int
    original_size: int
    sort_time: datetime
    taken: str
    rotated: bool
    category: str = '기타'
    location: str = ''
    content: str = ''
    order: int = 0


def validate_limits(count: int, sizes) -> None:
    if count == 0:
        raise PhotoError('JPG 또는 PNG 사진을 한 장 이상 넣어 주세요.')
    if count > MAX_FILES:
        raise PhotoError('사진은 한 번에 200장 이하로 나누어 넣어 주세요.')
    if any(size > MAX_BYTES for size in sizes):
        raise PhotoError('한 장당 15MB 이하로 줄여 다시 넣어 주세요.')


def filename_fields(name: str) -> tuple[str, str]:
    stem = Path(name).stem
    if re.fullmatch(r'(?:IMG|DSC|DSCF|PXL)_?\d+', stem, re.IGNORECASE):
        return '', ''
    return tuple(stem.split('_', 1)) if '_' in stem else ('', '')


def auto_category(name: str, content: str = '') -> str:
    # 단어 끝의 단계만 인식합니다. 전기·후면·중간 같은 단어는 제외합니다.
    matches = set(re.findall(r'([전중후])(?=$|[\W_])', Path(name).stem + ' ' + content))
    return matches.pop() if len(matches) == 1 else '기타'


def edit_photo(p: Photo, changes: dict) -> Photo:
    content = safe_text(changes.get('내용', p.content))
    category = (changes['구분'] if '구분' in changes else
                auto_category(p.name, content) if content != p.content else p.category)
    return replace(p, order=int(changes.get('순서', p.order)), category=category,
                   location=safe_text(changes.get('위치', p.location)), content=content,
                   taken=safe_text(changes.get('촬영일', p.taken)))


def read_photo(name: str, data: bytes, mtime: float) -> Photo:
    validate_limits(1, [len(data)])
    if Path(name).suffix.lower() not in ('.jpg', '.jpeg', '.png'):
        raise PhotoError('지원하지 않는 형식입니다. JPG 또는 PNG로 바꾸어 넣어 주세요.')
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in ('JPEG', 'PNG'):
                raise PhotoError('지원하지 않는 형식입니다. JPG 또는 PNG로 바꾸어 넣어 주세요.')
            exif = source.getexif()
            nested = exif.get_ifd(34665) if 34665 in exif else {}
            captured = None
            for value in (nested.get(36867), exif.get(36867), nested.get(36868), exif.get(36868), exif.get(306)):
                try:
                    captured = datetime.strptime(str(value), '%Y:%m:%d %H:%M:%S')
                    break
                except (ValueError, TypeError):
                    continue
            orientation = exif.get(274, 1)
            upright = ImageOps.exif_transpose(source)
            upright.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            # 투명 PNG는 흰 바탕으로 합칩니다. 원본 EXIF·위치 정보는 내보내지 않습니다.
            rgba = upright.convert('RGBA')
            rgb = Image.new('RGB', rgba.size, 'white')
            rgb.paste(rgba, mask=rgba.getchannel('A'))
            out = io.BytesIO()
            rgb.save(out, 'JPEG', quality=85, optimize=True)
            location, content = filename_fields(name)
            return Photo(name, out.getvalue(), *rgb.size, len(data), captured or datetime.fromtimestamp(mtime),
                         captured.strftime('%Y-%m-%d') if captured else '촬영일 없음',
                         orientation in (2, 3, 4, 5, 6, 7, 8), category=auto_category(name, content),
                         location=location, content=content)
    except PhotoError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise PhotoError('사진을 읽지 못했습니다. 정상적인 JPG 또는 PNG로 다시 저장해 넣어 주세요.') from exc


def sort_photos(photos):
    return [replace(p, order=i + 1) for i, p in enumerate(sorted(photos, key=lambda p: (p.sort_time, p.name)))]


def dimensions(slots: int, grouped: bool = False):
    if slots not in (2, 4, 6):
        raise ValueError('배치는 2·4·6칸 중에서 골라 주세요.')
    if grouped:
        return 3, 2
    return (2, 1) if slots == 2 else (2, 2) if slots == 4 else (3, 2)


def slot_geometry(slots: int, grouped: bool = False, photos=()):
    cols, rows = dimensions(slots, grouped)
    slot_w = PAGE_W / cols
    landscape = [p.width / p.height for p in photos if p and p.width >= p.height]
    aspect = median(landscape) if landscape else 4 / 3
    image_h = (slot_w - 8) / aspect + 8
    return slot_w, image_h, image_h + CAPTION_H


def paginate(photos, slots=4, grouped=False):
    cols, rows = dimensions(slots, grouped)
    ordered = sorted(photos, key=lambda p: p.order)
    if not grouped:
        size = cols * rows
        return [ordered[i:i + size] + [None] * (size - len(ordered[i:i + size])) for i in range(0, len(ordered), size)]
    # 위치별 전·중·후의 각 열을 고정하고, 같은 구분이 여러 장이면 다음 줄로 넘깁니다.
    locations = {}
    loose = []
    for p in ordered:
        if p.location.strip() and p.category in ('전', '중', '후'):
            locations.setdefault(p.location.strip(), {c: [] for c in ('전', '중', '후')})[p.category].append(p)
        else:
            loose.append(p)
    lines = []
    for group in locations.values():
        for n in range(max(map(len, group.values()))):
            lines.append([group[c][n] if n < len(group[c]) else None for c in ('전', '중', '후')])
    for i in range(0, len(loose), 3):
        lines.append(loose[i:i + 3] + [None] * (3 - len(loose[i:i + 3])))
    return [sum(lines[i:i + rows], []) + [None] * (cols * (rows - len(lines[i:i + rows]))) for i in range(0, len(lines), rows)]


def caption(p):
    return f'{p.category} · {p.location or "위치 미입력"}\n{p.content or "내용 미입력"}\n{p.taken or "촬영일 없음"}'


def fitted(p, box_w, box_h):
    ratio = min((box_w - 8) / p.width, (box_h - 8) / p.height)
    return p.width * ratio, p.height * ratio


def safe_text(value):
    # openpyxl이 =로 시작하는 사용자 설명을 수식으로 저장하지 않게 합니다.
    return str(value or '').replace('\x00', '')


def make_excel(photos, slots=4, grouped=False, cover=None):
    validate_limits(len(photos), [p.original_size for p in photos])
    cover = cover or {}
    pages = paginate(photos, slots, grouped)
    cols, rows = dimensions(slots, grouped)
    book = Workbook()
    sheet = book.active
    sheet.title = '사진대지'
    sheet.sheet_view.showGridLines = False
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = 'portrait'
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.print_options.horizontalCentered = True
    sheet.page_margins = PageMargins(left=.3, right=.3, top=.3, bottom=.3, header=.1, footer=.1)
    sheet.oddHeader.center.text = safe_text(cover.get('title', '')).replace('&', '&&')
    sheet.oddHeader.right.text = '&P / &N'
    sheet.oddHeader.center.size = 9
    sheet.oddFooter.center.text = 'PHOTOSHEET'
    sheet.oddFooter.center.size = 8
    for col in 'ABCDEFGHIJKL':
        sheet.column_dimensions[col].width = (60 - 5) / 7
    line = Side(style='thin', color='CFCECA')
    per_page = 3 + rows * 2
    def merged(row, start, end, value, size=10, bold=False, fill=None):
        sheet.merge_cells(start_row=row, start_column=start, end_row=row, end_column=end)
        cell = sheet.cell(row, start, safe_text(value))
        cell.data_type = 's'
        cell.font = Font(name='맑은 고딕', size=size, bold=bold, color='21201C')
        cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True, indent=1)
        for col in range(start, end + 1):
            c = sheet.cell(row, col)
            c.border = Border(left=line, right=line, top=line, bottom=line)
            if fill:
                c.fill = PatternFill('solid', fgColor=fill)
    for pi, page in enumerate(pages):
        base = pi * per_page
        for offset, height in enumerate((38, 22, 40), 1):
            sheet.row_dimensions[base + offset].height = height * .75
        merged(base + 1, 1, 12, cover.get('title') or '사진대지', 17, True)
        merged(base + 2, 1, 12, f"작성일 {cover.get('date', '')}    작성자 {cover.get('author', '')}    {cover.get('company', '')}", 9)
        merged(base + 3, 1, 12, f'사진대지    {pi + 1} / {len(pages)}쪽', 10, True, 'F1F0EF')
        slot_w, image_h, slot_h = slot_geometry(slots, grouped, page)
        for ri in range(rows):
            photo_row = base + 4 + ri * 2
            sheet.row_dimensions[photo_row].height = image_h * .75
            sheet.row_dimensions[photo_row + 1].height = CAPTION_H * .75
            for ci in range(cols):
                p = page[ri * cols + ci]
                start = ci * (12 // cols) + 1
                end = start + 12 // cols - 1
                merged(photo_row, start, end, '')
                merged(photo_row + 1, start, end, caption(p) if p else '', 10, fill='F9F9F8')
                if p:
                    width, height = fitted(p, slot_w, image_h)
                    drawing = ExcelImage(io.BytesIO(p.jpeg))
                    drawing.anchor = OneCellAnchor(
                        _from=AnchorMarker(col=start - 1, row=photo_row - 1,
                                           colOff=pixels_to_EMU((slot_w - width) / 2),
                                           rowOff=pixels_to_EMU((image_h - height) / 2)),
                        ext=XDRPositiveSize2D(pixels_to_EMU(width), pixels_to_EMU(height)))
                    sheet.add_image(drawing)
        if pi < len(pages) - 1:
            sheet.row_breaks.append(Break(id=base + per_page))
    sheet.print_area = f'A1:L{per_page * len(pages)}'
    output = io.BytesIO()
    book.save(output)
    return output.getvalue(), len(pages)


def preview_html(photos, slots, grouped, cover):
    cols, rows = dimensions(slots, grouped)
    pages = paginate(photos, slots, grouped)
    if not pages:
        return '<p>사진을 넣으면 첫 페이지가 여기에 나타납니다.</p>'
    slot_w, image_h, slot_h = slot_geometry(slots, grouped, pages[0])
    esc = lambda v: html.escape(str(v or ''))
    cards = []
    for p in pages[0]:
        if p:
            w, h = fitted(p, slot_w, image_h)
            cards.append(f'<div class="slot"><div class="photo"><img src="data:image/jpeg;base64,{base64.b64encode(p.jpeg).decode()}" style="width:{w}px;height:{h}px"/></div><div class="caption">{esc(caption(p)).replace(chr(10), "<br>")}</div></div>')
        else:
            cards.append('<div class="slot"><div class="photo"></div><div class="caption"></div></div>')
    font = base64.b64encode((ROOT / 'static/fonts/SUIT-Regular.woff2').read_bytes()).decode()
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><style>@font-face{{font-family:SUIT;src:url(data:font/woff2;base64,{font})}}*{{box-sizing:border-box}}body{{margin:0;background:#efeeec;font:13px SUIT,sans-serif;color:#21201c}}.paper{{width:720px;height:1000px;background:white;margin:auto;outline:1px solid #cfceca}}.head{{height:100px}}.title{{height:38px;font-size:23px;font-weight:bold;padding:5px 12px}}.meta{{height:22px;padding:0 12px}}.page{{height:40px;background:#f1f0ef;padding:10px 12px}}.grid{{display:grid;grid-template-columns:repeat({cols},1fr);grid-template-rows:repeat({rows},{slot_h}px)}}.slot{{min-width:0;outline:1px solid #cfceca;outline-offset:-1px}}.photo{{height:{image_h}px;display:flex;align-items:center;justify-content:center;overflow:hidden}}.caption{{height:74px;background:#f9f9f8;padding:8px 10px;overflow:hidden;overflow-wrap:anywhere;line-height:19px}}@media(max-width:740px){{.paper{{transform-origin:top left;transform:scale(calc((100vw - 2px) / 720px))}}}}</style><div class="paper"><div class="head"><div class="title">{esc(cover.get('title') or '사진대지')}</div><div class="meta">작성일 {esc(cover.get('date'))}　 작성자 {esc(cover.get('author'))}　{esc(cover.get('company'))}</div><div class="page">사진대지　1 / {len(pages)}쪽</div></div><div class="grid">{''.join(cards)}</div></div></html>'''


def size_text(n):
    return f'{n / 1024 / 1024:.2f}MB'


def main():
    import pandas as pd
    import streamlit as st
    import streamlit.components.v1 as components
    st.set_page_config(page_title='PHOTOSHEET · 사진대지 만들기', page_icon='▦', layout='wide')
    st.markdown('''<style>@font-face{font-family:SUIT;src:url('/app/static/fonts/SUIT-Regular.woff2')}html,body,[class*="css"],input,button,textarea{font-family:SUIT,sans-serif}.block-container{max-width:1480px;padding-top:5rem}h1{letter-spacing:-1.5px}.st-key-header{border-bottom:2px solid #21201c;margin-bottom:16px}.st-key-summary{background:#f1f0ef;border-left:4px solid #9c3d2e;padding:12px 18px}.st-key-size_note{color:#63635e;font-size:14px}button{border-radius:4px!important}[data-testid="stSidebar"]{border-right:1px solid #cfceca}[data-testid="stToolbar"],[data-testid="stMainMenu"],[data-testid="stAppDeployButton"],#MainMenu{display:none!important}</style>''', unsafe_allow_html=True)
    with st.sidebar:
        st.markdown('### 사진대지 설정')
        with st.container(key='sidebar_layout'):
            slots = st.radio('한 장에 넣을 사진', (2, 4, 6), index=1, format_func=lambda x: {2:'2칸 · 2 × 1',4:'4칸 · 2 × 2',6:'6칸 · 3 × 2'}[x], key='layout_choice')
        with st.container(key='sidebar_group'):
            grouped = st.checkbox('전·중·후 묶기', key='group_choice')
            if grouped:
                st.caption('같은 위치의 전·중·후를 3열 × 2줄로 나란히 놓습니다. 빈 구분은 빈칸으로 둡니다.')
        with st.container(key='sidebar_cover'):
            st.markdown('#### 표지 정보')
            title = st.text_input('공사명', key='cover_title')
            written = st.date_input('작성일', date.today(), key='cover_date')
            author = st.text_input('작성자 (빈칸 가능)', key='cover_author')
            company = st.text_input('회사명 (선택)', key='cover_company')
    cover = {'title':title, 'date':str(written), 'author':author, 'company':company}
    with st.container(key='header'):
        st.title('PHOTOSHEET')
        st.write('사진을 넣고 설명만 적으면, 인쇄할 엑셀 사진대지가 완성됩니다.')
    with st.container(key='uploader'):
        upload = components.declare_component('photo_upload', path=str(ROOT / 'uploader'))
        files = upload(key='photo_upload', default=None)
    photos = []
    if files:
        fingerprint = hashlib.sha256(''.join(f['name'] + str(f['mtime']) + f['data'] for f in files).encode()).hexdigest()
        if st.session_state.get('upload_fingerprint') != fingerprint:
            try:
                validate_limits(len(files), [len(base64.b64decode(f['data'])) for f in files])
                parsed = sort_photos([read_photo(f['name'], base64.b64decode(f['data']), f['mtime']) for f in files])
                st.session_state['photos'] = parsed
                st.session_state['upload_fingerprint'] = fingerprint
                st.session_state['editor_revision'] = st.session_state.get('editor_revision', 0) + 1
            except (PhotoError, ValueError) as exc:
                st.error(str(exc))
        else:
            parsed = st.session_state.get('photos', [])
        if st.session_state.get('upload_fingerprint') == fingerprint:
            photos = st.session_state.get('photos', [])
    with st.container(key='summary'):
        st.write(f'사진 {len(photos)}장 · 회전 보정 {sum(p.rotated for p in photos)}장 · 촬영일 없음 {sum(p.taken == "촬영일 없음" for p in photos)}장 · 구분 자동 {sum(auto_category(p.name, p.content) != "기타" and p.category == auto_category(p.name, p.content) for p in photos)}장')
    with st.container(key='table'):
        st.subheader('설명 표')
        st.caption('순서 숫자를 바꾸면 배치 순서가 바뀝니다. 촬영일이 없으면 파일 수정일로 정렬합니다. 파일명·내용의 전·중·후를 자동 채웁니다. 구분은 직접 수정할 수도 있습니다.')
        if photos:
            data = pd.DataFrame([{'순서':p.order,'파일명':p.name,'구분':p.category,'위치':p.location,'내용':p.content,'촬영일':p.taken} for p in photos])
            editor_key = f'description_editor_{st.session_state.get("editor_revision", 0)}'
            def save_edits():
                updates = st.session_state[editor_key]['edited_rows']
                st.session_state['photos'] = [edit_photo(p, updates.get(i, {})) for i, p in enumerate(photos)]
                st.session_state['editor_revision'] += 1
            st.data_editor(data, hide_index=True, use_container_width=True, num_rows='fixed',
                disabled=['파일명'], key=editor_key, on_change=save_edits,
                column_config={'순서':st.column_config.NumberColumn('순서', min_value=1, step=1, required=True),
                               '구분':st.column_config.SelectboxColumn('구분', options=list(CATEGORIES), required=True)})
        else:
            st.info('JPG 또는 PNG 사진을 한 장 이상 넣어 주세요.')
    with st.container(key='preview'):
        st.subheader('미리보기')
        if photos:
            st.caption(f'첫 페이지 · 전체 {len(paginate(photos, slots, grouped))}쪽 · A4 세로')
            components.html(preview_html(photos, slots, grouped, cover), height=1010, scrolling=True)
        else:
            st.caption('사진을 넣으면 첫 페이지가 여기에 나타납니다.')
    excel = None
    if photos:
        excel, _ = make_excel(photos, slots, grouped, cover)
    with st.container(key='save_button'):
        st.download_button('엑셀 사진대지 저장', data=excel or b'', file_name='사진대지.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                           disabled=not photos, type='primary', key='save_excel')
    with st.container(key='size_note'):
        st.write(f'원본 합계 {size_text(sum(p.original_size for p in photos))} → 엑셀 {size_text(len(excel)) if excel else "—"}')
        st.caption('사진은 긴 변 최대 1600px · JPEG 품질 85로 저장합니다. 작은 원본은 엑셀이 더 클 수 있습니다. 사진은 이 컴퓨터에서만 처리합니다.')


if __name__ == '__main__':
    main()
