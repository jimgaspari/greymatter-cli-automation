from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    api_token: str = Field(default="", validation_alias="API_TOKEN")

    # Never allow None here:
    workdir: str = Field(default="/work", validation_alias="CLI_API_WORKDIR")

    job_wait_timeout_s: int = Field(default=900, validation_alias="CLI_API_JOB_WAIT_TIMEOUT_S")

settings = Settings()

