"""Admin imports from the team's spreadsheet."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile

from app.core.dependencies import require_role
from app.db.session import SessionDep
from app.models import Role
from app.schemas.lookups import DataTabImportOut
from app.services import data_import as service

router = APIRouter(
    prefix="/admin/import", tags=["admin"], dependencies=[Depends(require_role(Role.ADMIN))]
)


@router.post("/data-tab", response_model=DataTabImportOut)
async def import_data_tab(
    file: Annotated[UploadFile, File(description="The sheet's Data tab saved as CSV")],
    db: SessionDep,
) -> DataTabImportOut:
    """Create missing categories, projects, activity groups, activities and O&M projects
    from the Data tab and link them. Idempotent; never deletes or renames anything."""
    content = await file.read(service.MAX_FILE_BYTES + 1)
    return await service.import_data_tab(db, content)
