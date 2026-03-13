"""Bearer strategy — simple token passthrough."""


def get_access_token(credential: dict) -> str:
    """Extract the bearer token from the credential file.

    Returns the token as-is. No refresh, no write-back.
    """
    token = credential.get("credential")
    if not token:
        raise ValueError("Credential file missing 'credential' field")
    return token
