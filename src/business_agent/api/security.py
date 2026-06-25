from typing import Annotated

from fastapi import Header, HTTPException, status

from business_agent.config import get_settings


def verify_internal_api_token(
    x_api_token: Annotated[str | None, Header(alias="X-API-Token")] = None,
) -> None:
    token = get_settings().internal_api_token
    if token and x_api_token != token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API token.",
        )

