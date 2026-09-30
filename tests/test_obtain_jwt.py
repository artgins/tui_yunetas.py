#
#   test_obtain_jwt.py
#
#   An IdP that answers an access_token that is not a string (a number, an
#   object) must be refused with a clear error, not passed to ycommand's argv,
#   where Python raises TypeError.
#
import types

import pytest

from yunetas.agent_tools import set_start_priorities, sync_binaries, sync_configs

MODULES = [sync_configs, sync_binaries, set_start_priorities]


def make_args():
    return types.SimpleNamespace(
        jwt=None,
        user_id="someone",
        user_passw="x",
        issuer=None,
        token_endpoint="https://idp.invalid/token",
        client_id="cli",
        client_secret=None,
    )


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize("token", [12345, {"a": 1}, ["x"], "", None])
def test_obtain_jwt_refuses_a_token_that_is_not_a_string(module, token, monkeypatch, capsys):
    monkeypatch.setattr(module, "_http_json", lambda url, data=None: {"access_token": token})
    with pytest.raises(SystemExit) as e:
        module.obtain_jwt(make_args())
    assert e.value.code == 2
    assert "access_token" in capsys.readouterr().out


@pytest.mark.parametrize("module", MODULES)
def test_obtain_jwt_returns_a_string_token(module, monkeypatch):
    monkeypatch.setattr(module, "_http_json", lambda url, data=None: {"access_token": "abc.def.ghi"})
    assert module.obtain_jwt(make_args()) == "abc.def.ghi"
