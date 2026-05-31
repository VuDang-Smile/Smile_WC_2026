from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


SELF_WORDS = {"toi", "tôi", "minh", "mình", "em", "anh", "chi", "chị", "me"}


@dataclass(frozen=True)
class ChatActor:
    user_name: str
    display_name: str
    email: str


@dataclass(frozen=True)
class ChatContext:
    actor: ChatActor
    subject_member_id: str | None
    actor_is_manager: bool
    text_without_bot_mention: str
    space_name: str
    thread_name: str
    create_time: str


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_bot_mention(text: str, bot_names: Iterable[str] = ("SmileAI", "smileai", "OpenClaw", "openclaw")) -> str:
    cleaned = text
    for name in bot_names:
        cleaned = re.sub(rf"@?{re.escape(name)}\b", " ", cleaned, flags=re.IGNORECASE)
    return normalize_text(cleaned)


def actor_from_event(event: dict[str, Any]) -> ChatActor:
    user = event.get("user", {}) or {}
    return ChatActor(
        user_name=user.get("name", ""),
        display_name=user.get("displayName", ""),
        email=user.get("email", ""),
    )


def build_context(event: dict[str, Any], members: list[dict[str, str]]) -> ChatContext:
    actor = actor_from_event(event)
    message = event.get("message", {}) or {}
    text = strip_bot_mention(message.get("text", ""))
    subject = resolve_subject_member_id(text, actor, members)
    space = event.get("space", {}) or {}
    thread = message.get("thread", {}) or {}
    return ChatContext(
        actor=actor,
        subject_member_id=subject,
        actor_is_manager=has_manager_permission(event, actor, members),
        text_without_bot_mention=text,
        space_name=space.get("name", ""),
        thread_name=thread.get("name", ""),
        create_time=message.get("createTime", ""),
    )


def resolve_subject_member_id(text: str, actor: ChatActor, members: list[dict[str, str]]) -> str | None:
    explicit = resolve_explicit_member(text, members)
    if explicit:
        return explicit
    if has_self_reference(text) or not mentions_member_like_text(text, members):
        return resolve_actor_member_id(actor, members)
    return None


def resolve_actor_member_id(actor: ChatActor, members: list[dict[str, str]]) -> str | None:
    for row in members:
        if actor.user_name and row.get("google_chat_user_name") == actor.user_name:
            return row.get("member_id") or None
    for row in members:
        if actor.email and row.get("email", "").lower() == actor.email.lower():
            return row.get("member_id") or None
    display_matches = [
        row for row in members
        if actor.display_name and row.get("display_name", "").lower() == actor.display_name.lower()
    ]
    if len(display_matches) == 1:
        return display_matches[0].get("member_id") or None
    return None


def resolve_explicit_member(text: str, members: list[dict[str, str]]) -> str | None:
    lowered = text.lower()
    member_id_match = re.search(r"\bM\d{4}\b", text, flags=re.IGNORECASE)
    if member_id_match:
        wanted = member_id_match.group(0).upper()
        if any(row.get("member_id") == wanted for row in members):
            return wanted

    mention_match = re.search(r"<users/([^>]+)>", text)
    if mention_match:
        user_name = f"users/{mention_match.group(1)}"
        for row in members:
            if row.get("google_chat_user_name") == user_name:
                return row.get("member_id") or None

    for row in members:
        email = row.get("email", "").lower()
        if email and email in lowered:
            return row.get("member_id") or None

    name_matches = [
        row for row in members
        if row.get("display_name") and re.search(rf"\b{re.escape(row['display_name'].lower())}\b", lowered)
    ]
    if len(name_matches) == 1:
        return name_matches[0].get("member_id") or None
    return None


def has_self_reference(text: str) -> bool:
    words = set(re.findall(r"[\wÀ-ỹ]+", text.lower()))
    return bool(words & SELF_WORDS)


def mentions_member_like_text(text: str, members: list[dict[str, str]]) -> bool:
    lowered = text.lower()
    if re.search(r"\bM\d{4}\b", text, flags=re.IGNORECASE):
        return True
    if re.search(r"<users/[^>]+>", text):
        return True
    return any(
        (row.get("email") and row["email"].lower() in lowered)
        or (row.get("display_name") and row["display_name"].lower() in lowered)
        for row in members
    )


def has_manager_permission(event: dict[str, Any], actor: ChatActor, members: list[dict[str, str]]) -> bool:
    actor_member_id = resolve_actor_member_id(actor, members)
    if actor_member_id:
        for row in members:
            if row.get("member_id") == actor_member_id:
                if is_truthy(row.get("is_admin", "")) or is_truthy(row.get("is_workspace_manager", "")):
                    return True

    membership = event.get("membership", {}) or {}
    role_candidates = [
        membership.get("role", ""),
        membership.get("memberRole", ""),
        membership.get("permission", ""),
    ]
    normalized_roles = {str(role).upper() for role in role_candidates if role}
    manager_roles = {"ROLE_MANAGER", "MANAGER", "OWNER", "ADMIN", "SPACE_MANAGER", "ROLE_ADMIN"}
    return bool(normalized_roles & manager_roles)


def is_truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}
