from typing import Any

from pydantic import BaseModel, ConfigDict


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: Any = ""
    model: Any = None
    history: Any = None
    cards_supported: Any = None
    user: Any = None
    id_token: Any = None
    today_bs: Any = None
    session_id: Any = None