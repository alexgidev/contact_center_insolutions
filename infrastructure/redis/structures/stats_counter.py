from typing import Dict, Optional
from infrastructure.redis.connection import get_redis_client
import logging

logger = logging.getLogger(__name__)


class StatsCounter:
    """Manages statistics counters in Redis.

    Uses STRING keys with atomic increment operations.
    Perfect for high-frequency counting without race conditions.
    """

    PREFIX = "stats:"


    def __init__(self):
        """Initialize with Redis client"""
        self.redis = get_redis_client()
        if not self.redis:
            raise ConnectionError("Redis client not available")


    def increment(
        self,
        stat_name: str,
        amount: int = 1
    ) -> Optional[int]:
        """Increment a counter atomically

        Args:
            stat_name: Name of the statistic
            amount: Amount to increment (default 1)

        Returns:
            New value after increment
        """
        try:
            key = f"{self.PREFIX}{stat_name}"
            new_value = self.redis.incrby(key, amount)
            return new_value

        except Exception as e:
            logger.error(f"Error incrementing {stat_name}: {e}")
            return None


    def get(
        self,
        stat_name: str
    ) -> int:
        """Get current value of a counter

        Args:
            stat_name: Name of the statistic

        Returns:
            Current value (0 if not exists)
        """
        try:
            key = f"{self.PREFIX}{stat_name}"
            value = self.redis.get(key)
            return int(value) if value else 0

        except Exception as e:
            logger.error(f"Error getting {stat_name}: {e}")
            return 0


    def set(
        self,
        stat_name: str,
        value: int
    ) -> bool:
        """Set a counter to specific value

        Args:
            stat_name: Name of the statistic
            value: Value to set

        Returns:
            True if set successfully
        """
        try:
            key = f"{self.PREFIX}{stat_name}"
            self.redis.set(key, value)
            return True

        except Exception as e:
            logger.error(f"Error setting {stat_name}: {e}")
            return False


    def reset(
        self,
        stat_name: str
    ) -> bool:
        """Reset a counter to zero
        
        Args:
            stat_name: Name of the statistic
            
        Returns:
            True if reset successfully
        """
        return self.set(stat_name, 0)


    def get_all(self) -> Dict[str, int]:
        """Get all statistics
        
        Returns:
            Dictionary with all counters
        """
        # Predefined stats for contact center
        stat_names = [
            'total_calls',
            'successful_calls',
            'failed_calls',
            'abandoned_calls',
            'assignments_ok',
            'assignments_failed',
            'calls_today',
            'calls_this_hour'
        ]

        return {
            name: self.get(name)
            for name in stat_names
        }


    def reset_all(self):
        """Reset all counters to zero"""
        try:
            # Get all stat keys
            pattern = f"{self.PREFIX}*"
            keys = self.redis.keys(pattern)

            # Delete all stat keys
            if keys:
                self.redis.delete(*keys)
                logger.info(f"Reset {len(keys)} counters")

        except Exception as e:
            logger.error(f"Error resetting counters: {e}")
