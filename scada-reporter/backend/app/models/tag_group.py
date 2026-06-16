from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TagGroup(Base):
    """Manuel tesis hiyerarşisi düğümü (Site → Ünite → Ekipman → ...).

    Kendine referanslı ağaç. Tag'ler `Tag.group_id` ile yaprak düğümlere
    bağlanır. Otomatik (PLC/device'tan türetilen) ağaç ile birlikte sunulur.
    """

    __tablename__ = "tag_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tag_groups.id", ondelete="CASCADE"), nullable=True, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
