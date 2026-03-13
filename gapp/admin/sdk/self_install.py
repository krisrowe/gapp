"""gapp admin install — register gapp's admin MCP server with agent clients."""

import subprocess


def install_admin_mcp(client: str, scope: str = "user") -> dict:
    """Register the gapp-admin MCP server with an agent client.

    Args:
        client: "claude" or "gemini"
        scope: "user" or "project"

    Returns dict with: client, scope, status, command
    """
    if client not in ("claude", "gemini"):
        raise ValueError(f"Unknown client: {client}. Use 'claude' or 'gemini'.")
    if scope not in ("user", "project"):
        raise ValueError(f"Unknown scope: {scope}. Use 'user' or 'project'.")

    if client == "claude":
        cmd = ["claude", "mcp", "add", "-s", scope, "gapp-admin", "gapp-mcp"]
    else:
        cmd = ["gemini", "mcp", "add", "gapp-admin", "gapp-mcp", "--scope", scope]

    result = subprocess.run(cmd, capture_output=True, text=True)

    return {
        "client": client,
        "scope": scope,
        "success": result.returncode == 0,
        "command": " ".join(cmd),
        "output": result.stdout.strip() if result.stdout.strip() else result.stderr.strip(),
    }


def check_admin_mcp_registration(client: str, scope: str = "user") -> bool:
    """Check if gapp-admin is registered with a client at the given scope."""
    if client == "claude":
        cmd = ["claude", "mcp", "list", "-s", scope]
    elif client == "gemini":
        cmd = ["gemini", "mcp", "list", "--scope", scope]
    else:
        return False

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return "gapp-admin" in result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
