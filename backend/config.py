from pydantic import BaseModel


class Settings(BaseModel):
	app_name: str = "Cycle Time Analysis API"
	api_prefix: str = "/api"
	cors_allow_origins: list[str] = [
		"http://localhost:5173",
		"http://127.0.0.1:5173",
	]
	data_dir: str = "./data"
	videos_dirname: str = "videos"


settings = Settings()
