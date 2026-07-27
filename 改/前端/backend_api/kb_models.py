from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


def utc_now() -> datetime:
    return datetime.utcnow()


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(64), nullable=False, default="local_demo", index=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=False, default="")
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    items = relationship("KnowledgeItem", back_populates="base", cascade="all, delete-orphan")
    chunks = relationship("KnowledgeChunk", back_populates="base", cascade="all, delete-orphan")


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, default="local_demo", index=True)
    title = Column(String(160), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    base = relationship("KnowledgeBase", back_populates="items")
    chunks = relationship("KnowledgeChunk", back_populates="item", cascade="all, delete-orphan")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("knowledge_items.id"), nullable=False, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, default="local_demo", index=True)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    item = relationship("KnowledgeItem", back_populates="chunks")
    base = relationship("KnowledgeBase", back_populates="chunks")
