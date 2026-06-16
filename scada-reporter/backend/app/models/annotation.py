from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Annotation(Base):
    """Trend grafiğine düşülen paylaşımlı not.

    `tag_id` None ise grafik-seviyesi (tüm seriler için) not. `ts` notun
    işaret ettiği zaman ekseni noktasıdır; `created_at` notun yazıldığı andır.
    """

    __tablename__ = "annotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tag_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(100), default="")
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
