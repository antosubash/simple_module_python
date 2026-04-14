"""Template generators for FastAPI endpoint files (api.py, views.py)."""

from __future__ import annotations

from _templates_py import ScaffoldContext


def api_py(ctx: ScaffoldContext) -> str:
    return f'''\
        """REST API endpoints for {ctx.class_name}."""

        from __future__ import annotations

        from fastapi import APIRouter, Depends, HTTPException

        from {ctx.pkg}.contracts.schemas import (
            {ctx.singular_class}Create,
            {ctx.singular_class}Out,
            {ctx.singular_class}Update,
        )
        from {ctx.pkg}.deps import get_{ctx.singular}_service
        from {ctx.pkg}.service import {ctx.singular_class}Service

        router = APIRouter()


        @router.get("/", response_model=list[{ctx.singular_class}Out])
        async def list_{ctx.name}(
            service: {ctx.singular_class}Service = Depends(get_{ctx.singular}_service),
        ) -> list[{ctx.singular_class}Out]:
            return await service.get_all()


        @router.get("/{{{ctx.singular}_id}}", response_model={ctx.singular_class}Out)
        async def get_{ctx.singular}(
            {ctx.singular}_id: int,
            service: {ctx.singular_class}Service = Depends(get_{ctx.singular}_service),
        ) -> {ctx.singular_class}Out:
            result = await service.get_by_id({ctx.singular}_id)
            if result is None:
                raise HTTPException(status_code=404, detail="{ctx.singular_class} not found")
            return result


        @router.post("/", response_model={ctx.singular_class}Out, status_code=201)
        async def create_{ctx.singular}(
            data: {ctx.singular_class}Create,
            service: {ctx.singular_class}Service = Depends(get_{ctx.singular}_service),
        ) -> {ctx.singular_class}Out:
            return await service.create(data)


        @router.put("/{{{ctx.singular}_id}}", response_model={ctx.singular_class}Out)
        async def update_{ctx.singular}(
            {ctx.singular}_id: int,
            data: {ctx.singular_class}Update,
            service: {ctx.singular_class}Service = Depends(get_{ctx.singular}_service),
        ) -> {ctx.singular_class}Out:
            result = await service.update({ctx.singular}_id, data)
            if result is None:
                raise HTTPException(status_code=404, detail="{ctx.singular_class} not found")
            return result


        @router.delete("/{{{ctx.singular}_id}}", status_code=204)
        async def delete_{ctx.singular}(
            {ctx.singular}_id: int,
            service: {ctx.singular_class}Service = Depends(get_{ctx.singular}_service),
        ) -> None:
            deleted = await service.delete({ctx.singular}_id)
            if not deleted:
                raise HTTPException(status_code=404, detail="{ctx.singular_class} not found")
        '''


def views_py(ctx: ScaffoldContext) -> str:
    return f'''\
        """Inertia view endpoints for {ctx.class_name}."""

        from __future__ import annotations

        from fastapi import APIRouter, Depends
        from inertia import InertiaResponse
        from simple_module_hosting.inertia_deps import InertiaDep

        from {ctx.pkg}.deps import get_{ctx.singular}_service
        from {ctx.pkg}.service import {ctx.singular_class}Service

        router = APIRouter()


        @router.get("/", response_model=None)
        async def browse(
            inertia: InertiaDep,
            service: {ctx.singular_class}Service = Depends(get_{ctx.singular}_service),
        ) -> InertiaResponse:
            items = await service.get_all()
            return await inertia.render(
                "{ctx.class_name}/Browse",
                {{"{ctx.name}": [item.model_dump(mode="json") for item in items]}},
            )


        @router.get("/create", response_model=None)
        async def create_view(inertia: InertiaDep) -> InertiaResponse:
            return await inertia.render("{ctx.class_name}/Create")


        @router.get("/{{{ctx.singular}_id}}/edit", response_model=None)
        async def edit_view(
            {ctx.singular}_id: int,
            inertia: InertiaDep,
            service: {ctx.singular_class}Service = Depends(get_{ctx.singular}_service),
        ) -> InertiaResponse:
            item = await service.get_by_id({ctx.singular}_id)
            if item is None:
                return await inertia.render(
                    "{ctx.class_name}/Browse",
                    {{"error": "{ctx.singular_class} not found"}},
                )
            return await inertia.render(
                "{ctx.class_name}/Edit",
                {{"{ctx.singular}": item.model_dump(mode="json")}},
            )
        '''
