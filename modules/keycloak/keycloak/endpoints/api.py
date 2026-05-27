"""Keycloak OIDC API endpoints — login redirect, callback."""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["keycloak-auth"])
