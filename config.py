import logging
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str = "sk-xxxx-your-key-here"
    OPENAI_TEXT_MODEL: str = "gpt-4"
    OPENAI_TEMPERATURE: float = 0.2
    
    # Tavily API for real search results (https://tavily.com)
    # Sign up for free tier at https://app.tavily.com/sign-up
    TAVILY_API_KEY: str = "your-tavily-api-key-here"
    
    # YouTube cookies for yt-dlp authentication (base64 encoded)
    # Export from browser, then: base64 < cookies.txt
    # This helps bypass YouTube bot detection on cloud servers
    YOUTUBE_COOKIES_BASE64: str = ""
    
    class Config:
        env_file = ".env"


settings = Settings()