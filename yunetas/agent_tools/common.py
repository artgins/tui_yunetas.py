# -*- coding: utf-8 -*-
"""
common.py — what the three agent tools (sync_binaries, sync_configs,
set_start_priorities) share: the colours, the reading of ycommand's JSON, the
version compare, the OAuth2 login and the connection flags of every ycommand
call.

Each tool carried its own copy of all of it, identical, until 0.23.0: three
copies of the login are three places for a fix to miss. Stdlib only, like the
tools.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

# ----------------------------------------------------------------------------
#   ANSI colours (only when stdout is a tty)
# ----------------------------------------------------------------------------
_TTY = sys.stdout.isatty()


def c(code, s):
    if not _TTY:
        return s
    return "\033[%sm%s\033[0m" % (code, s)


def bold(s):
    return c("1", s)


def green(s):
    return c("32", s)


def yellow(s):
    return c("33", s)


def red(s):
    return c("31", s)


def cyan(s):
    return c("36", s)


def dim(s):
    return c("90", s)


# ----------------------------------------------------------------------------
#   ycommand output and versions
# ----------------------------------------------------------------------------
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def parse_leading_json(text):
    """
    ycommand wraps the JSON payload with a leading blank line and a trailing
    coloured footer (the command name). Strip ANSI, locate the first '[' or '{'
    and decode just that value, ignoring whatever trails it.
    """
    clean = _ANSI_RE.sub("", text or "")
    start = None
    for i, ch in enumerate(clean):
        if ch in "[{":
            start = i
            break
    if start is None:
        raise json.JSONDecodeError("no JSON value found", clean, 0)
    obj, _ = json.JSONDecoder().raw_decode(clean[start:])
    return obj


def version_tuple(v):
    """
    Turn '7.4.5' or '1.4.4.0' into a comparable tuple of ints. Non-numeric
    chunks fall back to 0 so a malformed version never crashes the compare.
    """
    parts = []
    for chunk in str(v).split("."):
        m = re.match(r"\d+", chunk)
        parts.append(int(m.group(0)) if m else 0)
    return tuple(parts)


def cmp_versions(a, b):
    ta, tb = version_tuple(a), version_tuple(b)
    if ta < tb:
        return -1
    if ta > tb:
        return 1
    return 0


# ----------------------------------------------------------------------------
#   OAuth2 — log in ONCE, reuse the token on every ycommand call
# ----------------------------------------------------------------------------
#   ycommand reads its credentials only from argp and does NOT cache a token
#   between one-shot `-c` invocations, so passing -x/-X would re-run the
#   password grant on every call. Instead we log in once here (Keycloak
#   password grant), then thread the resulting jwt through `-j` to every
#   invocation. This is what lets these scripts drive a REMOTE wss:// agent
#   with SSH disabled.
def _http_json(url, data=None, timeout=30):
    """GET (data=None) or form-urlencoded POST, returning parsed JSON."""
    body = None
    headers = {}
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def discover_token_endpoint(issuer, timeout=30):
    """Read token_endpoint from the issuer's OIDC discovery document."""
    doc = _http_json(issuer.rstrip("/") + "/.well-known/openid-configuration",
                     timeout=timeout)
    ep = doc.get("token_endpoint") if isinstance(doc, dict) else None
    if not isinstance(ep, str) or not ep:
        raise RuntimeError("OIDC discovery document has no token_endpoint")
    return ep


def obtain_jwt(args):
    """
    Return one jwt to reuse on every ycommand call, or None for a local/
    unauthenticated run:
      * --jwt given                                 -> used verbatim.
      * user-id + passw + (issuer | token-endpoint) -> password grant, once.
      * otherwise                                   -> None (local ws:// needs none).
    """
    if args.jwt:
        return args.jwt
    if not (args.user_id and args.user_passw and (args.issuer or args.token_endpoint)):
        return None
    try:
        token_endpoint = args.token_endpoint or discover_token_endpoint(args.issuer)
    except Exception as e:
        print(red("ERROR: OIDC discovery failed: %s" % e))
        sys.exit(2)
    form = {
        "grant_type": "password",
        "client_id": args.client_id or "",
        "username": args.user_id,
        "password": args.user_passw,
    }
    if args.client_secret:
        form["client_secret"] = args.client_secret
    print(dim("authenticating once at %s ..." % token_endpoint))
    try:
        tok = _http_json(token_endpoint, data=form)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        print(red("ERROR: OAuth2 login failed (HTTP %s): %s" % (e.code, detail or e.reason)))
        sys.exit(2)
    except Exception as e:
        print(red("ERROR: OAuth2 login failed: %s" % e))
        sys.exit(2)
    jwt = tok.get("access_token") if isinstance(tok, dict) else None
    if not isinstance(jwt, str) or not jwt:
        print(red("ERROR: token endpoint returned no access_token (or not a string)."))
        sys.exit(2)
    return jwt


# ----------------------------------------------------------------------------
#   Connection flags of every ycommand call
# ----------------------------------------------------------------------------
#   TLS flags for a wss:// agent, set once in main() and used by every call.
#   The agent serves one long-life certificate of its own on every node, so
#   the name never matches the host dialed: --ssl-server-name says which name
#   to check the certificate against, and the chain is still validated.
TLS_FLAGS = []


def ycmd_base(ycommand, url, jwt):
    """Base ycommand argv: binary + optional -u url + optional -j jwt + TLS."""
    cmd = [ycommand]
    if url:
        cmd += ["-u", url]
    if jwt:
        cmd += ["-j", jwt]
    cmd += TLS_FLAGS
    return cmd


def set_tls_flags(args):
    """Record the TLS flags of the run, from the parsed arguments."""
    global TLS_FLAGS
    flags = []
    trusted = getattr(args, "ssl_trusted_certificate", None)
    if trusted:
        flags += ["--ssl-trusted-certificate", trusted]
    server_name = getattr(args, "ssl_server_name", None)
    if server_name:
        flags += ["--ssl-server-name", server_name]
    TLS_FLAGS = flags


def add_agent_arguments(ap):
    """
    The arguments every tool takes to reach an agent: url, ycommand path, the
    OAuth2 identity and the TLS of a wss:// agent. The password and the client
    secret default to the environment, which keeps them out of the process
    list (an argument is visible to every local user in `ps`).
    """
    ap.add_argument("-u", "--url", default=None,
                    help="ycommand url (default: ws://127.0.0.1:1991).")
    ap.add_argument("--ycommand", default=None,
                    help="path to ycommand (default: search PATH).")

    auth = ap.add_argument_group(
        "OAuth2 (remote wss:// agent; logs in ONCE, reuses the token via -j)")
    auth.add_argument("-I", "--issuer", default=None,
                      help="OIDC issuer for discovery, e.g. "
                           "https://auth.artgins.com/realms/artgins")
    auth.add_argument("-T", "--token-endpoint", default=None,
                      help="explicit token endpoint (skips discovery).")
    auth.add_argument("-Z", "--client-id", default=None, help="OAuth2 client_id.")
    auth.add_argument("--client-secret", default=os.environ.get("YUNETA_OAUTH_CLIENT_SECRET"),
                      help="OAuth2 client_secret (confidential client only; "
                           "default: $YUNETA_OAUTH_CLIENT_SECRET).")
    auth.add_argument("-x", "--user-id", default=None, help="OAuth2 username.")
    auth.add_argument("-X", "--user-passw", default=os.environ.get("YUNETA_OAUTH_PASSW"),
                      help="OAuth2 password (default: $YUNETA_OAUTH_PASSW, which "
                           "keeps it out of the process list).")
    auth.add_argument("-j", "--jwt", default=None,
                      help="reuse this jwt directly (skip the login).")

    tls = ap.add_argument_group("TLS (wss:// agent)")
    tls.add_argument("--ssl-trusted-certificate", default=None,
                     help="PEM of the CA that signs the agent certificate.")
    tls.add_argument("--ssl-server-name", default=None,
                     help="name to check the agent certificate against "
                          "(default: the host of the url).")


def ask(prompt):
    try:
        return input(prompt).strip().lower()
    except EOFError:
        return "q"
