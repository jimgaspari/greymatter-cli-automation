from pydantic import BaseModel
import os

class Settings(BaseModel):
    api_token: str = os.environ.get("API_TOKEN", "")
    workdir: str = os.environ.get("WORKDIR", "/work")

settings = Settings()
