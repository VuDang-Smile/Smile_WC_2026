#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.google_chat_context import build_context, resolve_subject_member_id, ChatActor

MEMBERS = [
    {
        "member_id": "M0001",
        "display_name": "Nam",
        "email": "nam@company.com",
        "google_chat_user_name": "users/111",
        "is_admin": "false",
    },
    {
        "member_id": "M0002",
        "display_name": "Linh",
        "email": "linh@company.com",
        "google_chat_user_name": "users/222",
        "is_admin": "false",
        "is_workspace_manager": "false",
    },
    {
        "member_id": "M0003",
        "display_name": "Manager",
        "email": "manager@company.com",
        "google_chat_user_name": "users/333",
        "is_admin": "false",
        "is_workspace_manager": "true",
    },
]

def test_default_subject_is_actor() -> None:
    actor = ChatActor("users/111", "Nam", "nam@company.com")
    assert resolve_subject_member_id("đặt Brazil thắng trận WC2026-0001", actor, MEMBERS) == "M0001"

def test_self_words_subject_is_actor() -> None:
    actor = ChatActor("users/111", "Nam", "nam@company.com")
    assert resolve_subject_member_id("xem điểm của mình", actor, MEMBERS) == "M0001"

def test_explicit_member_overrides_actor() -> None:
    actor = ChatActor("users/111", "Nam", "nam@company.com")
    assert resolve_subject_member_id("xem điểm của Linh", actor, MEMBERS) == "M0002"
    assert resolve_subject_member_id("xem điểm M0002", actor, MEMBERS) == "M0002"

def test_event_context_strips_bot_mention() -> None:
    event = {
        "user": {"name": "users/111", "displayName": "Nam", "email": "nam@company.com"},
        "message": {
            "text": "@SmileAI đặt tỷ số 2-1 trận WC2026-0001",
            "thread": {"name": "spaces/AAA/threads/BBB"},
            "createTime": "2026-05-31T01:00:00Z",
        },
        "space": {"name": "spaces/AAA"},
    }
    context = build_context(event, MEMBERS)
    assert context.subject_member_id == "M0001"
    assert context.text_without_bot_mention == "đặt tỷ số 2-1 trận WC2026-0001"
    assert context.space_name == "spaces/AAA"

def test_workspace_manager_is_manager() -> None:
    event = {
        "user": {"name": "users/333", "displayName": "Manager", "email": "manager@company.com"},
        "message": {"text": "@SmileAI nạp 50 point cho Nam", "thread": {}, "createTime": "2026-05-31T01:00:00Z"},
        "space": {"name": "spaces/AAA"},
    }
    assert build_context(event, MEMBERS).actor_is_manager is True

def test_space_manager_role_is_manager() -> None:
    event = {
        "user": {"name": "users/111", "displayName": "Nam", "email": "nam@company.com"},
        "message": {"text": "@SmileAI nạp 50 point cho Linh", "thread": {}, "createTime": "2026-05-31T01:00:00Z"},
        "space": {"name": "spaces/AAA"},
        "membership": {"role": "ROLE_MANAGER"},
    }
    assert build_context(event, MEMBERS).actor_is_manager is True

def main() -> int:
    tests = [
        test_default_subject_is_actor,
        test_self_words_subject_is_actor,
        test_explicit_member_overrides_actor,
        test_event_context_strips_bot_mention,
        test_workspace_manager_is_manager,
        test_space_manager_role_is_manager,
    ]
    failures = 0
    for test in tests:
        try:
            test()
        except Exception as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    print(f"summary: {len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
