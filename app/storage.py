import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_DOCUMENT_EXTENSIONS = {"pdf"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024      # 5 MB
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024  # 10 MB

# Magic byte signatures for MIME verification
# Keys are the first N bytes of a valid file of that type
_IMAGE_SIGNATURES = [
    (bytes([0xFF, 0xD8, 0xFF]),          "image/jpeg"),   # JPEG
    (bytes([0x89, 0x50, 0x4E, 0x47,
            0x0D, 0x0A, 0x1A, 0x0A]),   "image/png"),    # PNG
    (b"RIFF",                           "image/webp"),   # WebP (check RIFF + WEBP marker)
]
_PDF_SIGNATURE = b"%PDF"


def _sniff_mime(header: bytes) -> str:
    """Return a rough MIME type string based on the first bytes of a file."""
    for sig, mime in _IMAGE_SIGNATURES:
        if mime == "image/webp":
            # WebP: bytes 0-3 == RIFF and bytes 8-11 == WEBP
            if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
                return mime
        elif header[:len(sig)] == sig:
            return mime
    if header[:4] == _PDF_SIGNATURE:
        return "application/pdf"
    return "application/octet-stream"


def _verify_image_header(file_storage):
    """
    Read the first 12 bytes and confirm the file is actually an image.
    Rewinds the stream to 0 before returning.
    Raises ValueError if the header does not match an allowed image type.
    """
    header = file_storage.read(12)
    file_storage.seek(0)
    mime = _sniff_mime(header)
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        raise ValueError(
            "File content does not match an allowed image format (jpg, png, webp). "
            "Uploading disguised files is not permitted."
        )


def _verify_pdf_header(file_storage):
    """
    Read the first 4 bytes and confirm the file is actually a PDF.
    Rewinds the stream to 0 before returning.
    Raises ValueError if the header does not start with the PDF signature.
    """
    header = file_storage.read(4)
    file_storage.seek(0)
    if header != _PDF_SIGNATURE:
        raise ValueError(
            "File content does not match a PDF. "
            "Uploading disguised files is not permitted."
        )


def _base_upload_path():
    return current_app.config.get(
        "UPLOAD_FOLDER",
        os.path.join(current_app.root_path, "..", "uploads"),
    )


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def allowed_image(filename):
    return "." in filename and            filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def allowed_document(filename):
    return "." in filename and            filename.rsplit(".", 1)[1].lower() in ALLOWED_DOCUMENT_EXTENSIONS


def save_lawyer_photo(file_storage, user_id):
    if not allowed_image(file_storage.filename):
        raise ValueError("Invalid image format. Allowed: jpg, jpeg, png, webp")

    # Verify actual file content matches claimed extension
    _verify_image_header(file_storage)

    file_storage.seek(0, 2)
    size = file_storage.tell()
    file_storage.seek(0)
    if size > MAX_IMAGE_BYTES:
        raise ValueError("Image must be under 5 MB")

    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    filename = f"profile_{uuid.uuid4().hex}.{ext}"
    folder = os.path.join(_base_upload_path(), "lawyers", "photos", str(user_id))
    _ensure_dir(folder)
    file_storage.save(os.path.join(folder, filename))
    return os.path.join("lawyers", "photos", str(user_id), filename)


def save_lawyer_licence(file_storage, user_id):
    if not allowed_document(file_storage.filename):
        raise ValueError("Invalid format. Only PDF allowed.")

    # Verify actual file content is a PDF
    _verify_pdf_header(file_storage)

    file_storage.seek(0, 2)
    size = file_storage.tell()
    file_storage.seek(0)
    if size > MAX_DOCUMENT_BYTES:
        raise ValueError("Document must be under 10 MB")

    filename = f"licence_{uuid.uuid4().hex}.pdf"
    folder = os.path.join(_base_upload_path(), "lawyers", "licences", str(user_id))
    _ensure_dir(folder)
    file_storage.save(os.path.join(folder, filename))
    return os.path.join("lawyers", "licences", str(user_id), filename)


def delete_file(relative_path):
    if not relative_path:
        return
    try:
        os.remove(os.path.join(_base_upload_path(), relative_path))
    except FileNotFoundError:
        pass


def get_upload_url(relative_path):
    if not relative_path:
        return None
    return "/uploads/" + relative_path.replace(os.sep, "/")
