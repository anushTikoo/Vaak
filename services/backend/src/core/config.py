from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # CORS
    CORS_ORIGINS: str = "http://localhost:8081,http://localhost:19006,exp://localhost:8081,*"

    # Sarvam AI
    SARVAM_API_KEY: str = Field(default="", description="API Key for Sarvam services")
    SARVAM_STT_ENDPOINT: str = "wss://api.sarvam.ai/speech-to-text-realtime/ws"
    SARVAM_TTS_ENDPOINT: str = "wss://api.sarvam.ai/text-to-speech/ws"
    SARVAM_LLM_MODEL: str = "sarvam-105b-conversations"

    # Zepto MCP
    ZEPTO_MCP_ENDPOINT: str = "https://mcp.zepto.co.in/mcp"
    ZEPTO_CLIENT_ID: str = ""
    ZEPTO_CLIENT_SECRET: str = ""

    # Database
    DATABASE_URL: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
