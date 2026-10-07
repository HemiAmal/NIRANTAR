"""`python -m nirantar users ...`: account administration on the server (never over the network)."""
from __future__ import annotations

import getpass
import sys
from datetime import datetime

from nirantar.rakshak.auth import ALL_ROLES, AuthError, UserStore


def _passphrase(prompt: str = "Passphrase") -> str:
    if not sys.stdin.isatty():                       # scripted use: one line on stdin
        return sys.stdin.readline().rstrip("\n")
    a = getpass.getpass(f"{prompt}: ")
    if getpass.getpass("Again: ") != a:
        raise AuthError("the two entries differ")
    return a


def users_command(args) -> None:
    st = UserStore(args.db)
    roles = [r.strip() for r in args.roles.split(",")] if args.roles else None
    try:
        if args.action == "list":
            for u in st.users():
                state = "disabled" if u["disabled"] else "locked" if u["locked"] else "active"
                print(f"{u['username']:16s} {state:8s} {u['actor']:24s} {', '.join(u['roles'])}")
            if not st.users():
                print(f"no accounts yet; roles: {', '.join(ALL_ROLES)}")
            return
        if args.action == "audit":
            for e in reversed(st.audit_log(100)):
                print(f"{datetime.fromtimestamp(e['ts']):%Y-%m-%d %H:%M:%S}  {e['username'] or '-':12s} "
                      f"{e['event']:16s} {e['detail'] or ''} {e['ip'] or ''}")
            return
        if not args.username:
            raise AuthError("give a username")
        if args.action == "add":
            if not roles:
                raise AuthError(f"give --roles (any of: {', '.join(ALL_ROLES)})")
            u = st.create_user(args.username, _passphrase(), roles, args.display)
            print(f"added {u['username']} as {', '.join(u['roles'])}; signs as {u['actor']}")
        elif args.action == "roles":
            u = st.set_roles(args.username, roles or [])
            print(f"{u['username']}: {', '.join(u['roles'])} (signed out everywhere)")
        elif args.action in ("disable", "enable"):
            u = st.set_disabled(args.username, args.action == "disable")
            print(f"{u['username']}: {'disabled' if u['disabled'] else 'enabled'}")
        elif args.action == "reset-password":
            u = st.reset_password(args.username, _passphrase("New passphrase"))
            print(f"{u['username']}: new passphrase and new signing key {u['actor']}")
    except AuthError as exc:
        raise SystemExit(f"error: {exc}")
