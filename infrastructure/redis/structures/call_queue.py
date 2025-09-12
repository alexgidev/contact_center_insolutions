from typing import Optional
from infrastructure.redis.connection import get_redis_client
import logging


logger = logging.getLogger(__name__)


class CallQueue:
    """Manages pending calls queue in Redis
    
    Uses LIST structure for FIFO (First In, First Out):
        - LPUSH to add (left/front)
        - RPOP to get (right/back)
    """

    KEY = "calls:pending"


    def __init__(self):
        """Initialize with Redis client"""
        self.redis = get_redis_client()
        if not self.redis:
            raise ConnectionError("Redis client not available")


    def add(
        self,
        call_id: int
    ) -> bool:
        """Add call to pending queue
        
        Args:
            call_id: Call's ID
            
        Returns:
            True if added successfully
        """
        try:
            # Push to left (front) of list
            result = self.redis.lpush(self.KEY, str(call_id))

            return result is not None

        except Exception as e:
            logger.error(f"Error queueing call {call_id}: {e}")
            return False


    def get_next(self) -> Optional[int]:
        """Get next call from queue (oldest first)
        
        Returns:
            Call ID or None if queue is empty
        """
        try:
            # Pop from right (back) - FIFO
            call_id = self.redis.rpop(self.KEY)
            return int(call_id) if call_id else None

        except Exception as e:
            logger.error(f"Error getting next call: {e}")
            return None


    def count(self) -> int:
        """Get count of pending calls"""
        try:
            return self.redis.llen(self.KEY)
        except Exception as e:
            logger.error(f"Error getting pending call count: {e}")
            return 0


    def peek_next(self) -> Optional[int]:
        """View next call without removing it
        
        Returns:
            Call ID or None if queue is empty
        """
        try:
            # Get last element without removing
            call_id = self.redis.lindex(self.KEY, -1)
            return int(call_id) if call_id else None
        except Exception as e:
            logger.error(f"Error peeking next call: {e}")
            return None


    def clear(self):
        """Remove all calls from queue"""
        if self.redis:
            self.redis.delete(self.KEY)
