from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    supabase_url: str = Field("https://placeholder-url.supabase.co", validation_alias="VITE_SUPABASE_URL")
    supabase_service_key: str = Field("placeholder-key", validation_alias="VITE_SUPABASE_SERVICE_KEY")
    supabase_anon_key: str = Field("placeholder-key", validation_alias="VITE_SUPABASE_ANON_KEY")
    gemini_api_key: str = Field("placeholder-gemini-key", validation_alias="VITE_GEMINI_API_KEY")
    semantic_scholar_api_key: str = Field("", validation_alias="VITE_SEMANTIC_SCHOLAR_API_KEY")
    
    redis_url: str = "redis://localhost:6379"
    frontend_url: str = "http://localhost:5173"
    gemini_embedding_model: str = Field("models/embedding-001", validation_alias="VITE_GEMINI_EMBEDDING_MODEL")
    gemini_chat_model: str = Field("models/gemini-flash-latest", validation_alias="VITE_GEMINI_CHAT_MODEL")
    chunk_size: int = 600
    overlap_size: int = 100
    jwt_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        case_sensitive=False,
        extra="ignore"
    )


settings = Settings()
