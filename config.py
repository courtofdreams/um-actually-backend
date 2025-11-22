
import logging
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    OPENAI_API_KEY: str = "sk-xxxx-your-key-here"
    OPENAI_TEXT_MODEL: str = "gpt-4"
    OPENAI_TEMPERATURE: float = 0.2
    
    class Config:
        env_file = ".env"


settings = Settings()