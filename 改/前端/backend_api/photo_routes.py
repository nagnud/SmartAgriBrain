from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from database import get_db
from photo_service import (
    delete_disease_photo,
    get_disease_photo_or_raise,
    list_disease_photos,
    save_disease_photo,
    save_disease_photo_analysis,
    to_disease_photo_info,
)
from schemas import (
    DiseasePhotoAnalysisRequest,
    DiseasePhotoInfo,
    DiseasePhotoListResponse,
    OperationSuccess,
)


router = APIRouter(prefix="/api/v1/photos/disease", tags=["disease-photos"])


def public_upload_url(request: Request, relative_path: str) -> str:
    return str(request.url_for("uploads", path=relative_path))


@router.post("/upload", response_model=DiseasePhotoInfo)
async def post_disease_photo_upload(
    request: Request,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> DiseasePhotoInfo:
    photo = await save_disease_photo(db, image)
    return to_disease_photo_info(photo, public_upload_url(request, photo.relative_path))


@router.get("/list", response_model=DiseasePhotoListResponse)
def get_disease_photo_list(request: Request, db: Session = Depends(get_db)) -> DiseasePhotoListResponse:
    photos = list_disease_photos(db)
    return DiseasePhotoListResponse(
        items=[to_disease_photo_info(photo, public_upload_url(request, photo.relative_path)) for photo in photos]
    )


@router.get("/{photo_id}", response_model=DiseasePhotoInfo)
def get_disease_photo_detail(
    photo_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> DiseasePhotoInfo:
    photo = get_disease_photo_or_raise(db, photo_id)
    return to_disease_photo_info(photo, public_upload_url(request, photo.relative_path))


@router.post("/{photo_id}/analysis", response_model=DiseasePhotoInfo)
def post_disease_photo_analysis(
    photo_id: int,
    payload: DiseasePhotoAnalysisRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> DiseasePhotoInfo:
    photo = save_disease_photo_analysis(db, photo_id, payload.analysisResult)
    return to_disease_photo_info(photo, public_upload_url(request, photo.relative_path))


@router.delete("/{photo_id}", response_model=OperationSuccess)
def delete_disease_photo_detail(photo_id: int, db: Session = Depends(get_db)) -> OperationSuccess:
    delete_disease_photo(db, photo_id)
    return OperationSuccess(success=True)
