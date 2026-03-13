"""Tests for gapp.sdk.deploy — build and tfvars logic."""

from gapp.sdk.deploy import _build_tfvars, _get_template, _secret_name_to_env_var


def test_dockerfile_template_exists():
    path = _get_template("Dockerfile")
    assert path.exists()
    content = path.read_text()
    assert "ARG ENTRYPOINT" in content
    assert "uvicorn" in content
    assert "8080" in content


def test_secret_name_to_env_var():
    assert _secret_name_to_env_var("api-token") == "API_TOKEN"
    assert _secret_name_to_env_var("some-api-key") == "SOME_API_KEY"


def test_build_tfvars():
    config = {
        "entrypoint": "app:main",
        "port": 8080,
        "memory": "512Mi",
        "cpu": "1",
        "max_instances": 1,
        "public": False,
        "env": {},
    }
    tfvars = _build_tfvars("my-app", "my-project", "img:abc123", config)
    assert tfvars["project_id"] == "my-project"
    assert tfvars["service_name"] == "my-app"
    assert tfvars["image"] == "img:abc123"
    assert tfvars["public"] is False
    assert tfvars["secrets"] == {}


def test_build_tfvars_with_secrets():
    config = {
        "entrypoint": "app:main",
        "port": 8080,
        "memory": "512Mi",
        "cpu": "1",
        "max_instances": 1,
        "public": False,
        "env": {},
    }
    secrets = {"api-token": {"description": "Auth token"}}
    tfvars = _build_tfvars("my-app", "proj", "img:abc123", config, secrets)
    assert tfvars["secrets"] == {"API_TOKEN": "api-token"}


def test_build_tfvars_with_env():
    config = {
        "entrypoint": "app:main",
        "port": 8080,
        "memory": "512Mi",
        "cpu": "1",
        "max_instances": 1,
        "public": True,
        "env": {"DB_HOST": "localhost"},
    }
    tfvars = _build_tfvars("my-app", "proj", "img:abc123", config)
    assert tfvars["env"] == {"DB_HOST": "localhost"}
    assert tfvars["public"] is True


def test_build_tfvars_auth_disabled():
    config = {
        "entrypoint": "app:main",
        "port": 8080,
        "memory": "512Mi",
        "cpu": "1",
        "max_instances": 1,
        "public": False,
        "env": {},
    }
    tfvars = _build_tfvars("my-app", "proj", "img:abc123", config)
    assert tfvars["auth_enabled"] is False
    assert tfvars["auth_bucket"] == ""
    assert "GAPP_APP" not in tfvars["env"]


def test_build_tfvars_auth_enabled():
    config = {
        "entrypoint": "monarch.mcp.server:mcp_app",
        "port": 8080,
        "memory": "512Mi",
        "cpu": "1",
        "max_instances": 1,
        "public": True,
        "env": {"LOG_LEVEL": "INFO"},
    }
    auth = {"enabled": True, "strategy": "bearer"}
    tfvars = _build_tfvars("monarch-access", "proj", "img:abc123", config, auth_config=auth)
    assert tfvars["auth_enabled"] is True
    assert tfvars["auth_bucket"] == "gapp-monarch-access-proj"
    assert tfvars["env"]["GAPP_APP"] == "monarch.mcp.server:mcp_app"
    # Original env vars preserved
    assert tfvars["env"]["LOG_LEVEL"] == "INFO"


def test_build_tfvars_auth_does_not_mutate_original_env():
    config = {
        "entrypoint": "app:main",
        "port": 8080,
        "memory": "512Mi",
        "cpu": "1",
        "max_instances": 1,
        "public": False,
        "env": {"FOO": "bar"},
    }
    original_env = config["env"].copy()
    auth = {"enabled": True, "strategy": "bearer"}
    _build_tfvars("my-app", "proj", "img:abc123", config, auth_config=auth)
    # Original config dict should not be modified
    assert config["env"] == original_env


def test_dockerfile_template_supports_runtime_install():
    path = _get_template("Dockerfile")
    content = path.read_text()
    assert ".gapp-run" in content
