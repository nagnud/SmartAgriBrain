from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from photo_models import DiseasePhoto
from schemas import DiseasePhotoInfo


DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "local_demo")
BACKEND_DIR = Path(__file__).resolve().parent
UPLOAD_ROOT = BACKEND_DIR / "uploads"
DISEASE_UPLOAD_ROOT = UPLOAD_ROOT / "disease"
MAX_DISEASE_PHOTO_BYTES = int(os.getenv("DISEASE_PHOTO_MAX_BYTES", str(10 * 1024 * 1024)))

ALLOWED_IMAGE_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def ensure_upload_root() -> None:
    DISEASE_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


def now_text(value: datetime | None = None) -> str:
    current = value or datetime.utcnow()
    return current.strftime("%Y-%m-%d %H:%M")


def clean_original_name(filename: str | None) -> str:
    name = Path(filename or "disease-photo").name.strip()
    return name[:260] if name else "disease-photo"


def normalized_content_type(upload: UploadFile) -> str:
    return (upload.content_type or "").split(";", 1)[0].strip().lower()


def extension_for_upload(upload: UploadFile) -> tuple[str, str]:
    content_type = normalized_content_type(upload)
    suffix = Path(upload.filename or "").suffix.lower()

    if content_type in ALLOWED_IMAGE_MIME_TYPES:
        if suffix in ALLOWED_IMAGE_EXTENSIONS:
            return (".jpg" if suffix == ".jpeg" else suffix, content_type)
        return ALLOWED_IMAGE_MIME_TYPES[content_type], content_type

    if suffix in ALLOWED_IMAGE_EXTENSIONS:
        guessed_type = "image/jpeg" if suffix in {".jpg", ".jpeg"} else f"image/{suffix.removeprefix('.')}"
        return (".jpg" if suffix == ".jpeg" else suffix, guessed_type)

    raise HTTPException(status_code=400, detail="Only jpg, png, and webp images are supported.")


def to_disease_photo_info(photo: DiseasePhoto, url: str) -> DiseasePhotoInfo:
    return DiseasePhotoInfo(
        photoId=photo.id,
        url=url,
        originalName=photo.original_name,
        mimeType=photo.mime_type,
        size=photo.size,
        createdAt=now_text(photo.created_at),
        analysisResult=photo.analysis_result,
    )


def list_disease_photos(db: Session, user_id: str = DEFAULT_USER_ID) -> List[DiseasePhoto]:
    return (
        db.query(DiseasePhoto)
        .filter(DiseasePhoto.user_id == user_id)
        .order_by(DiseasePhoto.created_at.desc(), DiseasePhoto.id.desc())
        .all()
    )


def get_disease_photo_or_raise(db: Session, photo_id: int, user_id: str = DEFAULT_USER_ID) -> DiseasePhoto:
    photo = (
        db.query(DiseasePhoto)
        .filter(DiseasePhoto.id == photo_id, DiseasePhoto.user_id == user_id)
        .first()
    )
    if photo is None:
        raise HTTPException(status_code=404, detail="Disease photo not found.")
    return photo


async def save_disease_photo(db: Session, upload: UploadFile, user_id: str = DEFAULT_USER_ID) -> DiseasePhoto:
    ensure_upload_root()
    extension, content_type = extension_for_upload(upload)
    content = await upload.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")
    if len(content) > MAX_DISEASE_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded image exceeds the 10MB limit.")

    now = datetime.utcnow()
    date_dir = DISEASE_UPLOAD_ROOT / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{extension}"
    file_path = date_dir / stored_name
    file_path.write_bytes(content)
    relative_path = file_path.relative_to(UPLOAD_ROOT).as_posix()

    photo = DiseasePhoto(
        user_id=user_id,
        original_name=clean_original_name(upload.filename),
        stored_name=stored_name,
        relative_path=relative_path,
        mime_type=content_type,
        size=len(content),
        analysis_result=None,
        created_at=now,
        updated_at=now,
    )
    db.add(photo)
    try:
        db.commit()
    except Exception:
        db.rollback()
        if file_path.exists():
            file_path.unlink()
        raise
    db.refresh(photo)
    return photo


def save_disease_photo_analysis(
    db: Session,
    photo_id: int,
    analysis_result: Dict[str, Any],
    user_id: str = DEFAULT_USER_ID,
) -> DiseasePhoto:
    photo = get_disease_photo_or_raise(db, photo_id, user_id)
    photo.analysis_result = analysis_result
    photo.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(photo)
    return photo


def delete_disease_photo(db: Session, photo_id: int, user_id: str = DEFAULT_USER_ID) -> None:
    photo = get_disease_photo_or_raise(db, photo_id, user_id)
    file_path = (UPLOAD_ROOT / photo.relative_path).resolve()
    upload_root = UPLOAD_ROOT.resolve()
    db.delete(photo)
    db.commit()

    if file_path == upload_root or upload_root not in file_path.parents:
        return
    if file_path.is_file():
        file_path.unlink()
