from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NADI_", env_file=".env", extra="ignore")

    app_name: str = "The Escalate"
    api_prefix: str = "/v1"
    default_timezone: str = "Asia/Kuala_Lumpur"
    default_region: str = "ap-southeast-1"
    default_retention_days: int = 396
    ave_enabled: bool = False  # cannot be overridden meaningfully in product policy
    brief_model_version: str = "nadi-brief-2026-08"
    gemini_api_key: str = ""
    openai_api_key: str = ""
    llm_provider: str = "auto"  # 'vertex', 'gemini', 'openai', 'mock', or 'auto'
    llm_model: str = "gemini-3.5-flash"
    llm_temperature: float = 0.2
    # Vertex AI (Google Cloud). Set gcp_project_id to route Gemini calls
    # through Vertex AI instead of the direct Gemini Developer API. This is
    # what makes the LLM call actually a Google Cloud product rather than
    # the consumer generativelanguage.googleapis.com endpoint.
    gcp_project_id: str = ""
    gcp_location: str = "asia-southeast1"
    database_url: str = "sqlite:///./nadi.db"
    use_db_store: bool = False
    max_mention_window_days: int = 31

    contribution_weights: dict[str, float] = {
        "outputs": 0.15,
        "outtakes": 0.25,
        "outcomes": 0.35,
        "impact": 0.25,
    }


settings = Settings()

