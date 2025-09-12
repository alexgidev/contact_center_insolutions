import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError
from infrastructure.database.base import Base
from infrastructure.config import settings
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MySQLConnection:
    """Manages MySQL database connection
    with retry logic and connection pooling"""

    def __init__(
        self,
        retry_count: int = 3,
        retry_delay: int = 5
    ):
        self.engine = None
        self.SessionLocal = None
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self._initialize_connection()


    def _initialize_connection(self) -> None:
        """Initialize connection with retry logic"""
        db_connected = False
        for attempt in range(1, self.retry_count + 1):
            try:
                if (
                    self._create_engine() and
                    self.test_connection()
                ):
                    db_connected = True
                    logger.info("MySQL connection initialized successfully")
                    break
            except Exception as e:
                logger.error(
                    "Error initializing connection "
                    f"(attempt {attempt}/{self.retry_count}): {e}"
                )

            if attempt < self.retry_count:
                logger.warning(f"Retrying in {self.retry_delay} seconds...")
                time.sleep(self.retry_delay)

        if not db_connected:
            logger.error("Failed to initialize MySQL connection after all retries")
            raise ConnectionError("Could not connect to MySQL database")


    def _create_engine(self) -> bool:
        """Create SQLAlchemy engine with connection pooling

        Returns:
            bool: Engine created OK/KO
        """
        try:
            url = settings.get_mysql_url()
            self.engine = create_engine(
                url,
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                pool_timeout=settings.db_pool_timeout,
                pool_recycle=settings.db_pool_recycle,
                pool_pre_ping=True,
                echo=settings.sql_echo,
                connect_args={'connect_timeout': 10}
            )

            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )

            return True

        except Exception as e :
            logger.error(f"Failed to create engine: {e}")
            return False


    def test_connection(self) -> bool:
        """Test database connection with a simple query

        Returns:
            bool: Test OK/KO
        """
        if not self.engine:
            return False

        try:
            with self.engine.connect() as connection:
                return connection.scalar(text("SELECT 1 as test")) == 1

        except OperationalError as e:
            logger.error(f"Connection test failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in connection test: {e}")

        return False


    def get_session(self) -> Session:
        """Get a new database session

        Returns:
            Session: A new SQLAlchemy Session instance
        """
        if not self.SessionLocal:
            raise ConnectionError("Database not initialized")
        return self.SessionLocal()


    def create_tables(self):
        """Create all tables defined in models"""
        if not self.engine:
            raise ConnectionError("Database engine not initialized")

        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created/verified successfully")
        except Exception as e:
            logger.err(f"Error creating tables: {e}")
            raise


    def close_all_connections(self):
        """Close all connections in the pool."""
        if self.engine:
            self.engine.dispose()
            logger.info("All database connections closed")


# Global database connection instance
db_connection = MySQLConnection()


def init_database() -> bool:
    """Initialize database on application startup."""
    try:
        db_connection.create_tables()

        if db_connection.test_connection():
            logger.info("Database ready to use")
            return True
        else:
            logger.error("Database connection failed")
            return False

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False


def get_db_session() -> Session:
    """Get a database session for repository operations."""
    return db_connection.get_session()
