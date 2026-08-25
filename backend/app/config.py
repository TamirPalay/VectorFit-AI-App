from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM
    llm_provider: str = "groq"  # "groq" | "gemini" | "ollama"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"  # live chat model (separate from labeling)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:70b"

    # Database
    database_url: str = "sqlite:///./vectorfit.db"

    # App
    frontend_origin: str = "http://localhost:5173"
    secret_key: str = "change_me"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
