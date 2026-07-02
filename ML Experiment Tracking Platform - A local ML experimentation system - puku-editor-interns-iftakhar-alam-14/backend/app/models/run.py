from sqlalchemy import Column, Integer, String, DateTime, Text, Float, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.app.database import Base

class Run(Base):
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=False)
    run_name = Column(String(255), nullable=True)
    status = Column(String(50), default="RUNNING")
    metrics = Column(Text, nullable=True)
    parameters = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)
    artifact_uri = Column(String(500), nullable=True)
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)

    experiment = relationship("Experiment", back_populates="runs")
