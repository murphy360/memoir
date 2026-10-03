"""The archive: one family's memoir. Every other row belongs to exactly one archive."""

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audited import Audited
from app.core.db import Base, Timestamped


class Archive(Audited, Timestamped, Base):
    __tablename__ = "archives"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    time_zone: Mapped[str] = mapped_column(String(64), default="UTC")
