"""Every file Memoir keeps is a blob: audio, photos, documents, thumbnails."""

from sqlalchemy import BigInteger, CHAR, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamped


class Blob(Timestamped, Base):
    __tablename__ = "blobs"

    sha256: Mapped[str] = mapped_column(CHAR(64), primary_key=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    content_type: Mapped[str] = mapped_column(String(120))
