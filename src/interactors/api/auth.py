from fastapi import HTTPException, Request

DEV_USER_ID = "dev-user"


def current_user_id(request: Request) -> str:
    """Dev mode: fixed local user. Auth0 JWT validation replaces this in remote profile (A5)."""
    settings = request.app.state.settings
    if settings.auth_mode == "dev":
        return DEV_USER_ID
    raise HTTPException(status_code=501, detail="auth0 mode not implemented yet")
