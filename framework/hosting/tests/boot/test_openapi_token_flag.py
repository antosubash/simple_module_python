from fastapi import Depends, FastAPI
from simple_module_hosting.auth.token_guard import TokenAllowed
from simple_module_hosting.boot._openapi import install_openapi_filter
from simple_module_hosting.pipeline._route_access import check_unguarded_api_routes


async def test_operations_carry_token_flag(app):
    schema = app.openapi()
    flags = {
        op["operationId"]: op["x-sm-token"]
        for item in schema["paths"].values()
        for op in item.values()
        if isinstance(op, dict) and "operationId" in op
    }
    assert flags["meta_whoami"] is True
    assert flags["tenants_list_mine"] is False
    assert flags["users_admin_list_users"] is True
    assert all(isinstance(value, bool) for value in flags.values())
    assert not any("/api/_meta/whoami" in d.message for d in check_unguarded_api_routes(app))


def test_schema_included_head_carries_token_flag():
    app = FastAPI()
    app.add_api_route(
        "/api/probe", lambda: None, methods=["HEAD"], dependencies=[Depends(TokenAllowed())]
    )
    install_openapi_filter(app)
    assert app.openapi()["paths"]["/api/probe"]["head"]["x-sm-token"] is True
