class KeysUpdateBody(BaseModel):
    keys: dict[str, str]


class KeyTestBody(BaseModel):
    key_id: str
    key_value: str | None = None


class YouTubeSearchBody(BaseModel):
    query: str
    per: int = 6
    orientation: str = "landscape"


class YouTubeDownloadBody(BaseModel):
    url: str
    project_id: str | None = None
    scene_id: str | None = None
    rights_confirmed: bool = False
    rights_confirmed: bool = False
