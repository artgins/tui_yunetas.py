#
#   test_node_connection.py
#
#   Where the credentials of a registered node go:
#     - never on a command line as a password or a client secret (any local
#       user reads them in `ps`): the tools inherit them in the environment;
#     - the ycommand calls of the CLI log in ONCE and carry the jwt alone,
#       because ycommand runs its own password grant whenever it is given an
#       issuer and a user id, and it knows no --client-secret.
#
import pytest

import yunetas.main as m

NODE = {
    "name": "prod",
    "url": "wss://node.invalid:1993",
    "issuer": "https://idp.invalid/realms/r",
    "client_id": "node.invalid",
    "user_id": "me@invalid",
    "ssl_trusted_certificate": "/ca.pem",
    "ssl_server_name": "agent",
}
TLS = ["--ssl-trusted-certificate", "/ca.pem", "--ssl-server-name", "agent"]


@pytest.fixture
def env(monkeypatch):
    for name in (m.ENV_OAUTH_PASSW, m.ENV_OAUTH_CLIENT_SECRET, m.ENV_OAUTH_JWT):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def connection(node=NODE):
    conn = m.NodeConnection(dict(node))
    conn.url = node["url"]
    return conn


def test_tool_args_carry_no_secret(env):
    env.setenv(m.ENV_OAUTH_PASSW, "the-password")
    env.setenv(m.ENV_OAUTH_CLIENT_SECRET, "the-secret")
    args = connection().args()
    assert "the-password" not in args
    assert "the-secret" not in args
    assert "-X" not in args and "--client-secret" not in args
    assert args[:2] == ["-u", NODE["url"]]
    assert ["-x", "me@invalid"] == args[args.index("-x"):args.index("-x") + 2]


def test_tool_args_forward_a_given_jwt(env):
    env.setenv(m.ENV_OAUTH_JWT, "a.b.c")
    args = connection().args()
    assert args[-2:] == ["-j", "a.b.c"]


def test_ycommand_args_log_in_once(env):
    env.setenv(m.ENV_OAUTH_PASSW, "the-password")
    env.setenv(m.ENV_OAUTH_CLIENT_SECRET, "the-secret")
    logins = []

    def fake_obtain_jwt(args):
        logins.append(args)
        return "x.y.z"

    env.setattr(m, "obtain_jwt", fake_obtain_jwt)
    conn = connection()
    first = conn.ycommand_args()
    second = conn.ycommand_args()
    assert first == second == ["-u", NODE["url"], "-j", "x.y.z"] + TLS
    assert len(logins) == 1
    assert logins[0].user_passw == "the-password"
    assert logins[0].client_secret == "the-secret"
    assert logins[0].issuer == NODE["issuer"]
    assert logins[0].client_id == NODE["client_id"]


def test_ycommand_args_use_a_given_jwt_without_the_identity(env):
    env.setenv(m.ENV_OAUTH_JWT, "a.b.c")
    env.setattr(m, "obtain_jwt", lambda args: pytest.fail("no login with a jwt given"))
    args = connection().ycommand_args()
    assert args == ["-u", NODE["url"], "-j", "a.b.c"] + TLS
    assert "-I" not in args and "-x" not in args


def test_ycommand_args_without_a_credential(env):
    env.setattr(m, "obtain_jwt", lambda args: pytest.fail("nothing to log in with"))
    args = connection().ycommand_args()
    assert "-j" not in args and "-X" not in args
    assert args[:2] == ["-u", NODE["url"]]


def test_ws_url_needs_no_oauth(env):
    env.setenv(m.ENV_OAUTH_PASSW, "the-password")
    env.setattr(m, "obtain_jwt", lambda args: pytest.fail("a ws:// agent needs no login"))
    conn = connection(dict(NODE, url="ws://127.0.0.1:41000"))
    assert conn.args() == ["-u", "ws://127.0.0.1:41000"]
    assert conn.ycommand_args() == ["-u", "ws://127.0.0.1:41000"]


def test_ycmd_conn_flags_follow_the_connection(env):
    env.setenv(m.ENV_OAUTH_JWT, "a.b.c")
    env.setattr(m, "AGENT_CONN", None)
    assert m.ycmd_conn_flags("ws://127.0.0.1:1991") == ["-u", "ws://127.0.0.1:1991"]
    m.set_agent_flags(connection())
    assert m.ycmd_conn_flags(None) == ["-u", NODE["url"], "-j", "a.b.c"] + TLS
