from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Date, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class BranchRow(Base):
    __tablename__ = "branches"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))


class StaffReservationRow(Base):
    """지점별 당일(또는 저장된 날짜) 직원 입력 예약 한 건."""

    __tablename__ = "staff_reservations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # FK 없음: replace_branches() 가 branches 전체 삭제 후 재삽입하므로 CASCADE 시 예약 데이터가 함께 삭제됨
    branch_id: Mapped[str] = mapped_column(String(64), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    time: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    room: Mapped[str] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class TelReservationRow(Base):
    """전화 예약 한 건 (전 지점 공통 시퀀스 id)."""

    __tablename__ = "tel_reservations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    branch_id: Mapped[str] = mapped_column(String(64), index=True)
    date: Mapped[str] = mapped_column(String(10))
    time: Mapped[str] = mapped_column(String(32))
    slot: Mapped[str] = mapped_column(String(32))
    phone: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    count: Mapped[int] = mapped_column(Integer, default=2)
    room: Mapped[str] = mapped_column(String(255))
    adult: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    child: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    infant: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class DisplaySettingsRow(Base):
    """지점별 하단 광고 기본 슬라이드 간격(초)."""

    __tablename__ = "display_settings"
    branch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    default_interval_sec: Mapped[int] = mapped_column(Integer, default=8)


class DisplayItemRow(Base):
    """현황판 하단 광고 슬라이드 한 장."""

    __tablename__ = "display_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    branch_id: Mapped[str] = mapped_column(String(64), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    type: Mapped[str] = mapped_column(String(16), default="image")
    url: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(String(255), default="")
    duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


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


class RoomsConfigSetRow(Base):
    """룸 설정 파일(논리 키)별 메타: rooms_config.json, rooms_config.mchowon.json 등."""

    __tablename__ = "rooms_config_sets"
    file_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class RoomOptionRow(Base):
    """한 파일 안의 룸·테이블 한 칸."""

    __tablename__ = "room_options"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_name: Mapped[str] = mapped_column(String(128), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    room_id: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(255))
    display_label: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(32), default="table")
    section: Mapped[str] = mapped_column(String(128), default="기타")


class RoomsConfigLegacyBlobRow(Base):
    """구버전: 파일명당 JSON 한 덩어리. 이관 후 행 삭제."""

    __tablename__ = "rooms_config"
    file_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)


# --- 구버전 JSON 단일 컬럼 테이블 (스키마 전환 전 DB에만 존재). 이관 후 행 삭제됨. ---
class StaffTodayLegacyRow(Base):
    __tablename__ = "staff_today"
    branch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)


class DisplayContentLegacyRow(Base):
    __tablename__ = "display_content"
    branch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)


class TelStoreLegacyRow(Base):
    __tablename__ = "tel_store"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)
