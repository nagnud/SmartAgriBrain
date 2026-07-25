from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agri_source_service import list_source_infos, test_agri_source, update_source_enabled
from database import get_db
from schemas import AgriSourceListResponse, AgriSourceTestResponse, AgriSourceUpdateRequest, AgriSourceInfo


router = APIRouter(prefix="/api/v1/agri", tags=["online-agriculture-sources"])


@router.get("/sources", response_model=AgriSourceListResponse)
def get_agri_sources(db: Session = Depends(get_db)) -> AgriSourceListResponse:
    return AgriSourceListResponse(items=list_source_infos(db))


@router.patch("/sources/{source_id}", response_model=AgriSourceInfo)
def patch_agri_source(
    source_id: str,
    payload: AgriSourceUpdateRequest,
    db: Session = Depends(get_db),
) -> AgriSourceInfo:
    try:
        return update_source_enabled(db, source_id, payload.enabled)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="没有找到该农业知识源。") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/sources/{source_id}/test", response_model=AgriSourceTestResponse)
def post_test_agri_source(source_id: str, db: Session = Depends(get_db)) -> AgriSourceTestResponse:
    try:
        source, sample_count = test_agri_source(db, source_id)
        return AgriSourceTestResponse(source=source, sampleCount=sample_count)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="没有找到该农业知识源。") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"农业知识源连接失败：{error}") from error
