import base64
from dataclasses import dataclass
from html import escape
from pathlib import Path

from bs4 import BeautifulSoup
import fitz
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
from core.utils.image_utils import validated_image_data_uri


MAX_PREVIEW_SIZE = 20 * 1024 * 1024
PDF_MAX_PAGES = 10
PDF_MIN_TEXT_CHARS_PER_PAGE = 30
PDF_RENDER_MAX_EDGE = 2000
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


def _open_pdf(path):
    try:
        document = fitz.open(str(path))
    except Exception as error:
        raise ValueError(f"PDF {path.name} 无法打开或已损坏") from error
    if document.needs_pass or document.is_encrypted:
        document.close()
        raise ValueError(f"PDF {path.name} 已加密，无法读取")
    return document


def _pdf_page_png_data_uri(page):
    longest = max(page.rect.width, page.rect.height) or 1
    zoom = min(150 / 72, PDF_RENDER_MAX_EDGE / longest)
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
    return validated_image_data_uri(f"data:image/png;base64,{encoded}")


def _pdf_content(path):
    """Return (page_texts, scanned, page_count, image_data_uris)."""
    if path.stat().st_size > MAX_PREVIEW_SIZE:
        raise ValueError("文件超过 20 MB，暂不支持 AI 评分")
    document = _open_pdf(path)
    try:
        page_count = document.page_count
        pages = [document[i] for i in range(min(page_count, PDF_MAX_PAGES))]
        texts = [page.get_text("text").strip() for page in pages]
        total_chars = sum(len(text) for text in texts)
        scanned = total_chars < PDF_MIN_TEXT_CHARS_PER_PAGE * max(len(pages), 1)
        images = []
        if scanned:
            for page in pages:
                data_uri = _pdf_page_png_data_uri(page)
                if data_uri is None:
                    raise ValueError(f"PDF {path.name} 页面渲染失败或超过 8 MB")
                images.append(data_uri)
        return texts, scanned, page_count, tuple(images)
    finally:
        document.close()


def _pdf_scoring_content(path):
    texts, scanned, page_count, images = _pdf_content(path)
    notice = (
        f"（仅评前 {PDF_MAX_PAGES} 页，共 {page_count} 页）"
        if page_count > PDF_MAX_PAGES else ""
    )
    if scanned:
        if not images:
            raise ValueError(f"PDF {path.name} 中没有可评分内容")
        return notice, images
    body = "\n\n".join(
        f"--- 第 {index} 页 ---\n{text}"
        for index, text in enumerate(texts, 1) if text
    )
    return f"{notice}\n{body}".strip(), ()


def _pdf_document(path):
    texts, scanned, page_count, images = _pdf_content(path)
    if scanned:
        if not images:
            raise ValueError(f"PDF {path.name} 中没有可预览内容")
        content = "".join(
            f'<img alt="第 {index} 页" src="{src}">'
            f'<hr>' for index, src in enumerate(images, 1)
        )
    else:
        content = "<hr>".join(
            f"<pre>{escape(text)}</pre>" for text in texts if text
        )
    warnings = ()
    if page_count > PDF_MAX_PAGES:
        warnings = (f"仅预览前 {PDF_MAX_PAGES} 页，共 {page_count} 页",)
    return AttachmentPreviewDocument(
        title=path.name,
        html=_page(path.name, content),
        warnings=warnings,
    )


def render_attachment_preview(file_path):
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdf_document(path)
    if suffix == ".docx":
        return _docx_document(path)
    if suffix in {".md", ".markdown", ".mdown"}:
        return _markdown_document(path)
    return _code_document(path)


def extract_attachment_text(file_path):
    path = Path(file_path)
    if path.stat().st_size > MAX_PREVIEW_SIZE:
        raise ValueError("文件超过 20 MB，暂不支持 AI 评分")

    suffix = path.suffix.lower()
    if suffix == ".docx":
        with path.open("rb") as document_file:
            text = mammoth.extract_raw_text(document_file).value
    elif suffix in {".md", ".markdown", ".mdown"}:
        text = _read_text(path)
    else:
        try:
            get_lexer_for_filename(str(path))
        except ClassNotFound:
            if suffix not in PLAIN_TEXT_EXTENSIONS:
                raise UnsupportedAttachmentPreviewError(
                    f"不支持从 {suffix or '该类型'} 附件提取 AI 评分文本"
                )
        text = _read_text(path)

    if not text.strip():
        raise ValueError(f"附件 {path.name} 中没有可用于评分的文本")
    return text.strip()


def extract_attachment_scoring_content(file_path):
    path = Path(file_path)
    if path.stat().st_size > MAX_PREVIEW_SIZE:
        raise ValueError("文件超过 20 MB，暂不支持 AI 评分")

    image_mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    image_mime_type = image_mime_types.get(path.suffix.lower())
    if image_mime_type:
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError(f"图片附件 {path.name} 超过 8 MB，暂不支持 AI 评分")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        image_data_uri = validated_image_data_uri(
            f"data:{image_mime_type};base64,{encoded}"
        )
        if image_data_uri is None:
            raise ValueError(f"图片附件 {path.name} 格式无效或不受支持")
        return "", (image_data_uri,)

    if path.suffix.lower() == ".pdf":
        return _pdf_scoring_content(path)

    if path.suffix.lower() != ".docx":
        return extract_attachment_text(path), ()

    with path.open("rb") as document_file:
        result = mammoth.convert_to_html(
            document_file,
            convert_image=mammoth.images.img_element(_docx_image),
        )
    document = BeautifulSoup(result.value, "html.parser")
    image_data_uris = []
    for image_index, image in enumerate(document.find_all("img"), 1):
        image_data_uri = validated_image_data_uri(image.get("src", ""))
        if image_data_uri is None:
            raise ValueError(
                f"附件 {path.name} 的第 {image_index} 张图片格式不受支持或超过 8 MB"
            )
        image_data_uris.append(image_data_uri)
        image.replace_with(f"[图片 {image_index}]")

    text = document.get_text("\n", strip=True)
    if not text and not image_data_uris:
        raise ValueError(f"附件 {path.name} 中没有可用于评分的文本或图片")
    return text, tuple(image_data_uris)