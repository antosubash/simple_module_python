"""Body-size limits for the upload endpoints."""

from __future__ import annotations

from simple_module_core.body_limits import BodyLimitRegistry

from file_storage import constants
from file_storage.upload_support import choose_part_size


def register_upload_body_limits(registry: BodyLimitRegistry) -> None:
    # The upload is multipart and its own ceiling (``max_file_size_bytes``,
    # a runtime setting, 100 MB by default) is far above the host's global
    # body guard. Track it, plus headroom for the multipart framing.
    registry.add_exact(
        constants.ROUTE_PREFIX_API + constants.PATH_UPLOAD,
        lambda app: (
            app.state.file_storage.settings.max_file_size_bytes + constants.MULTIPART_OVERHEAD_BYTES
        ),
        methods={"POST"},
    )

    # Filesystem parts are relayed through the app: one part at most, plus
    # slack. (S3 parts never reach us — they go straight to the bucket.)
    registry.add_regex(
        constants.ROUTE_PREFIX_API + r"/uploads/[^/]+/parts/\d+$",
        lambda app: (
            choose_part_size(
                app.state.file_storage.settings.max_direct_upload_bytes,
                app.state.file_storage.settings.multipart_part_size_bytes,
            )
            + constants.PART_BODY_SLACK_BYTES
        ),
        methods={"PUT"},
    )
