"""账户管理（ADR-0019 D1：无自助注册，账户只在服务器上建）。

用法（仓根，直连真实 data/flai_os.db；e2e/测试传 --db 指向 tmp 库）：
    python3 scripts/user_admin.py create <username> <display_name>   # 密码 getpass 交互输入
    python3 scripts/user_admin.py list
    python3 scripts/user_admin.py deactivate <username>
    python3 scripts/user_admin.py activate <username>
    python3 scripts/user_admin.py reset-password <username>

纪律：
- 密码绝不走 argv（进程列表/shell 历史不落密码）；非交互场景（部署脚本）
  用环境变量 FLAI_USER_PASSWORD 一次性传入，用后即清。
- 停用/改密即时吊销该用户全部会话（service 层保证）。
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.app import config  # noqa: E402
from backend.app.auth import service  # noqa: E402
from backend.app.storage.db import get_conn, init_db  # noqa: E402


def _read_password(confirm: bool) -> str:
    env_pw = os.environ.get("FLAI_USER_PASSWORD")
    if env_pw:
        return env_pw
    pw = getpass.getpass("密码：")
    if confirm:
        again = getpass.getpass("再输一次：")
        if pw != again:
            sys.exit("两次输入不一致，未做任何修改。")
    if not pw:
        sys.exit("密码不得为空，未做任何修改。")
    return pw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # 默认库跟随 config.DB_PATH（尊重 FLAI_DB_PATH 环境覆盖，Codex 审 P1）——
    # 否则内网若设 FLAI_DB_PATH，本脚本会把账户写进 data/flai_os.db 而线上库
    # 无人，全员锁死在门外。
    parser.add_argument("--db", default=str(config.DB_PATH))
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_create = sub.add_parser("create")
    p_create.add_argument("username")
    p_create.add_argument("display_name")
    sub.add_parser("list")
    for name in ("deactivate", "activate", "reset-password"):
        p = sub.add_parser(name)
        p.add_argument("username")
    args = parser.parse_args()

    # 密码在开写事务**之前**读（Codex 审 P2）：getpass 交互可能持续数十秒，
    # 若在 BEGIN IMMEDIATE 之后读，管理员打字期间全应用写者被锁、5s 后开始
    # 报 database is locked。此处先拿到密码，再进短事务。
    new_password: str | None = None
    if args.cmd in ("create", "reset-password"):
        new_password = _read_password(confirm=True)

    db_path = Path(args.db)
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if args.cmd == "create":
                user = service.create_user(
                    conn, username=args.username, display_name=args.display_name,
                    password=new_password,
                )
                print(f"已创建：{user['username']}（{user['display_name']}）")
            elif args.cmd == "list":
                users = service.list_users(conn)
                if not users:
                    print("（无账户——部署第一步：create 建首个账户，否则所有人在登录门外）")
                for u in users:
                    state = "active" if u["is_active"] == 1 else "DEACTIVATED"
                    print(f"{u['username']:<20} {u['display_name']:<12} {state}  建于 {u['created_at']}")
            elif args.cmd == "deactivate":
                service.set_user_active(conn, args.username, False)
                print(f"已停用并吊销全部会话：{args.username}")
            elif args.cmd == "activate":
                service.set_user_active(conn, args.username, True)
                print(f"已启用：{args.username}")
            elif args.cmd == "reset-password":
                service.reset_password(conn, args.username, new_password)
                print(f"已改密并吊销旧会话：{args.username}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    except ValueError as exc:
        print(f"诚实失败：{exc}")
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
