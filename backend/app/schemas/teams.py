from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

TeamName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class TeamIn(BaseModel):
    name: TeamName


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    member_count: int
    """Active and inactive users currently in the team."""
    created_at: datetime
