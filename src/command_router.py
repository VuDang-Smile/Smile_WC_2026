from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.betting_service import BettingError, BettingService, CommandResult
from src.google_chat_context import build_context


@dataclass(frozen=True)
class RoutedReply:
    ok: bool
    message: str
    intent: str
    data: dict[str, Any]


class CommandRouter:
    def __init__(self, service: BettingService | None = None) -> None:
        self.service = service or BettingService()

    def handle_event(self, event: dict[str, Any], members: list[dict[str, str]]) -> RoutedReply:
        context = build_context(event, members)
        text = context.text_without_bot_mention

        try:
            if self._looks_like_balance(text):
                member_id = context.subject_member_id
                if not member_id:
                    raise BettingError("Không xác định được member để xem điểm.")
                result = self.service.show_balance(member_id)
                return self._ok(result)

            match_link = re.search(
                r"(?:link|sheet)(?:\s+(?:trận|tran))?\s+(WC2026-\d{4}|WC2026-FINAL)",
                text,
                flags=re.IGNORECASE,
            )
            if match_link:
                result = self.service.show_match_sheet_link(match_link.group(1).upper())
                return self._ok(result)

            settle_match = re.search(r"(?:settle|chốt kết quả|chot ket qua)\s+(?:trận\s+)?(WC2026-\d{4}|WC2026-FINAL)", text, flags=re.IGNORECASE)
            if settle_match:
                if not context.actor_is_manager:
                    raise BettingError("Quản lý space hoặc admin mới được settle trận.")
                result = self.service.settle_match(
                    match_id=settle_match.group(1).upper(),
                    admin_id=context.actor.user_name,
                )
                return self._ok(result)

            transfer_match = re.search(
                r"(?:chuyển|cho|tang|tặng)\s+(\d+)\s+point(?:\s+cho)?\s+(.+)",
                text,
                flags=re.IGNORECASE,
            )
            if transfer_match:
                actor_member_id = context.subject_member_id if context.subject_member_id == self._actor_member_id(members, context) else self._actor_member_id(members, context)
                target_member_id = self._resolve_target_member_id(transfer_match.group(2).strip(), members)
                if not actor_member_id:
                    raise BettingError("Không xác định được member gửi point.")
                if not target_member_id:
                    raise BettingError("Không xác định được member nhận point.")
                result = self.service.transfer_points(
                    from_member_id=actor_member_id,
                    to_member_id=target_member_id,
                    points=int(transfer_match.group(1)),
                    actor_member_id=actor_member_id,
                )
                return self._ok(result)

            score_match = re.search(r"đặt tỷ số\s+(\d+)\s*[-:]\s*(\d+)\s+trận\s+(WC2026-\d{4}|WC2026-FINAL)", text, flags=re.IGNORECASE)
            if score_match:
                member_id = context.subject_member_id
                if not member_id:
                    raise BettingError("Không xác định được member để đặt tỷ số.")
                result = self.service.place_score_bet(
                    member_id=member_id,
                    match_id=score_match.group(3).upper(),
                    home_score=int(score_match.group(1)),
                    away_score=int(score_match.group(2)),
                    ticket_count=1,
                )
                return self._ok(result)

            wdl_match = re.search(
                r"đặt\s+(?:(\d+)\s+vé\s+)?(.+?)\s+(thắng|hòa|hoa|draw|đội khách|doi khach|đội chủ nhà|doi chu nha)\s+trận\s+(WC2026-\d{4}|WC2026-FINAL)",
                text,
                flags=re.IGNORECASE,
            )
            if wdl_match:
                member_id = context.subject_member_id
                if not member_id:
                    raise BettingError("Không xác định được member để đặt cược.")
                ticket_count = int(wdl_match.group(1) or "1")
                team_or_side = (wdl_match.group(2) or "").strip()
                side_word = (wdl_match.group(3) or "").strip()
                pick = self._wdl_pick_from_phrase(team_or_side, side_word)
                result = self.service.place_wdl_bet(
                    member_id=member_id,
                    match_id=wdl_match.group(4).upper(),
                    pick=pick,
                    ticket_count=ticket_count,
                )
                return self._ok(result)

            return RoutedReply(False, "Chưa hiểu lệnh. Hiện hỗ trợ: xem điểm, link trận, đặt đội thắng, đặt tỷ số, settle trận.", "UNKNOWN", {"text": text})
        except BettingError as exc:
            return RoutedReply(False, str(exc), "ERROR", {"text": text})

    @staticmethod
    def _wdl_pick_from_phrase(team_or_side: str, side_word: str) -> str:
        side = side_word.casefold().strip()
        if side in {"hòa", "hoa", "draw"}:
            raise BettingError("Không được đặt Hòa. Chỉ đặt đội thắng: đội chủ nhà hoặc đội khách.")
        if side in {"đội khách", "doi khach"}:
            return "AWAY"
        if side in {"đội chủ nhà", "doi chu nha"}:
            return "HOME"
        if team_or_side.strip():
            return team_or_side.strip()
        raise BettingError("Không xác định được lựa chọn cược.")

    @staticmethod
    def _looks_like_balance(text: str) -> bool:
        lowered = text.casefold()
        return "xem điểm" in lowered or lowered.strip() in {"điểm", "balance"}

    @staticmethod
    def _ok(result: CommandResult) -> RoutedReply:
        return RoutedReply(True, result.reply_text, result.intent, result.data)

    @staticmethod
    def _actor_member_id(members: list[dict[str, str]], context: Any) -> str | None:
        actor = context.actor
        for row in members:
            if actor.user_name and row.get("google_chat_user_name") == actor.user_name:
                return row.get("member_id") or None
        for row in members:
            if actor.email and row.get("email", "").lower() == actor.email.lower():
                return row.get("member_id") or None
        return None

    @staticmethod
    def _resolve_target_member_id(raw_target: str, members: list[dict[str, str]]) -> str | None:
        target = raw_target.strip()
        member_id_match = re.search(r"\bM\d{4}\b", target, flags=re.IGNORECASE)
        if member_id_match:
            wanted = member_id_match.group(0).upper()
            if any(row.get("member_id") == wanted for row in members):
                return wanted
        mention_match = re.search(r"<users/([^>]+)>", target)
        if mention_match:
            user_name = f"users/{mention_match.group(1)}"
            for row in members:
                if row.get("google_chat_user_name") == user_name:
                    return row.get("member_id") or None
        lowered = target.lower()
        for row in members:
            if row.get("email", "").lower() == lowered:
                return row.get("member_id") or None
        display_matches = [
            row for row in members
            if row.get("display_name") and row.get("display_name", "").lower() == lowered
        ]
        if len(display_matches) == 1:
            return display_matches[0].get("member_id") or None
        return None
