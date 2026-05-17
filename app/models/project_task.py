"""
app/models/project_task.py
A ProjectTask is a single row within a Project, with all 13 CMMI fields.
Supports multiple assignees via the project_task_assignees association table.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Date, ForeignKey, Table
from sqlalchemy.orm import relationship

from app.database import Base


# Association table — many ProjectTasks ↔ many Users
project_task_assignees = Table(
    "project_task_assignees",
    Base.metadata,
    Column("project_task_id", Integer, ForeignKey("project_tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class ProjectTask(Base):
    __tablename__ = "project_tasks"

    id                 = Column(Integer, primary_key=True, index=True)
    project_id         = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    # Core CMMI fields
    milestone_phase    = Column(String(120), nullable=True)   # "Phase 1", "Design", etc.
    category           = Column(String(120), nullable=True)   # "Development", "Testing", etc.
    task_description   = Column(Text, nullable=False)

    # Planning (set by PM)
    planned_start_date = Column(Date, nullable=True)
    planned_end_date   = Column(Date, nullable=True)
    planned_effort     = Column(Float, default=0.0)            # hours

    # Actuals (filled by assignees)
    actual_start_date  = Column(Date, nullable=True)
    actual_end_date    = Column(Date, nullable=True)
    actual_effort      = Column(Float, default=0.0)

    # CMMI tracking
    action_item        = Column(Text, nullable=True)
    remarks            = Column(Text, nullable=True)
    status             = Column(String(30), default="not_started")  # not_started | in_progress | completed | on_hold

    created_at         = Column(DateTime, default=datetime.utcnow)
    updated_at         = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project   = relationship("Project", back_populates="tasks")
    assignees = relationship("User", secondary=project_task_assignees, lazy="joined")

    # ----- Computed properties used by reports -----
    @property
    def days_delayed(self) -> int:
        """How many days past planned end (positive = late, 0 = on time)."""
        if not self.planned_end_date:
            return 0
        end = self.actual_end_date or datetime.utcnow().date()
        if self.status != "completed" and self.actual_end_date is None:
            end = datetime.utcnow().date()
        delta = (end - self.planned_end_date).days
        return max(delta, 0)

    @property
    def effort_variance_pct(self) -> float:
        """((actual - planned) / planned) * 100. Positive = over budget."""
        if not self.planned_effort or self.planned_effort == 0:
            return 0.0
        return round(((self.actual_effort - self.planned_effort) / self.planned_effort) * 100, 1)
