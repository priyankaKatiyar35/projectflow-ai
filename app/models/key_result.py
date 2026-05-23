"""
app/models/key_result.py
Key Results - the measurable outcomes for an Objective.

Each KR has a target value and a current value. Progress is calculated as:
  - numeric: (current - start) / (target - start) * 100
  - percent: current / target * 100  (where target is usually 100)
  - boolean: 100 if current >= target, else 0
  - milestone: percent of completed milestones (current = count done, target = total)
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship

from app.database import Base


class KeyResult(Base):
    __tablename__ = "key_results"

    id           = Column(Integer, primary_key=True, index=True)
    objective_id = Column(Integer, ForeignKey("objectives.id", ondelete="CASCADE"), nullable=False, index=True)
    title        = Column(String(300), nullable=False)

    # Type of measurement
    # numeric  -> "Increase revenue from 100 to 500" (start=100, target=500, current=N)
    # percent  -> "Achieve 95% test coverage" (target=95, current=N)
    # boolean  -> "Launch v2 of product" (target=1, current=0 or 1)
    # milestone-> "Complete 5 of 5 milestones" (target=5, current=N)
    kr_type      = Column(String(20), nullable=False, default="numeric")

    unit         = Column(String(20), nullable=True)  # e.g. "$", "%", "customers", "stories"
    start_value  = Column(Float, default=0.0)
    target_value = Column(Float, nullable=False)
    current_value= Column(Float, default=0.0)

    # Owner can be different from objective owner (delegated KR)
    owner_id     = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    sort_order   = Column(Integer, default=0)

    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    objective = relationship("Objective", back_populates="key_results")
    owner     = relationship("User", foreign_keys=[owner_id])
    checkins  = relationship("KRCheckin", back_populates="key_result", cascade="all, delete-orphan", order_by="KRCheckin.created_at.desc()")

    @property
    def progress_pct(self) -> float:
        """Calculate progress 0-100 based on type."""
        if self.kr_type == "boolean":
            return 100.0 if self.current_value >= self.target_value else 0.0
        elif self.kr_type == "percent":
            if self.target_value == 0:
                return 0.0
            pct = (self.current_value / self.target_value) * 100
            return round(max(0.0, min(100.0, pct)), 1)
        else:
            # numeric or milestone
            if self.target_value == self.start_value:
                return 100.0 if self.current_value >= self.target_value else 0.0
            pct = ((self.current_value - self.start_value) / (self.target_value - self.start_value)) * 100
            return round(max(0.0, min(100.0, pct)), 1)


class KRCheckin(Base):
    """A weekly/periodic check-in note on a key result."""
    __tablename__ = "kr_checkins"

    id            = Column(Integer, primary_key=True, index=True)
    key_result_id = Column(Integer, ForeignKey("key_results.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id     = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Snapshot at time of check-in
    value_at_checkin = Column(Float, nullable=False)
    confidence       = Column(String(20), nullable=True)  # high / medium / low
    note             = Column(Text, nullable=True)

    created_at    = Column(DateTime, default=datetime.utcnow, index=True)

    key_result = relationship("KeyResult", back_populates="checkins")
    author     = relationship("User", foreign_keys=[author_id])