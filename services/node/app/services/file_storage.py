import re
from pathlib import Path

from fastapi import UploadFile

from ..config import settings

ALLOWED_MIME_TYPES: dict[str, set[str]] = {
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".mp4": {"video/mp4"},
    ".webm": {"video/webm", "audio/webm"},
    ".mp3": {"audio/mpeg"},
    ".wav": {"audio/wav", "audio/x-wav"},
    ".txt": {"text/plain"},
    ".pdf": {"application/pdf"},
}


class InvalidUploadError(ValueError):
    pass


def storage_root() -> Path:
    return Path(settings.storage_dir).resolve()


def safe_filename(filename: str | None) -> tuple[str, str]:
    if not filename:
        raise InvalidUploadError("A filename is required")
    path = Path(filename)
    if path.name != filename or filename in {".", ".."}:
        raise InvalidUploadError("Filename must not contain a path")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,254}", filename):
        raise InvalidUploadError("Filename contains unsupported characters")
    extension = path.suffix.lower()
    if extension not in ALLOWED_MIME_TYPES:
        raise InvalidUploadError("File extension is not allowed")
    return filename, extension


def validate_upload(filename: str | None, content_type: str | None) -> tuple[str, str]:
    clean_name, extension = safe_filename(filename)
    if content_type not in ALLOWED_MIME_TYPES[extension]:
        raise InvalidUploadError("File type does not match the allowed extension")
    return clean_name, extension


def node_directory(node_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", node_id):
        raise InvalidUploadError("Configured node identity is not a safe storage name")
    directory = storage_root() / node_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def resolve_storage_key(storage_key: str) -> Path:
    root = storage_root()
    candidate = (root / storage_key).resolve()
    if root != candidate and root not in candidate.parents:
        raise InvalidUploadError("Invalid storage reference")
    return candidate


async def save_upload(upload: UploadFile, node_id: str, evidence_id: str) -> tuple[str, int]:
    filename, _ = validate_upload(upload.filename, upload.content_type)
    extension = Path(filename).suffix.lower()
    directory = node_directory(node_id)
    target = directory / f"{evidence_id}{extension}"
    size = 0
    try:
        with target.open("wb") as destination:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_size_mb * 1024 * 1024:
                    raise InvalidUploadError(f"File exceeds {settings.max_upload_size_mb} MB limit")
                destination.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target.relative_to(storage_root()).as_posix(), size
