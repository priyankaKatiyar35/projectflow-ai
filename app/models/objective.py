"""
app/models/objective.py
Objectives (the 'O' in OKR) - qualitative ambitions for a time period.

An Objective:
  - Has an owner (the person accountable)
  - Belongs to a time period (e.g. 2026 Q2)
  - Has one or more Key Results (measurable outcomes)
  - Progress auto-calculated as avg of KR progress
  - Status derived from progress: on-track / at-risk / off-track / done
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Date
from sqlalchemy.orm import relationship

from app.database import Base


class Objective(Base):
    __tablename__ = "objectives"

    id          = Column(Integer, primary_key=True, index=True)
    title       = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)

    # Category tag - free text but common values: Revenue, Product, People, Process, Quality, etc.
    category    = Column(String(50), nullable=True, index=True)

    # Time period
    period_label = Column(String(30), nullable=False, index=True)  # e.g. "2026-Q2", "2026 H1"
    period_start = Column(Date, nullable=True)
    period_end   = Column(Date, nullable=True)

    # Owner = the person accountable for this objective
    owner_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Manually-set status override (if null, computed from KR progress)
    status_override = Column(String(20), nullable=True)
    # values: on_track | at_risk | off_track | done | paused

    # Visibility - company (everyone sees) or private (only owner + admin)
    visibility  = Column(String(20), nullable=False, default="company")

    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id])
    key_results = relationship("KeyResult", back_populates="objective", cascade="all, delete-orphan", order_by="KeyResult.id")

    @property
    def progress_pct(self) -> float:
        """Average progress across all KRs (0-100)."""
        if not self.key_results:
            return 0.0
        total = sum(kr.progress_pct for kr in self.key_results)
        return round(total / len(self.key_results), 1)

    @property
    def computed_status(self) -> str:
        """Auto status based on progress vs time elapsed in period."""
        if self.status_override:
            return self.status_override

        progress = self.progress_pct
        if progress >= 100:
            return "done"
        if not self.period_start or not self.period_end:
            return "on_track"

        from datetime import date
        today = date.today()
        if today < self.period_start:
            return "on_track"
        if today > self.period_end:
            return "off_track" if progress < 90 else "done"

        # Calculate expected progress vs actual
        total_days = (self.period_end - self.period_start).days or 1
        elapsed = (today - self.period_start).days
        expected = (elapsed / total_days) * 100

        if progress >= expected * 0.9:
            return "on_track"
        if progress >= expected * 0.7:
            return "at_risk"
        return "off_track"