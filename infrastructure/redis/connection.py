import redis
from typing import Optional
from infrastructure.config import settings
import logging


logger = logging.getLogger(__name__)


class RedisConnection:
    """Manages Redis connection and provides basic operations"""

    def __init__(self) -> None:
        """Initialize Redis connection"""
        self.client: Optional[redis.Redis] = None
        self._connect()


    def _connect(self) -> None:
        """Establish connection to Redis server"""
        try:
            self.client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )

            self.client.ping()
            logger.info(
                "Connected to Redis at %s:%s",
                settings.redis_host,
                settings.redis_port
            )

        except redis.ConnectionError as e:
            logger.error(f"Redis connection failed: {e}")
            self.client = None

        except Exception as e:
            logger.error(f"Unexpected Redis error: {e}")
            self.client = None


    def test_connection(self) -> bool:
        """Test if Redis is accessible."""
        if not self.client:
            return False
        try:
            return bool(self.client.ping())
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False


    def get_client(self) -> redis.Redis:
        """Get the Redis client instance"""
        if not self.client:
            self._connect()
        if not self.client:
            raise ConnectionError("Redis client is not available")
        return self.client


redis_connection: RedisConnection = RedisConnection()


def init_redis() -> bool:
    """Initialize Redis on application startup"""
    if redis_connection.test_connection():
        logger.info("Redis ready to use")
        return True
    else:
        logger.error("Redis initialization failed")
        return False


def get_redis_client() -> redis.Redis:
    """Get Redis client for operations
    Used by the structure classes"""
    return redis_connection.get_client()
