"""gapp admin MCP server — stdio-only, exposes admin SDK operations as tools."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gapp-admin")


@mcp.tool()
def gapp_status(solution: str | None = None) -> dict:
    """Infrastructure health check for a gapp solution.

    Returns deployment status, service URL, health, and guided next steps.
    """
    from gapp.admin.sdk.status import get_status
    return get_status(solution).model_dump()


@mcp.tool()
def gapp_list(available: bool = False) -> list[dict]:
    """List registered gapp solutions.

    Args:
        available: Include remote GitHub solutions.
    """
    from gapp.admin.sdk.solutions import list_solutions
    return list_solutions(include_remote=available)


@mcp.tool()
def gapp_mcp_status(solution: str | None = None) -> dict:
    """MCP health check with tool enumeration for a gapp solution.

    Returns MCP URL, health, auth status, and list of available tools.
    """
    from gapp.admin.sdk.mcp_status import mcp_status
    return mcp_status(solution).model_dump()


@mcp.tool()
def gapp_mcp_list() -> list[dict]:
    """List gapp solutions that have MCP endpoints configured."""
    from gapp.admin.sdk.mcp_status import mcp_list
    return [s.model_dump() for s in mcp_list()]


@mcp.tool()
def gapp_mcp_connect(solution: str | None = None, user: str | None = None) -> dict:
    """Generate MCP client connection info for a gapp solution.

    Shows connection details for Claude Code, Gemini CLI, and Claude.ai
    with registration status. If user email is specified, mints a real PAT.

    Args:
        solution: Solution name. Defaults to current directory's solution.
        user: Email of registered user to mint a real PAT for.
    """
    from gapp.admin.sdk.mcp_status import mcp_connect
    return mcp_connect(solution, user=user).model_dump()


@mcp.tool()
def gapp_users_list(solution: str | None = None, limit: int = 10) -> dict:
    """List registered users for a gapp solution.

    Args:
        solution: Solution name. Defaults to current directory's solution.
        limit: Maximum number of users to return.
    """
    from gapp.admin.sdk.users import list_users
    return list_users(limit=limit)


@mcp.tool()
def gapp_users_register(
    email: str,
    credential: str,
    strategy: str = "bearer",
) -> dict:
    """Register a user and store their upstream credential.

    Args:
        email: User's email address.
        credential: The upstream API token (e.g., Monarch session token).
        strategy: Credential strategy (default: bearer).
    """
    from gapp.admin.sdk.users import register_user
    return register_user(email, credential, strategy)


@mcp.tool()
def gapp_tokens_create(email: str, solution: str | None = None, duration_days: int = 3650) -> dict:
    """Create a signed PAT (JWT) for a registered user.

    Args:
        email: Email of the registered user.
        solution: Solution name. Defaults to current directory's solution.
        duration_days: Token validity in days (default: 3650 / ~10 years).
    """
    from gapp.admin.sdk.tokens import create_token
    return create_token(email, duration_days=duration_days, solution=solution)


@mcp.tool()
def gapp_tokens_revoke(email: str, solution: str | None = None) -> dict:
    """Invalidate all PATs for a user by setting revoke_before to now.

    Args:
        email: Email of the user whose tokens to revoke.
        solution: Solution name. Defaults to current directory's solution.
    """
    from gapp.admin.sdk.tokens import revoke_tokens
    return revoke_tokens(email, solution=solution)


def main():
    """Run the MCP server on stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
