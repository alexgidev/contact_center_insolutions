from typing import Optional, List
from datetime import datetime
from infrastructure.redis.connection import get_redis_client
import logging


logger = logging.getLogger(__name__)


class AgentQueue:
    """Manages available agents queue in Redis.

    Uses SORTED SET where:
        - Member = agent_id
        - Score = last_call_timestamp (lower = longer idle = higher priority)
    """

    KEY = "agents:available"


    def __init__(self):
        """Initialize with Redis client"""
        self.redis = get_redis_client()
        if not self.redis:
            raise ConnectionError("Redis client not available")


    def add(
        self,
        agent_id: int,
        last_call_time: Optional[datetime] = None
    ) -> bool:
        """Add agent to available queue

        Args:
            agent_id: Agent's ID
            last_call_time: When the agent last handled a call

        Returns:
            bool: True if added successfully
        """
        try:
            # Calculate priority score (older, lower score)
            if last_call_time:
                score = last_call_time.timestamp()
            else:
                # Add new agent with the highest score 
                top = self.redis.zrevrange(self.KEY, 0, 0, withscores=True)
                max_score = (
                    top[0][1] if top 
                    else datetime.now().timestamp()
                )
                score = max_score + 1

            result = self.redis.zadd(
                self.KEY,
                {str(agent_id): score}
            )

            return result is not None

        except Exception as e:
            logger.error(f"Error adding agent {agent_id}: {e}")
            return False


    def get_next(self) -> Optional[int]:
        """Get and remove from queue agent with longest idle time
        
        Returns:
            Agent ID or None if no agents available
        """
        try:
            # Pop member with minimum score (longest idle)
            if result := self.redis.zpopmin(self.KEY, count=1):
                agent_id_str, _ = result[0]
                return int(agent_id_str)

            logger.warning("No available agents")
            return None

        except Exception as e:
            logger.error(f"Error getting next agent: {e}")
            return None


    def remove(self, agent_id: int) -> bool:
        """Remove specific agent from queue
        
        Args:
            agent_id: Agent to remove

        Returns:
            True if removed successfully
        """
        try:
            result = self.redis.zrem(self.KEY, str(agent_id))
            return result > 0
        except Exception as e:
            logger.error(f"Error removing agent {agent_id}: {e}")
            return False


    def count(self) -> int:
        """Get count of available agents"""
        try:
            return self.redis.zcard(self.KEY)
        except Exception as e:
            logger.error(f"Failed to get agent count: {e}")
            return 0


    def get_all(self) -> List[int]:
        """Get all available agents sorted by idle time

        Returns:
            List of agent IDs (longest idle first)
        """
        try:
            agents = self.redis.zrange(self.KEY, 0, -1)
            return [int(agent_id) for agent_id in agents]
        except Exception as e:
            logger.error(f"Error getting all agents{e}")
            return []


    def clear(self):
        """Remove all agents from queue"""
        try:
            self.redis.delete(self.KEY)
        except Exception as e:
            logger.error(f"Error clearing agent queue: {e}")
