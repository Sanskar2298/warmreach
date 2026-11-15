import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String,
    Text,
    DateTime,
    Enum as SAEnum,
    func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ContactType(str, enum.Enum):
    HR = "hr"
    PROFESSOR = "professor"


class ContactStatus(str, enum.Enum):
    NEW = "new"
    DRAFTED = "drafted"
    APPROVED = "approved"
    SENT = "sent"
    REPLIED = "replied"
    BOUNCED = "bounced"
    DO_NOT_CONTACT = "do_not_contact"


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    organization: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    type: Mapped[ContactType] = mapped_column(
        SAEnum(ContactType, native_enum=False, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False
    )
    research_area_or_team: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    status: Mapped[ContactStatus] = mapped_column(
        SAEnum(ContactStatus, native_enum=False, values_callable=lambda obj: [e.value for e in obj]),
        default=ContactStatus.NEW,
        nullable=False,
        index=True
    )
    draft_subject: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    draft_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    followup_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<Contact(id={self.id}, name='{self.name}', email='{self.email}', status='{self.status.value}')>"
