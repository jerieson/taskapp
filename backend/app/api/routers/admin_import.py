"""Admin imports from the team's spreadsheet."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.core.config import SettingsDep
from app.core.dependencies import CurrentUser, require_role
from app.db.session import SessionDep
from app.models import Role
from app.schemas.lookups import DataTabImportOut
from app.schemas.support import SupportImportOut
from app.services import data_import as service
from app.services import support_import

router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(require_role(Role.ADMIN))]
)


@router.post("/import/data-tab", response_model=DataTabImportOut)
async def import_data_tab(
    file: Annotated[UploadFile, File(description="The sheet's Data tab saved as CSV")],
    db: SessionDep,
) -> DataTabImportOut:
    """Create missing categories, projects, activity groups, activities and O&M projects
    from the Data tab and link them. Idempotent; never deletes or renames anything."""
    content = await file.read(service.MAX_FILE_BYTES + 1)
    return await service.import_data_tab(db, content)


@router.post("/support/import", response_model=SupportImportOut)
async def import_support(
    file: Annotated[UploadFile, File(description="The support dictionary sheet saved as CSV")],
    user: CurrentUser,
    db: SessionDep,
    settings: SettingsDep,
    dry_run: Annotated[bool, Query(description="Preview: report counts, save nothing")] = False,
) -> SupportImportOut:
    """Create support entries from the team's sheet (see the service for the rules).
    Rows already in the dictionary are skipped, so re-importing creates nothing new."""
    content = await file.read(support_import.MAX_FILE_BYTES + 1)
    return await support_import.import_support(db, user, content, settings, dry_run=dry_run)
