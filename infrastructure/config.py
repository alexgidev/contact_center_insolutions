from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """ App settings loaded from environment variables.
        Pydantic validates types and raises 
        clear errors if something is missing.
    """

    # MySQL Configuration
    mysql_host: str
    mysql_port: int
    mysql_database: str
    mysql_user: str
    mysql_password: str

    # Redis Configuration
    redis_host: str
    redis_port: int
    redis_db: int
    
    # API Configuration
    api_host: str
    api_port: int
    
    # System Configuration
    max_concurrent_calls: int
    response_time_target_ms: int
    
    # Pool Configuration
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 3600
    
    # Debug
    debug_mode: bool = False
    sql_echo: bool = False
    
    class Config:
        """Pydantic configuration"""
        env_file = ".env"
        case_sensitive = False


    def get_mysql_url(self) -> str:
        """Build MySQL connection URL"""
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}@"
            f"{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
        )


    def get_redis_url(self) -> str:
        """Build Redis connection URL"""
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


settings = Settings()
