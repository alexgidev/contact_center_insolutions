from sqlalchemy import Column, Integer, String, DateTime, func
from infrastructure.database.base import Base
from domain.enums import AgentStatus


class AgentModel(Base):
    """ Agents table model """

    __tablename__ = 'agents'

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Tenant 1 default for the technical test
    tenant_id = Column(Integer, nullable=False, default=1)
    reference_code = Column(Integer, nullable=False, unique=True)
    agent_type = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default=AgentStatus.AVAILABLE.value)
    last_call_time = Column(DateTime, nullable=True)
    current_call_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())


    def __repr__(self) -> str:
        return (
            f"<Agent(id={self.id}, "
            f"ref={self.reference_code}, "
            f"status={self.status})>"
        )
