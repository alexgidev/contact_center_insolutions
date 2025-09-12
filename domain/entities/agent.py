from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from domain.enums import AgentStatus


@dataclass
class ETAgent:
    """Entity for Agent"""

    id: int
    tenant_id: int
    reference_code: int
    agent_type: int
    created_at: datetime
    status: str = AgentStatus.AVAILABLE.value
    last_call_time: Optional[datetime] = None
    current_call_id: Optional[int] = None
