from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, func
from sqlalchemy.orm import relationship
from infrastructure.database.base import Base
from domain.enums import CallStatus


class CallModel(Base):
    """ Calls table model """

    __tablename__ = 'calls'

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Tenant 1 default for the technical test
    tenant_id = Column(Integer, nullable=False, default=1)
    call_type = Column(Integer, nullable=False)
    agent_id = Column(Integer, ForeignKey('agents.id'), nullable=True)
    status = Column(String(20), nullable=False, default=CallStatus.QUEUED.value)
    created_at = Column(DateTime, nullable=False, default=func.now())
    assignment_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    result = Column(String(10), nullable=True)
    wait_time_seconds = Column(Float, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    agent = relationship("AgentModel", backref="calls")

    def __repr__(self):
        return (
            f"<Call(id={self.id}, "
            f"type={self.call_type}, "
            f"status={self.status})>"
        )
