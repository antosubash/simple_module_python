"""URL builders consuming modules can use without hard-coding prefixes.

If the Datasets module's ``route_prefix`` ever changes, downstream modules
don't have to audit every hard-coded ``/api/datasets/...`` string — they
just re-import these helpers.
"""

from __future__ import annotations

API_PREFIX = "/api/datasets"
VIEW_PREFIX = "/datasets"


def download_url(dataset_id: int) -> str:
    """URL that streams the dataset's stored file back to the client."""
    return f"{API_PREFIX}/{dataset_id}/download"


def detail_url(dataset_id: int) -> str:
    """URL of the dataset's JSON detail endpoint."""
    return f"{API_PREFIX}/{dataset_id}"


def show_url(dataset_id: int) -> str:
    """URL of the Inertia ``Show`` page."""
    return f"{VIEW_PREFIX}/{dataset_id}"
