import pytest


def test_sandboxed_env_blocks_dunder_attribute_access():
    """SandboxedEnvironment must block __class__ access chains."""
    from jinja2 import StrictUndefined
    from jinja2.exceptions import SecurityError
    from jinja2.sandbox import SandboxedEnvironment

    env = SandboxedEnvironment(
        variable_start_string="${",
        variable_end_string="}",
        undefined=StrictUndefined,
    )
    template = env.from_string("${'x'.__class__}")
    with pytest.raises(SecurityError):
        template.render()
