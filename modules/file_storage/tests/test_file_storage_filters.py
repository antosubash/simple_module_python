"""Search and content-type filtering for the file browse screen.

The screen shipped with neither, so a bucket past its first page was only
navigable by luck. These cover the filters and — importantly — that the
total travels with them, since a count that ignores the filter produces a
pager offering pages that render empty.
"""

from __future__ import annotations

from io import BytesIO

from fastapi import UploadFile
from file_storage import constants
from file_storage.backends.filesystem import FilesystemBackend
from file_storage.service import FileStorageService
from file_storage.settings import FileStorageSettings
from sqlalchemy.ext.asyncio import AsyncSession


def _upload(name: str, content_type: str) -> UploadFile:
    return UploadFile(
        filename=name,
        file=BytesIO(b"payload"),
        headers={"content-type": content_type},  # type: ignore[arg-type]
    )


def _service(tmp_path, db_session: AsyncSession) -> FileStorageService:
    settings = FileStorageSettings(
        backend=constants.BackendId.FILESYSTEM,
        fs_root_path=str(tmp_path),
    )
    return FileStorageService(db_session, FilesystemBackend(root=tmp_path), settings)


async def _seed(svc: FileStorageService) -> None:
    await svc.upload(_upload("q3-report.pdf", "application/pdf"))
    await svc.upload(_upload("export-2026-08.csv", "text/csv"))
    await svc.upload(_upload("logo.png", "image/png"))
    await svc.upload(_upload("banner.jpeg", "image/jpeg"))


async def test_search_matches_filename_substring(tmp_path, db_session: AsyncSession):
    svc = _service(tmp_path, db_session)
    await _seed(svc)

    items, total = await svc.list_files(search="report")
    assert [i.filename for i in items] == ["q3-report.pdf"]
    assert total == 1


async def test_search_is_case_insensitive(tmp_path, db_session: AsyncSession):
    svc = _service(tmp_path, db_session)
    await _seed(svc)

    items, _ = await svc.list_files(search="REPORT")
    assert [i.filename for i in items] == ["q3-report.pdf"]


async def test_exact_content_type_filter(tmp_path, db_session: AsyncSession):
    svc = _service(tmp_path, db_session)
    await _seed(svc)

    items, total = await svc.list_files(content_type="application/pdf")
    assert [i.filename for i in items] == ["q3-report.pdf"]
    assert total == 1


async def test_trailing_slash_selects_a_whole_family(tmp_path, db_session: AsyncSession):
    """`image/` has to catch png and jpeg, or the filter is useless on a
    bucket holding nine kinds of image."""
    svc = _service(tmp_path, db_session)
    await _seed(svc)

    items, total = await svc.list_files(content_type="image/")
    assert sorted(i.filename for i in items) == ["banner.jpeg", "logo.png"]
    assert total == 2


async def test_search_and_type_filters_combine(tmp_path, db_session: AsyncSession):
    svc = _service(tmp_path, db_session)
    await _seed(svc)

    items, total = await svc.list_files(search="o", content_type="image/png")
    assert [i.filename for i in items] == ["logo.png"]
    assert total == 1


async def test_total_reflects_the_filter_not_the_table(tmp_path, db_session: AsyncSession):
    """A total that ignores the filter yields pages that render empty."""
    svc = _service(tmp_path, db_session)
    await _seed(svc)

    _, unfiltered = await svc.list_files()
    _, filtered = await svc.list_files(search="report")
    assert unfiltered == 4
    assert filtered == 1


async def test_facets_report_present_types_with_counts(tmp_path, db_session: AsyncSession):
    svc = _service(tmp_path, db_session)
    await _seed(svc)

    facets = {f["value"]: f["count"] for f in await svc.content_type_facets()}
    assert facets == {
        "application/pdf": 1,
        "text/csv": 1,
        "image/png": 1,
        "image/jpeg": 1,
    }


async def test_facets_are_empty_for_an_empty_bucket(tmp_path, db_session: AsyncSession):
    svc = _service(tmp_path, db_session)
    assert await svc.content_type_facets() == []


async def test_deleted_files_leave_the_facets(tmp_path, db_session: AsyncSession):
    """Offering a type filter that matches nothing is a dead end."""
    svc = _service(tmp_path, db_session)
    out = await svc.upload(_upload("q3-report.pdf", "application/pdf"))
    await svc.upload(_upload("logo.png", "image/png"))

    await svc.delete(out.id)

    facets = {f["value"] for f in await svc.content_type_facets()}
    assert facets == {"image/png"}
