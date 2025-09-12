from enum import Enum, unique


@unique
class AgentStatus(Enum):
    """Agent status"""

    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    PAUSE = "PAUSE"
    OFFLINE = "OFFLINE"


@unique
class CallStatus(Enum):
    """Call status"""

    QUEUED = "QUEUED"
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"


@unique
class CallResult(Enum):
    """Call result"""

    OK = "OK"
    KO = "KO"
