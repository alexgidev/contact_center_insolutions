from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from domain.enums import CallStatus


@dataclass
class ETCall:
    """Entity for Call"""

    id: int
    tenant_id: int
    call_type: int
    created_at: datetime
    status: str = CallStatus.QUEUED.value
    agent_id: Optional[int] = None
    assignment_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    result: Optional[str] = None
    wait_time_seconds: Optional[float] = None
    duration_seconds: Optional[float] = None
