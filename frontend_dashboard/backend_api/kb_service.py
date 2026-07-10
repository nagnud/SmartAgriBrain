from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Iterable, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from deepseek_service import call_deepseek_chat, deepseek_api_key, strip_code_fence
from kb_models import KnowledgeBase, KnowledgeChunk, KnowledgeItem
from schemas import (
    KnowledgeAnalyzeResult,
    KnowledgeBaseInfo,
    KnowledgeItemInfo,
    KnowledgeReference,
    KnowledgeTextAddResult,
)


DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "local_demo")
CHUNK_SIZE = 420


SEED_BASES = [
    {
        "name": "番茄管理知识库",
        "description": "温室番茄水肥、光照、CO2 和病害管理经验",
        "items": [
            {
                "title": "番茄高湿管理原则",
                "content": "番茄结果期应避免空气湿度长期高于 85%，高湿会增加灰霉病、霜霉病和叶斑病风险，应加强通风并减少叶面结露。",
            },
            {
                "title": "土壤 EC 管理",
                "content": "番茄基质 EC 建议维持在 1.5 到 2.4 mS/cm，过高会造成盐害，过低会影响养分供应。",
            },
        ],
    },
    {
        "name": "病虫害防治库",
        "description": "叶斑病、霜霉病、白粉病等识别与处理建议",
        "items": [
            {
                "title": "叶斑病早期处理",
                "content": "叶片出现黄褐色不规则斑点时，应降低湿度、清除病叶并观察 24 小时扩展情况，必要时进行人工确认。",
            },
            {
                "title": "霜霉病风险条件",
                "content": "霜霉病常在高湿、通风不足、昼夜温差大时发生，早期可见黄斑，潮湿时叶背可能出现霉层。",
            },
        ],
    },
    {
        "name": "设备控制规则库",
        "description": "风机、水泵、补光灯、卷帘联动规则",
        "items": [
            {
                "title": "卷帘与补光联动",
                "content": "当自然光照不足时优先打开卷帘并观察光照变化，若仍低于目标区间再开启补光灯。",
            },
            {
                "title": "通风安全规则",
                "content": "风机单次建议运行 5 到 10 分钟，执行后需要回传状态，避免长时间通风造成温度快速下降。",
            },
        ],
    },
]


def now_text(value: Optional[datetime] = None) -> str:
    current = value or datetime.utcnow()
    return current.strftime("%Y-%m-%d %H:%M")


def safe_text(value: object, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def split_chunks(content: str, size: int = CHUNK_SIZE) -> List[str]:
    text = safe_text(content)
    if not text:
        return []

    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    chunks: List[str] = []
    current = ""
    for paragraph in paragraphs or [text]:
        if len(paragraph) > size:
            if current:
                chunks.append(current)
                current = ""
            for start in range(0, len(paragraph), size):
                chunks.append(paragraph[start:start + size])
            continue
        if current and len(current) + len(paragraph) + 1 > size:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n{paragraph}".strip() if current else paragraph
    if current:
        chunks.append(current)
    return chunks or [text[:size]]


def to_base_info(base: KnowledgeBase) -> KnowledgeBaseInfo:
    return KnowledgeBaseInfo(
        kbId=base.id,
        name=base.name,
        description=base.description or "",
        enabled=bool(base.enabled),
        updatedAt=now_text(base.updated_at),
    )


def to_item_info(item: KnowledgeItem) -> KnowledgeItemInfo:
    return KnowledgeItemInfo(
        itemId=item.id,
        kbId=item.kb_id,
        title=item.title,
        content=item.content,
        updatedAt=now_text(item.updated_at),
    )


def create_chunks(db: Session, item: KnowledgeItem) -> int:
    for chunk in list(item.chunks):
        db.delete(chunk)
    db.flush()

    chunks = split_chunks(item.content)
    for index, content in enumerate(chunks, start=1):
        db.add(
            KnowledgeChunk(
                item_id=item.id,
                kb_id=item.kb_id,
                user_id=item.user_id,
                content=content,
                chunk_index=index,
            )
        )
    return len(chunks)


def seed_initial_knowledge(db: Session, user_id: str = DEFAULT_USER_ID) -> None:
    exists = db.query(KnowledgeBase).filter(KnowledgeBase.user_id == user_id).first()
    if exists is not None:
        return

    for base_data in SEED_BASES:
        base = KnowledgeBase(
            user_id=user_id,
            name=base_data["name"],
            description=base_data["description"],
            enabled=True,
        )
        db.add(base)
        db.flush()
        for item_data in base_data["items"]:
            item = KnowledgeItem(
                kb_id=base.id,
                user_id=user_id,
                title=item_data["title"],
                content=item_data["content"],
            )
            db.add(item)
            db.flush()
            create_chunks(db, item)
    db.commit()


def get_base_or_raise(db: Session, kb_id: int, user_id: str = DEFAULT_USER_ID) -> KnowledgeBase:
    base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user_id).first()
    if base is None:
        raise ValueError("知识库不存在")
    return base


def get_item_or_raise(db: Session, kb_id: int, item_id: int, user_id: str = DEFAULT_USER_ID) -> KnowledgeItem:
    item = (
        db.query(KnowledgeItem)
        .filter(KnowledgeItem.id == item_id, KnowledgeItem.kb_id == kb_id, KnowledgeItem.user_id == user_id)
        .first()
    )
    if item is None:
        raise ValueError("知识条目不存在")
    return item


def list_knowledge_bases(db: Session, user_id: str = DEFAULT_USER_ID) -> List[KnowledgeBaseInfo]:
    bases = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.user_id == user_id)
        .order_by(KnowledgeBase.id)
        .all()
    )
    return [to_base_info(base) for base in bases]


def list_knowledge_items(db: Session, kb_id: int, user_id: str = DEFAULT_USER_ID) -> List[KnowledgeItemInfo]:
    get_base_or_raise(db, kb_id, user_id)
    items = (
        db.query(KnowledgeItem)
        .filter(KnowledgeItem.kb_id == kb_id, KnowledgeItem.user_id == user_id)
        .order_by(KnowledgeItem.id)
        .all()
    )
    return [to_item_info(item) for item in items]


def create_knowledge_base(db: Session, name: str, description: str, user_id: str = DEFAULT_USER_ID) -> KnowledgeBaseInfo:
    base = KnowledgeBase(user_id=user_id, name=safe_text(name, "未命名知识库")[:120], description=safe_text(description))
    db.add(base)
    db.commit()
    db.refresh(base)
    return to_base_info(base)


def update_knowledge_base(
    db: Session,
    kb_id: int,
    name: str,
    description: str,
    user_id: str = DEFAULT_USER_ID,
) -> KnowledgeBaseInfo:
    base = get_base_or_raise(db, kb_id, user_id)
    base.name = safe_text(name, base.name)[:120]
    base.description = safe_text(description)
    base.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(base)
    return to_base_info(base)


def delete_knowledge_base(db: Session, kb_id: int, user_id: str = DEFAULT_USER_ID) -> None:
    base = get_base_or_raise(db, kb_id, user_id)
    db.delete(base)
    db.commit()


def add_knowledge_item(
    db: Session,
    kb_id: int,
    title: str,
    content: str,
    user_id: str = DEFAULT_USER_ID,
) -> KnowledgeTextAddResult:
    base = get_base_or_raise(db, kb_id, user_id)
    item = KnowledgeItem(
        kb_id=base.id,
        user_id=user_id,
        title=safe_text(title, "未命名知识")[:160],
        content=safe_text(content),
    )
    db.add(item)
    db.flush()
    chunk_count = create_chunks(db, item)
    base.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return KnowledgeTextAddResult(itemId=item.id, chunkCount=chunk_count, updatedAt=now_text(item.updated_at))


def update_knowledge_item(
    db: Session,
    kb_id: int,
    item_id: int,
    title: str,
    content: str,
    user_id: str = DEFAULT_USER_ID,
) -> KnowledgeTextAddResult:
    item = get_item_or_raise(db, kb_id, item_id, user_id)
    item.title = safe_text(title, item.title)[:160]
    item.content = safe_text(content)
    item.updated_at = datetime.utcnow()
    chunk_count = create_chunks(db, item)
    item.base.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return KnowledgeTextAddResult(itemId=item.id, chunkCount=chunk_count, updatedAt=now_text(item.updated_at))


def delete_knowledge_item(db: Session, kb_id: int, item_id: int, user_id: str = DEFAULT_USER_ID) -> None:
    item = get_item_or_raise(db, kb_id, item_id, user_id)
    item.base.updated_at = datetime.utcnow()
    db.delete(item)
    db.commit()


def extract_keywords(question: str) -> List[str]:
    text = safe_text(question).lower()
    keywords = set(re.findall(r"[a-z0-9_]{2,}", text))
    for sequence in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        keywords.add(sequence)
        for start in range(0, max(len(sequence) - 1, 0)):
            keywords.add(sequence[start:start + 2])
    return [item for item in keywords if len(item) >= 2]


def score_chunk(question: str, keywords: Iterable[str], title: str, content: str) -> float:
    title_text = title.lower()
    content_text = content.lower()
    question_text = safe_text(question).lower()
    score = 0.0
    if question_text and question_text in content_text:
        score += 4.0
    if question_text and question_text in title_text:
        score += 5.0
    for keyword in keywords:
        if keyword in title_text:
            score += 2.5
        if keyword in content_text:
            score += 1.0
    return score


def search_knowledge_references(
    db: Session,
    question: str,
    kb_id: Optional[int] = None,
    user_id: str = DEFAULT_USER_ID,
    limit: int = 5,
) -> List[KnowledgeReference]:
    query = (
        db.query(KnowledgeChunk, KnowledgeItem)
        .join(KnowledgeItem, KnowledgeChunk.item_id == KnowledgeItem.id)
        .filter(KnowledgeChunk.user_id == user_id)
    )
    if kb_id:
        query = query.filter(KnowledgeChunk.kb_id == kb_id)

    rows = query.order_by(desc(KnowledgeChunk.created_at), desc(KnowledgeChunk.id)).limit(100).all()
    keywords = extract_keywords(question)
    scored = []
    for chunk, item in rows:
        raw_score = score_chunk(question, keywords, item.title, chunk.content)
        scored.append((raw_score, chunk, item))

    positive = [entry for entry in scored if entry[0] > 0]
    selected = sorted(positive or scored[:limit], key=lambda entry: (entry[0], entry[1].id), reverse=True)[:limit]
    references: List[KnowledgeReference] = []
    for index, (raw_score, chunk, item) in enumerate(selected):
        score = min(0.99, max(0.35, 0.55 + raw_score / 10 if raw_score > 0 else 0.35 - index * 0.03))
        references.append(
            KnowledgeReference(
                itemId=item.id,
                chunkId=chunk.chunk_index,
                title=item.title,
                content=chunk.content[:420],
                score=round(score, 2),
            )
        )
    return references


def parse_knowledge_answer(content: str) -> str:
    text = strip_code_fence(content)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text.strip()
    if isinstance(parsed, dict):
        return safe_text(parsed.get("answer"), text)[:1800]
    return text.strip()


def analyze_knowledge(
    db: Session,
    kb_id: int,
    field_id: str,
    question: str,
    user_id: str = DEFAULT_USER_ID,
) -> KnowledgeAnalyzeResult:
    get_base_or_raise(db, kb_id, user_id)
    references = search_knowledge_references(db, question, kb_id=kb_id, user_id=user_id, limit=5)
    if not deepseek_api_key():
        return KnowledgeAnalyzeResult(
            answer="AI 未连接：后端未配置 DeepSeek API Key。",
            references=references,
            updatedAt=now_text(),
        )

    context = {
        "fieldId": field_id,
        "question": question,
        "references": [reference.model_dump(mode="json") for reference in references],
    }
    try:
        content = call_deepseek_chat(
            [
                {
                    "role": "system",
                    "content": "你是智慧农业知识库分析助手。只能根据给定知识库引用和问题回答，不要声称已经执行设备操作。输出 JSON。",
                },
                {
                    "role": "user",
                    "content": (
                        "请结合知识库引用回答用户问题，输出格式为 {\"answer\":\"...\"}。"
                        f"\n上下文：{json.dumps(context, ensure_ascii=False)}"
                    ),
                },
            ],
            max_tokens=900,
            timeout_seconds=90,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        answer = parse_knowledge_answer(content)
    except Exception as error:
        print(f"knowledge analysis unavailable: {error}")
        answer = "AI 调用失败：DeepSeek API 暂时不可用，请检查 Key、网络或模型配置。"

    return KnowledgeAnalyzeResult(answer=answer, references=references, updatedAt=now_text())
