"""
YeongjoPT Configuration Settings
"""
import os
from typing import Optional
from pydantic import BaseSettings


class Settings(BaseSettings):
    # Server Configuration
    HOST: str = "0.0.0.0"
    CONTROLLER_PORT: int = 21001
    MODEL_WORKER_PORT: int = 21002
    API_PORT: int = 8000
    GRADIO_PORT: int = 7860
    
    # Model Configuration
    DEFAULT_MODEL_PATH: str = "mistralai/Mistral-7B-Instruct-v0.1"
    MODEL_NAME: str = "yeongjopt-mistral-7b"
    
    # Security (Optional)
    API_KEY: Optional[str] = None
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "./logs"
    
    # Worker Configuration
    WORKER_CONCURRENCY: int = 5
    WORKER_TIMEOUT: int = 100
    
    # URLs
    @property
    def controller_url(self) -> str:
        return f"http://{self.HOST}:{self.CONTROLLER_PORT}"
    
    @property
    def worker_url(self) -> str:
        return f"http://{self.HOST}:{self.MODEL_WORKER_PORT}"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings() 