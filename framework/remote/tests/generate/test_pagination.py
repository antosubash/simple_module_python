from simple_module_remote.generate.operations import Operation, Param
from simple_module_remote.http.pagination import iter_items, pagination_style


def make_op(*names: str) -> Operation:
    params = tuple(Param(n, "query", False, {"type": "integer"}, "") for n in names)
    return Operation(
        "x", "GET", "/api/x", "g", "n", params, "none", None, "", "", False, False, True
    )


ENVELOPE = {"type": "object", "properties": {"items": {}, "pages": {}, "total": {}}}
FILES = {"type": "object", "properties": {"items": {}, "total": {}}}


def test_style_detection():
    op = make_op("page", "per_page")
    assert pagination_style(op, {"type": "array"}) == "page_per_page"
    assert pagination_style(op, ENVELOPE) == "page_envelope"
    assert pagination_style(op, FILES) == "file_storage"
    assert pagination_style(make_op("page"), ENVELOPE) is None
    assert pagination_style(op, None) is None


class Server:
    def __init__(self, total: int, shape: str) -> None:
        self.total, self.shape, self.calls = total, shape, []

    def __call__(self, params: dict):
        self.calls.append(dict(params))
        page, size = params["page"], params["per_page"]
        items = list(range(self.total))[(page - 1) * size : page * size]
        if self.shape == "array":
            return items
        body = {"items": items, "total": self.total, "page": page, "per_page": size}
        if self.shape == "envelope":
            body["pages"] = -(-self.total // size)
        return body


def collect(shape, style, total=5, per_page=2, limit=None):
    server, progress = Server(total, shape), []
    items = list(iter_items(server, style, {"per_page": per_page}, limit, progress.append))
    return items, server, progress


def test_page_envelope_uses_pages():
    items, server, _ = collect("envelope", "page_envelope", total=4)
    assert items == [0, 1, 2, 3]
    assert len(server.calls) == 2  # pages=2 stops without a third request


def test_page_per_page_array():
    items, server, progress = collect("array", "page_per_page")
    assert items == [0, 1, 2, 3, 4]
    assert [c["page"] for c in server.calls] == [1, 2, 3]
    assert progress == [2, 4, 5]


def test_file_storage_total():
    items, server, _ = collect("files", "file_storage", total=4)
    assert items == [0, 1, 2, 3]
    assert len(server.calls) == 2


def test_limit_stops_early():
    items, server, _ = collect("array", "page_per_page", limit=3)
    assert items == [0, 1, 2]
    assert len(server.calls) == 2


def test_short_page_stops():
    items, server, _ = collect("array", "page_per_page", total=3)
    assert items == [0, 1, 2]
    assert len(server.calls) == 2


def test_empty_page_stops_and_default_per_page():
    server = Server(0, "array")
    assert list(iter_items(server, "page_per_page", {}, None, lambda n: None)) == []
    assert server.calls[0]["per_page"] == 100


def test_clamped_per_page_continues_while_metadata_says_more():
    def fetch(params):
        page = params["page"]
        return {"items": [page] * 2, "total": 6, "page": page, "per_page": 2, "pages": 3}

    # Requested 100 but the server serves 2 per page.
    assert list(iter_items(fetch, "page_envelope", {}, None, lambda n: None)) == [1, 1, 2, 2, 3, 3]

    def files(params):
        page = params["page"]
        return {"items": [page] * 2, "total": 4, "page": page}

    assert list(iter_items(files, "file_storage", {"per_page": 50}, None, lambda n: None)) == [
        1, 1, 2, 2,
    ]  # fmt: skip
