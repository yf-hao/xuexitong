import base64
from dataclasses import dataclass
from html import escape
from pathlib import Path

import mammoth
import markdown
import nh3
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.token import STANDARD_TYPES
from pygments.util import ClassNotFound


MAX_PREVIEW_SIZE = 20 * 1024 * 1024
PLAIN_TEXT_EXTENSIONS = {
    ".conf", ".config", ".csv", ".diff", ".env", ".ini", ".lock",
    ".log", ".out", ".patch", ".properties", ".txt",
}
PREVIEW_TAGS = {
    "a", "abbr", "blockquote", "br", "caption", "code", "dd", "del",
    "div", "dl", "dt", "em", "h1", "h2", "h3", "h4", "hr", "img",
    "li", "ol", "p", "pre", "s", "span", "strong", "sub", "sup",
    "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
}
PREVIEW_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"alt", "src", "title"},
    "td": {"colspan", "rowspan", "align"},
    "th": {"colspan", "rowspan", "align"},
}
PREVIEW_CLASSES = {
    "div": {"codehilite", "highlight"},
    "span": set(STANDARD_TYPES.values()) | {"hll"},
}


class UnsupportedAttachmentPreviewError(ValueError):
    pass


@dataclass(frozen=True)
class AttachmentPreviewDocument:
    title: str
    html: str
    warnings: tuple[str, ...] = ()


def _page(title, content, extra_css=""):
    safe_title = escape(title)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title><style>
:root {{ --preview-bg: #ffffff; --preview-text: #202124; --preview-code-bg: #f5f6f7; --preview-border: #d8dadd; --preview-muted: #73777d; --preview-link: #0969da; }}
body {{ color: var(--preview-text); background: var(--preview-bg); font: 14px/1.65 sans-serif; margin: 24px auto; max-width: 960px; padding: 0 24px; }}
h1, h2, h3, h4 {{ line-height: 1.3; margin: 1.2em 0 .55em; }}
p {{ margin: .65em 0; }}
pre {{ overflow-x: auto; padding: 14px; background: var(--preview-code-bg); border: 1px solid var(--preview-border); border-radius: 4px; }}
code {{ font-family: Menlo, Consolas, monospace; }}
a {{ color: var(--preview-link); }}
table {{ border-collapse: collapse; max-width: 100%; }}
th, td {{ border: 1px solid var(--preview-border); padding: 6px 9px; }}
img {{ max-width: 100%; height: auto; }}
.highlight {{ overflow-x: auto; }}
.highlighttable {{ border: 0; width: 100%; }}
.highlighttable td {{ border: 0; padding: 0; }}
.linenos {{ color: var(--preview-muted); user-select: none; padding-right: 12px !important; text-align: right; }}
{extra_css}
</style></head><body>{content}</body></html>"""


def _pygments_styles():
    light_formatter = HtmlFormatter(style="friendly")
    dark_formatter = HtmlFormatter(style="monokai")
    return "\n".join((
        light_formatter.get_style_defs('body[data-theme="light"] .highlight'),
        dark_formatter.get_style_defs('body[data-theme="dark"] .highlight'),
    ))


def _sanitize_html(content):
    return nh3.clean(
        content,
        tags=PREVIEW_TAGS,
        attributes=PREVIEW_ATTRIBUTES,
        url_schemes={"http", "https", "mailto", "data"},
        allowed_classes=PREVIEW_CLASSES,
        strip_comments=True,
    )


def _read_text(path):
    if path.stat().st_size > MAX_PREVIEW_SIZE:
        raise ValueError("文件超过 20 MB，暂不支持应用内预览")
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _code_document(path):
    source = _read_text(path)
    try:
        lexer = get_lexer_for_filename(str(path), stripnl=False)
    except ClassNotFound:
        if path.suffix.lower() not in PLAIN_TEXT_EXTENSIONS:
            raise UnsupportedAttachmentPreviewError(
                f"没有找到 {path.suffix or '该类型'} 的代码解析器"
            )
        lexer = TextLexer(stripnl=False)

    formatter = HtmlFormatter(linenos="table")
    highlighted = highlight(source, lexer, formatter)
    return AttachmentPreviewDocument(
        title=path.name,
        html=_page(path.name, highlighted, _pygments_styles()),
    )


def _markdown_document(path):
    source = _read_text(path)
    converter = markdown.Markdown(extensions=[
        FencedCodeExtension(),
        TableExtension(),
        CodeHiliteExtension(
            css_class="highlight", guess_lang=True, pygments_style="friendly"
        ),
    ])
    rendered = converter.convert(source)
    sanitized = _sanitize_html(rendered)
    return AttachmentPreviewDocument(
        title=path.name,
        html=_page(path.name, sanitized, _pygments_styles()),
    )


def _docx_image(image):
    with image.open() as image_file:
        encoded = base64.b64encode(image_file.read()).decode("ascii")
    return {"src": f"data:{image.content_type};base64,{encoded}"}


def _docx_document(path):
    if path.stat().st_size > MAX_PREVIEW_SIZE:
        raise ValueError("文件超过 20 MB，暂不支持应用内预览")
    with path.open("rb") as document_file:
        result = mammoth.convert_to_html(
            document_file,
            convert_image=mammoth.images.img_element(_docx_image),
        )
    sanitized = _sanitize_html(result.value)
    warnings = tuple(message.message for message in result.messages)
    return AttachmentPreviewDocument(
        title=path.name,
        html=_page(path.name, sanitized),
        warnings=warnings,
    )


def render_attachment_preview(file_path):
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _docx_document(path)
    if suffix in {".md", ".markdown", ".mdown"}:
        return _markdown_document(path)
    return _code_document(path)