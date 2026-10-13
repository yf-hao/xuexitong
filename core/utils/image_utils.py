import base64
import binascii
import re


def validated_image_data_uri(value):
    match = re.fullmatch(
        r"data:image/(png|jpeg|gif|webp|bmp);base64,([A-Za-z0-9+/]*={0,2})",
        str(value or ""),
        flags=re.IGNORECASE,
    )
    if match is None or len(match.group(2)) > 11_184_812:
        return None
    try:
        image_bytes = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(image_bytes) > 8 * 1024 * 1024:
        return None

    image_type = match.group(1).lower()
    signatures = {
        "png": image_bytes.startswith(b"\x89PNG\r\n\x1a\n"),
        "jpeg": image_bytes.startswith(b"\xff\xd8\xff"),
        "gif": image_bytes.startswith((b"GIF87a", b"GIF89a")),
        "webp": (
            image_bytes.startswith(b"RIFF")
            and image_bytes[8:12] == b"WEBP"
        ),
        "bmp": image_bytes.startswith(b"BM"),
    }
    if not signatures[image_type]:
        return None
    return f"data:image/{image_type};base64,{match.group(2)}"