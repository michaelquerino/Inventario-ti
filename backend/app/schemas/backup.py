from pydantic import BaseModel


class BackupLogRead(BaseModel):
    id: int
    started_at: str
    finished_at: str | None = None
    status: str
    file_path: str | None = None
    size_bytes: int | None = None
    message: str | None = None
    triggered_by: str
    triggered_by_email: str | None = None

    model_config = {"from_attributes": True}
