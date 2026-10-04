"""The archive (one family's memoir) and its users.

The accounts ticket adds passwords, roles and sessions to `users`. The bootstrap only
needs the tables to exist, so that every later table can refer to them.
"""

from sqlalchemy import BigInteger, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamped


class Archive(Timestamped, Base):
    __tablename__ = "archives"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    time_zone: Mapped[str] = mapped_column(String(64), default="UTC")


class User(Timestamped, Base):
    __tablename__ = "users"
    __table_args__ = (Index("uq_users_email_lower", func.lower("email"), unique=True),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    archive_id: Mapped[int] = mapped_column(
        ForeignKey("archives.id", ondelete="RESTRICT"), index=True
    )
    email: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))
