from typing import Optional, Dict
from datetime import datetime
from infrastructure.redis.connection import get_redis_client
import logging


logger = logging.getLogger(__name__)


class AgentState:
    """Manages agent state in Redis.
    
    Uses HASH structure for storing multiple fields:
        - Efficient for getting/setting individual fields
        - Perfect for real-time state tracking
    """

    PREFIX = "agent:state:"
    DEFAULT_DATA_DURATION = 3600


    def __init__(self):
        """Initialize with Redis client"""
        self.redis = get_redis_client()
        if not self.redis:
            raise ConnectionError("Redis client not available")


    def set(
        self,
        agent_id: int,
        status: str,
        call_id: Optional[int] = None
    ) -> bool:
        """Store agent's current state.

        Args:
            agent_id: Agent's ID
            status: Current status (AVAILABLE, BUSY, PAUSE)
            call_id: Current call ID if BUSY

        Returns:
            True if stored successfully
        """
        try:
            key = f"{self.PREFIX}{agent_id}"
            data = {
                'status': status,
                'call_id': str(call_id) if call_id else '',
                'last_update': datetime.now().isoformat()
            }
            pipe = self.redis.pipeline()
            pipe.hset(key, mapping=data)
            pipe.expire(key, self.DEFAULT_DATA_DURATION)
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Error setting state for agent {agent_id}: {e}")
            return False


    def get(
        self,
        agent_id: int
    ) -> Optional[Dict]:
        """Get agent's current state.

        Args:
            agent_id: Agent's ID

        Returns:
            Dictionary with state data or None
        """
        try:
            key = f"{self.PREFIX}{agent_id}"
            agent_data = self.redis.hgetall(key)

            if not agent_data:
                return None

            call_id = (
                int(agent_data['call_id'])
                if agent_data.get('call_id', '').isdigit()
                else None
            )
            state = {
                'status': agent_data.get('status'),
                'call_id': call_id,
                'last_update': agent_data.get('last_update')
            }

            return state
        except Exception:
            logger.error(f"Error getting state for agent {agent_id}")
            return None


    def get_field(
        self,
        agent_id: int,
        field: str
    ) -> Optional[str]:
        """Get specific field from agent's state.
        
        Args:
            agent_id: Agent's ID
            field: Field name (status, call_id, last_update)
            
        Returns:
            Field value or None
        """
        try:
            key = f"{self.PREFIX}{agent_id}"
            return self.redis.hget(key, field)
        except Exception as e:
            logger.error(f"Error getting {field} for agent {agent_id}: {e}")
            return None


    def update_field(
        self,
        agent_id: int,
        field: str,
        value: str
    ) -> bool:
        """Update specific field in agent's state.
        
        Args:
            agent_id: Agent's ID
            field: Field to update
            value: New value
            
        Returns:
            True if updated successfully
        """
        try:
            key = f"{self.PREFIX}{agent_id}"
            pipe = self.redis.pipeline()
            pipe.hset(key, field, value)
            pipe.hset(key, 'last_update', datetime.now().isoformat())
            pipe.expire(key, self.DEFAULT_DATA_DURATION)
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Error updating {field} for agent {agent_id}: {e}")
            return False


    def delete(
        self,
        agent_id: int
    ) -> bool:
        """Remove agent's state.
        
        Args:
            agent_id: Agent's ID
            
        Returns:
            True if deleted successfully
        """
        try:
            key = f"{self.PREFIX}{agent_id}"
            return self.redis.delete(key) > 0
        except Exception as e:
            logger.error(f"Error deleting state for agent {agent_id}: {e}")
            return False


    def exists(
        self,
        agent_id: int
    ) -> bool:
        """Check if agent has state stored.
        
        Args:
            agent_id: Agent's ID
            
        Returns:
            True if state exists
        """
        try:
            key = f"{self.PREFIX}{agent_id}"
            return self.redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Error checking existence for agent {agent_id}: {e}")
            return False
