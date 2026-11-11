from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str = Field(examples=["not_found"])
    message: str = Field(examples=["Not Found"])
    fields: dict[str, str] | None = Field(
        default=None, description="Present only for validation errors."
    )


class ErrorResponse(BaseModel):
    error: ErrorBody
