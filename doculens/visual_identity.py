"""Single, validated visual identity for the DOCULENS product and video studio.

UI, video, cover art and QC deliberately resolve the *same* immutable preset.
Per-video scripts may change words and footage, never camera behavior or styling.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILE = ROOT / "visual_identity.json"
PRESET = "COMMERCIAL_EDITORIAL_WORKBENCH_V2"

# Canonical style tokens. New software may change its product name and copy,
# but not these aesthetics without intentionally creating a new standard.
FIXED_PALETTE = {
    "background": "#F9F9F8", "toolbar": "#F1F0EF", "surface": "#FDFDFC",
    "raised": "#E9E8E6", "border": "#CFCECA", "text": "#21201C",
    "muted": "#63635E", "accent": "#9C3D2E", "accent_text": "#FDFDFC",
    "success": "#426149", "paper": "#FDFDFC",
}
FIXED_TYPE = {"ui": "SUIT", "korean": "SUIT", "mono": "Consolas"}
FIXED_GEOMETRY = {
    "corner_radius": 4, "line_width": 2, "app_max_width": 1480,
    "short_title_rows": 2, "short_title_safe_max_chars": 18,
    "long_title_safe_max_chars": 34,
}
FIXED_RULES = {
    "camera": "LOCKED", "transitions": "HARD_CUT_ONLY",
    "motion_graphics": False, "style_randomization": False, "max_accents": 1,
    "avoid_gradient": True, "avoid_glassmorphism": True, "avoid_pills": True,
    "use_original_product_capture": True,
}


def load_identity(path=FILE):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if data.get("schema_version") != 1 or data.get("preset") != PRESET or data.get("locked") is not True:
        raise ValueError("Unsupported or unlocked DOCULENS visual identity")
    palette = data.get("palette", {})
    names = ("background", "toolbar", "surface", "raised", "border", "text",
             "muted", "accent", "accent_text", "success", "paper")
    for name in names:
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(palette.get(name, ""))):
            raise ValueError("Invalid design color: " + name)
    if palette != FIXED_PALETTE:
        raise ValueError("Commercial program colors cannot be altered per generated app")
    if data.get("type") != FIXED_TYPE:
        raise ValueError("Commercial program font hierarchy is pinned")
    if data.get("geometry") != FIXED_GEOMETRY:
        raise ValueError("Commercial program geometry is pinned")
    if data.get("rules") != FIXED_RULES:
        raise ValueError("Commercial studio requires static, editorial layouts without camera motion")
    return data


def app_css(identity):
    p = identity["palette"]
    # CSS custom properties ensure each widget shares the exact same tokens.
    tokens = "\n".join("--dl-%s:%s;" % (name.replace("_", "-"), color)
                       for name, color in p.items())
    return """
    <style>
    @font-face{font-family:SUIT;src:url('/app/static/fonts/SUIT-Regular.woff2') format('woff2');font-weight:400;font-display:swap}
    @font-face{font-family:SUIT;src:url('/app/static/fonts/SUIT-SemiBold.woff2') format('woff2');font-weight:600 900;font-display:swap}
    :root {
    """ + tokens + """
    --dl-radius:4px;
    }
    * {scroll-behavior:auto!important;box-sizing:border-box}
    html,body,.stApp,[data-testid="stSidebar"] {
      background:var(--dl-background);color:var(--dl-text);
      font-family:SUIT,"Malgun Gothic",sans-serif!important;
      -webkit-font-smoothing:antialiased;
    }
    [data-testid="stHeader"],#MainMenu,footer,[data-testid="stToolbar"] {visibility:hidden;height:0}
    [data-testid="stAppViewContainer"] {background:var(--dl-background)}
    [data-testid="stSidebar"] {
      background:var(--dl-background)!important;
      border-right:1px solid var(--dl-border);
    }
    [data-testid="stSidebar"][aria-expanded="true"] {min-width:240px;max-width:240px}
    [data-testid="stSidebar"] > div {padding-top:1.0rem}
    .block-container {max-width:1480px;padding:.6rem 2.2rem 2rem}
    [data-testid="stVerticalBlock"] {gap:.65rem}
    button,a,input,textarea,select {font-family:SUIT,"Malgun Gothic",sans-serif!important}
    .stApp p,.stApp li,.stApp label,[data-testid="stMarkdownContainer"]{font-size:15px}
    h1,h2,h3,h4,label,p,li,small,
    [data-testid="stCaptionContainer"],[data-testid="stWidgetLabel"] {
      color:var(--dl-text);
    }
    [data-testid="stCaptionContainer"],small {color:var(--dl-muted)!important}
    .dl-topbar {
      min-height:40px;display:flex;align-items:center;justify-content:space-between;
      gap:16px;border-bottom:1px solid var(--dl-border);
      padding:0 0 8px;margin-bottom:8px;
    }
    .dl-brand{font:22px Georgia,serif;letter-spacing:-.04em;color:var(--dl-text)}
    .dl-menubar{display:flex;align-items:center;gap:16px;font:12px "Segoe UI","Malgun Gothic",sans-serif;color:var(--dl-muted)}
    .dl-menubar span{padding:2px 4px;border-bottom:2px solid transparent}
    .dl-menubar span.active{color:var(--dl-text);border-bottom-color:var(--dl-accent);font-weight:600}
    .dl-track {color:var(--dl-muted);font:13px/1.5 SUIT,sans-serif}
    .dl-live{color:var(--dl-muted);font:14px SUIT,sans-serif}
    .dl-heading{
      padding:0 0 6px;display:flex;justify-content:space-between;align-items:end;
      gap:20px;
    }
    .dl-heading .kicker {font:600 14px SUIT,sans-serif;color:var(--dl-accent);margin-bottom:4px}
    .dl-heading h1{font-size:22px;font-weight:600;letter-spacing:-.03em;margin:0 0 4px;line-height:1.3;padding:0}
    .dl-heading p{font-size:15px;line-height:1.65;color:var(--dl-muted);margin:0;word-break:keep-all}
    .dl-heading .serial {
      text-align:right;color:var(--dl-muted);font:13px/1.65 SUIT,sans-serif;
      white-space:nowrap;padding:6px 0;
    }
    .dl-section {
      display:flex;align-items:center;justify-content:space-between;gap:16px;
      border-top:1px solid var(--dl-border);
      padding:10px 0 2px;margin-top:6px;
    }
    .dl-section .left {display:flex;align-items:center;gap:10px}
    .dl-section .index{
      font:20px Georgia,serif;color:var(--dl-accent);padding-right:4px;
    }
    .dl-section h2 {margin:0;font-size:18px;letter-spacing:-.02em;font-weight:600}
    .dl-section .detail{color:var(--dl-muted);font:14px SUIT,sans-serif}
    .dl-statusbar{
      display:grid;grid-template-columns:repeat(3,minmax(0,1fr));
      background:var(--dl-surface);border-top:1px solid var(--dl-border);border-bottom:1px solid var(--dl-border);margin:8px 0 12px;
    }
    .dl-stat-unit{padding:12px 20px;border-right:1px solid var(--dl-border);min-width:0}
    .dl-stat-unit:last-child{border-right:none}
    .dl-stat-label{font:14px SUIT,sans-serif;color:var(--dl-muted);display:flex;justify-content:space-between}
    .dl-stat-value{
      font:600 24px/1.3 SUIT,"Malgun Gothic",sans-serif;
      color:var(--dl-text);font-variant-numeric:tabular-nums;letter-spacing:-.025em;margin-top:4px;
    }
    .dl-panel{
      padding:6px 0 8px 24px;border-left:1px solid var(--dl-border);
    }
    .dl-panel-header{
      font:600 14px SUIT,sans-serif;color:var(--dl-text);
      padding-bottom:8px;margin-bottom:4px;
      display:flex;justify-content:space-between;
    }
    .dl-kv-row{
      display:flex;justify-content:space-between;align-items:center;
      padding:8px 0;font-size:13px;gap:14px;
    }
    .dl-kv-row:last-child{border-bottom:none}
    .dl-kv-key{color:var(--dl-muted)}
    .dl-kv-val{font:600 13px SUIT,sans-serif;color:var(--dl-text);text-align:right;font-variant-numeric:tabular-nums}
    .dl-notice{
      font-size:15px;line-height:1.6;padding:8px 0;
      color:var(--dl-muted);
      display:flex;justify-content:space-between;align-items:center;
    }
    .dl-muted-note{color:var(--dl-muted);font-size:13px;line-height:1.8;word-break:keep-all}
    .dl-review-panel{
      background:var(--dl-surface);border:1px solid var(--dl-border);
      border-left:3px solid var(--dl-accent);padding:14px 16px;margin:8px 0;
    }
    .dl-review-panel .dl-secondary{color:var(--dl-muted);font-size:13px;line-height:1.65}
    .dl-review-warning{color:var(--dl-accent);font-size:13px;font-weight:600;line-height:1.6}
    [data-testid="stSelectbox"] [aria-selected="true"]{background:var(--dl-raised)!important;color:var(--dl-text)!important}
    input:focus-visible,textarea:focus-visible,[role="combobox"]:focus-visible{
      outline:2px solid var(--dl-accent)!important;outline-offset:2px;
    }
    .dl-sidebar-title{
      font:23px Georgia,serif;letter-spacing:-.035em;margin:12px 0 30px;
      padding:0 8px 16px;border-bottom:1px solid var(--dl-border);
      display:flex;align-items:center;justify-content:space-between;
    }
    .dl-sidebar-title span{font:12px SUIT,sans-serif;color:var(--dl-muted)}
    .dl-rail-label{
      padding:14px 8px 6px;
      font:600 12px SUIT,sans-serif;color:var(--dl-muted);
    }
    .dl-rail-row{
      display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 8px;
      font-size:14px;color:var(--dl-text);margin-top:3px;
    }
    .dl-rail-row.active{color:var(--dl-accent);font-weight:600}
    .dl-rail-row i{font:14px Georgia,serif;color:var(--dl-muted);font-style:normal;margin-right:8px}
    .dl-rail-meta{font:12px SUIT,sans-serif;color:var(--dl-muted)}
    [data-testid="stFileUploaderDropzone"]{
      background:var(--dl-surface)!important;border:1px dashed var(--dl-border)!important;
      border-radius:var(--dl-radius)!important;padding:.9rem 1.2rem!important;min-height:110px;
    }
    .stButton > button,.stDownloadButton > button{
      border-radius:var(--dl-radius)!important;border:1px solid var(--dl-border)!important;
      background:var(--dl-surface)!important;color:var(--dl-text)!important;
      font-weight:600!important;font-size:16px!important;min-height:46px!important;
    }
    .stButton > button[kind="primary"],.stDownloadButton > button[kind="primary"]{
      background:var(--dl-accent)!important;color:var(--dl-accent-text)!important;
      border-color:var(--dl-accent)!important;font-weight:700!important;
    }
    [data-testid="stBaseButton-primaryFormSubmit"]{
      background:var(--dl-accent)!important;color:var(--dl-accent-text)!important;
      border:1px solid var(--dl-accent)!important;border-radius:var(--dl-radius)!important;
      font-weight:700!important;min-height:42px;padding:0 22px!important;
    }
    [data-testid="stBaseButton-primaryFormSubmit"] p,
    .stButton > button[kind="primary"] p,.stDownloadButton > button[kind="primary"] p{
      color:var(--dl-accent-text)!important;
    }
    [data-testid="stButtonGroup"] button{
      border-radius:var(--dl-radius)!important;border:1px solid var(--dl-border)!important;
      background:var(--dl-surface)!important;color:var(--dl-text)!important;min-height:38px;font-size:15px!important;
    }
    [data-testid="stButtonGroup"] button[kind$="Active"],[data-testid="stButtonGroup"] button[aria-checked="true"]{
      background:var(--dl-raised)!important;border-color:var(--dl-text)!important;font-weight:700!important;
      box-shadow:inset 0 -2px 0 var(--dl-accent)!important;
    }
    [data-testid="stButtonGroup"] button p{font-size:15px!important;color:var(--dl-text)!important}
    .dl-edit-count{font:600 15px/1.6 SUIT,sans-serif;color:var(--dl-text);margin:2px 0 10px;display:block;
      border-left:3px solid var(--dl-accent);padding-left:10px}
    .dl-file-status{border:1px solid var(--dl-border);background:var(--dl-surface);border-radius:var(--dl-radius)}
    .dl-file-row{display:flex;justify-content:space-between;gap:16px;padding:7px 14px;font-size:15px;
      border-bottom:1px solid var(--dl-border);font-variant-numeric:tabular-nums}
    .dl-file-row:last-child{border-bottom:none}
    .dl-file-row b{font-weight:600;color:var(--dl-muted)}
    .dl-file-row[data-state="읽는"] b{color:var(--dl-accent)}
    .dl-file-row[data-state="완료"] b{color:var(--dl-success)}
    .dl-file-row[data-state="실패"] b{color:var(--dl-accent)}
    [data-testid="stDataFrame"],[data-testid="stDataEditor"]{
      border:1px solid var(--dl-border)!important;border-radius:var(--dl-radius)!important;
      background:var(--dl-surface)!important;
    }
    [data-testid="stAlert"]{
      background:var(--dl-surface)!important;color:var(--dl-text)!important;
      border:1px solid var(--dl-border)!important;border-left:3px solid var(--dl-accent)!important;
      border-radius:var(--dl-radius)!important;
    }
    button:focus-visible,a:focus-visible{outline:2px solid var(--dl-accent)!important;outline-offset:3px}
    .stButton>button:disabled{opacity:.5!important;cursor:not-allowed!important}
    [data-testid="stFileUploaderDropzoneInstructions"] small{color:var(--dl-muted)!important}
    @media(max-width:930px){
      .block-container{padding:.75rem 1rem 2rem}
      .dl-heading,.dl-topbar,.dl-section{flex-direction:column;align-items:flex-start}
      .dl-statusbar{grid-template-columns:1fr}
      .dl-stat-unit{border-right:none;border-bottom:1px solid var(--dl-border)}
    }
    </style>
    """
