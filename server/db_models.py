from __future__ import annotations

from typing import Optional

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class BranchRow(Base):
    __tablename__ = "branches"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))


class StaffTodayRow(Base):
    __tablename__ = "staff_today"
    branch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)


class DisplayContentRow(Base):
    __tablename__ = "display_content"
    branch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)


class TelStoreRow(Base):
    """전화 예약 전체 JSON {\"reservations\": [...]}"""

    __tablename__ = "tel_store"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)


class AccountRow(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AppKvRow(Base):
    __tablename__ = "app_kv"
    k: Mapped[str] = mapped_column(String(128), primary_key=True)
    v: Mapped[str] = mapped_column(Text)


class RoomsConfigRow(Base):
    """rooms_config.json 등 파일명별 전체 JSON"""

    __tablename__ = "rooms_config"
    file_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)
