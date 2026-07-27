from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from kb_service import (
    add_knowledge_item,
    analyze_knowledge,
    create_knowledge_base,
    delete_knowledge_base,
    delete_knowledge_item,
    list_knowledge_bases,
    list_knowledge_items,
    update_knowledge_base,
    update_knowledge_item,
)
from schemas import (
    KnowledgeAnalyzeRequest,
    KnowledgeAnalyzeResult,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseDeleteRequest,
    KnowledgeBaseInfo,
    KnowledgeBaseListResponse,
    KnowledgeBaseUpdateRequest,
    KnowledgeItemDeleteRequest,
    KnowledgeItemListResponse,
    KnowledgeItemUpdateRequest,
    KnowledgeTextAddRequest,
    KnowledgeTextAddResult,
    OperationSuccess,
)


router = APIRouter(prefix="/api/v1/kb", tags=["knowledge-base"])


def request_error(error: ValueError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(error))


@router.get("/list", response_model=KnowledgeBaseListResponse)
def get_kb_list(db: Session = Depends(get_db)) -> KnowledgeBaseListResponse:
    return KnowledgeBaseListResponse(items=list_knowledge_bases(db))


@router.get("/items", response_model=KnowledgeItemListResponse)
def get_kb_items(kbId: int = Query(..., ge=1), db: Session = Depends(get_db)) -> KnowledgeItemListResponse:
    try:
        items = list_knowledge_items(db, kbId)
    except ValueError as error:
        raise request_error(error) from error
    return KnowledgeItemListResponse(items=items)


@router.post("/create", response_model=KnowledgeBaseInfo)
def post_kb_create(payload: KnowledgeBaseCreateRequest, db: Session = Depends(get_db)) -> KnowledgeBaseInfo:
    return create_knowledge_base(db, payload.name, payload.description)


@router.post("/update", response_model=KnowledgeBaseInfo)
def post_kb_update(payload: KnowledgeBaseUpdateRequest, db: Session = Depends(get_db)) -> KnowledgeBaseInfo:
    try:
        return update_knowledge_base(db, payload.kbId, payload.name, payload.description)
    except ValueError as error:
        raise request_error(error) from error


@router.post("/delete", response_model=OperationSuccess)
def post_kb_delete(payload: KnowledgeBaseDeleteRequest, db: Session = Depends(get_db)) -> OperationSuccess:
    try:
        delete_knowledge_base(db, payload.kbId)
    except ValueError as error:
        raise request_error(error) from error
    return OperationSuccess(success=True)


@router.post("/add_text", response_model=KnowledgeTextAddResult)
def post_kb_add_text(payload: KnowledgeTextAddRequest, db: Session = Depends(get_db)) -> KnowledgeTextAddResult:
    try:
        return add_knowledge_item(db, payload.kbId, payload.title, payload.content)
    except ValueError as error:
        raise request_error(error) from error


@router.post("/item/update", response_model=KnowledgeTextAddResult)
def post_kb_item_update(payload: KnowledgeItemUpdateRequest, db: Session = Depends(get_db)) -> KnowledgeTextAddResult:
    try:
        return update_knowledge_item(db, payload.kbId, payload.itemId, payload.title, payload.content)
    except ValueError as error:
        raise request_error(error) from error


@router.post("/item/delete", response_model=OperationSuccess)
def post_kb_item_delete(payload: KnowledgeItemDeleteRequest, db: Session = Depends(get_db)) -> OperationSuccess:
    try:
        delete_knowledge_item(db, payload.kbId, payload.itemId)
    except ValueError as error:
        raise request_error(error) from error
    return OperationSuccess(success=True)


@router.post("/analyze", response_model=KnowledgeAnalyzeResult)
def post_kb_analyze(payload: KnowledgeAnalyzeRequest, db: Session = Depends(get_db)) -> KnowledgeAnalyzeResult:
    try:
        return analyze_knowledge(db, payload.kbId, payload.fieldId, payload.question)
    except ValueError as error:
        raise request_error(error) from error
