"""Conservative matching of reviewed Skill packages to one current work segment.

The matcher is deliberately a pure routing boundary around the materializer's
cold-verified package view.  It never queries package tables or opens package
files itself, and it never lets model-authored data participate in the trusted
reuse reference.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any


MATCH_POLICY_VERSION = "skill_reuse_match.v1"
MATCH_BASIS_SCHEMA_VERSION = "skill_reuse_match_basis.v1"

_MAX_PACKAGES = 100
_PACKAGE_SENTINEL_LIMIT = _MAX_PACKAGES + 1
_MAX_SEGMENT_MESSAGES = 64
_MAX_MESSAGE_CHARS = 8_000
_MAX_SEGMENT_CHARS = 32_000
_MAX_ATTACHMENTS = 64
_MAX_FILENAME_CHARS = 512
_MAX_SKILL_REVISION_BYTES = 128_000
_MAX_SKILL_MARKDOWN_BYTES = 128_000
_MAX_IDENTIFIER_CHARS = 256
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SEMVER_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_REUSABLE_SUFFIX_RE = re.compile(
    r"\s*(?:[:：\-—]\s*)?(?:可复用方法|reusable\s+method)\s*$",
    flags=re.IGNORECASE,
)
_LATIN_TOKEN_RE = re.compile(r"[a-z0-9]+")
_REUSE_INTENT_VERB_RE = re.compile(
    r"复用|沿用|使用|采用|\b(?:reuse|reusing|use|using)\b"
)
_CHINESE_NEGATOR_SUFFIX_RE = re.compile(
    r"(?:不要再|不要|不再|别再|别|请勿|不得|严禁|禁止)\s*$"
)
_ENGLISH_NEGATOR_SUFFIX_RE = re.compile(
    r"(?:do\s+not|don\s+t|must\s+not|shall\s+not|never|stop|no|not)\s*$"
)
_GLOBAL_NO_REUSE_SCOPE_RE = re.compile(
    r"^\s*(?:(?:任何|任意|全部|所有)\s*)?"
    r"(?:已有|现有|既有|旧有|之前|过去)?\s*"
    r"(?:skill|skills|技能|方法|资产)\b"
    r"|^\s*(?:any|all)\s+(?:existing\s+|previous\s+|prior\s+)?"
    r"(?:skill|skills|method|methods)\b"
)
_EXPLICIT_POSITIVE_REUSE_VERBS = frozenset({"复用", "沿用", "reuse", "reusing"})
_LATIN_STOP_WORDS = frozenset(
    {
        "about",
        "analysis",
        "and",
        "assessment",
        "check",
        "create",
        "data",
        "document",
        "file",
        "for",
        "from",
        "generate",
        "guide",
        "method",
        "process",
        "report",
        "reusable",
        "skill",
        "system",
        "task",
        "the",
        "this",
        "use",
        "using",
        "with",
        "workflow",
    }
)


class SkillReuseMatcher:
    """Return at most one byte-verified, owner-scoped Skill reuse match."""

    def __init__(self, materializer: Any) -> None:
        self._materializer = materializer

    def match(
        self,
        conn: Any,
        *,
        username: str,
        segment_messages: Sequence[Mapping[str, Any]],
        attachment_filenames: Sequence[str] = (),
    ) -> dict[str, Any] | None:
        """Match only the supplied current work segment, failing closed.

        ``list_reuse_eligible`` is the trust seam: it owner-filters packages and
        cold-verifies their immutable bytes.  This method still checks the
        returned envelope defensively so an individual malformed item is merely
        skipped and cannot poison an otherwise unambiguous result.
        """

        normalized_username = _bounded_identity(username)
        basis = _match_basis(segment_messages, attachment_filenames)
        if normalized_username is None or basis is None:
            return None

        try:
            raw_items = self._materializer.list_reuse_eligible(
                conn,
                username=normalized_username,
                # Read one bounded sentinel beyond the usable population.  If
                # it exists, choosing among the first 100 could hide an equal
                # candidate and manufacture false uniqueness.
                limit=_PACKAGE_SENTINEL_LIMIT,
            )
        except Exception:
            # Package storage availability must never make Guide routing claim
            # a reuse that cannot be proven.  The caller can continue normally.
            return None
        if not isinstance(raw_items, (list, tuple)):
            return None
        if len(raw_items) >= _PACKAGE_SENTINEL_LIMIT:
            # More than the policy's bounded population needs a paginated,
            # global ambiguity proof.  Until that exists, reuse fails closed.
            return None

        ranked: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
        for raw_item in raw_items:
            try:
                trusted = _trusted_item(raw_item, username=normalized_username)
                if trusted is None:
                    continue
                if _latest_intent_negates(
                    trusted["core_title"], basis["user_messages"]
                ):
                    continue
                score = _match_score(
                    trusted["core_title"],
                    basis["search_text"],
                    basis["search_tokens"],
                )
                if score is not None:
                    ranked.append((score, trusted))
            except (TypeError, ValueError, UnicodeError, RecursionError):
                # A single stale or malformed package is not allowed to suppress
                # a different, fully verified package.
                continue

        if not ranked:
            return None
        best_score = max(score for score, _ in ranked)
        winners = [item for score, item in ranked if score == best_score]
        if len(winners) != 1:
            return None

        winner = winners[0]
        package = winner["package"]
        source = winner["source"]
        return {
            "ref": {
                "schema_version": "skill_reuse_ref.v1",
                "package_id": package["id"],
                "package_version": package["version"],
                "package_digest": package["package_digest"],
                "candidate_digest": source["candidate_digest"],
                "skill_digest": source["skill_digest"],
                "skill_name": winner["skill_name"],
                "matched_agent_id": winner["agent_id"],
                "review_state": "approved",
                "match_policy_version": MATCH_POLICY_VERSION,
                "match_basis_digest": basis["digest"],
            },
            "method": {
                "skill_revision": winner["skill_revision"],
                "skill_markdown": winner["skill_markdown"],
            },
        }


def _match_basis(
    segment_messages: Sequence[Mapping[str, Any]],
    attachment_filenames: Sequence[str],
) -> dict[str, Any] | None:
    if (
        not isinstance(segment_messages, (list, tuple))
        or len(segment_messages) > _MAX_SEGMENT_MESSAGES
        or not isinstance(attachment_filenames, (list, tuple))
        or len(attachment_filenames) > _MAX_ATTACHMENTS
    ):
        return None

    normalized_messages: list[str] = []
    total_chars = 0
    for message in segment_messages:
        if not isinstance(message, Mapping):
            return None
        role = message.get("role")
        if role != "user":
            continue
        content = message.get("content")
        if not isinstance(content, str) or len(content) > _MAX_MESSAGE_CHARS:
            return None
        normalized = _search_text(content)
        if not normalized:
            continue
        total_chars += len(normalized)
        if total_chars > _MAX_SEGMENT_CHARS:
            return None
        normalized_messages.append(normalized)

    normalized_filenames: list[str] = []
    for filename in attachment_filenames:
        if not isinstance(filename, str) or len(filename) > _MAX_FILENAME_CHARS:
            return None
        normalized = _search_text(filename)
        if normalized:
            normalized_filenames.append(normalized)
    # Attachment ordering is not semantically meaningful.  Sorting and
    # deduplicating prevents roster order from changing the evidence digest.
    normalized_filenames = sorted(set(normalized_filenames))

    if not normalized_messages and not normalized_filenames:
        return None
    digest_input = {
        "schema_version": MATCH_BASIS_SCHEMA_VERSION,
        "user_messages": normalized_messages,
        "attachment_filenames": normalized_filenames,
    }
    search_text = " ".join([*normalized_messages, *normalized_filenames])
    return {
        "digest": _digest(digest_input),
        "search_text": search_text,
        "search_tokens": frozenset(_LATIN_TOKEN_RE.findall(search_text)),
        "user_messages": tuple(normalized_messages),
    }


def _trusted_item(
    raw_item: Any,
    *,
    username: str,
) -> dict[str, Any] | None:
    if not isinstance(raw_item, Mapping):
        return None
    package = raw_item.get("package")
    revision = raw_item.get("skill_revision")
    markdown = raw_item.get("skill_markdown")
    if (
        not isinstance(package, Mapping)
        or not isinstance(revision, Mapping)
        or not isinstance(markdown, str)
    ):
        return None
    if package.get("state") != "approved" or package.get("reuse_eligible") is not True:
        return None

    source = package.get("source")
    if not isinstance(source, Mapping):
        return None
    owner = _bounded_identity(source.get("initiated_by_username"))
    if owner is None or owner != username:
        return None

    package_id = _bounded_text(package.get("id"), max_chars=_MAX_IDENTIFIER_CHARS)
    version = _bounded_text(package.get("version"), max_chars=64)
    package_digest = _required_digest(package.get("package_digest"))
    candidate_digest = _required_digest(source.get("candidate_digest"))
    skill_digest = _required_digest(source.get("skill_digest"))
    revision_digest = _required_digest(revision.get("content_digest"))
    agent_id = _bounded_text(
        source.get("agent_id", source.get("source_agent_id")),
        max_chars=_MAX_IDENTIFIER_CHARS,
    )
    skill_name = _bounded_text(revision.get("name"), max_chars=512)
    if (
        package_id is None
        or version is None
        or not _SEMVER_RE.fullmatch(version)
        or package_digest is None
        or candidate_digest is None
        or skill_digest is None
        or revision_digest != skill_digest
        or agent_id is None
        or skill_name is None
    ):
        return None

    if unicodedata.normalize("NFC", markdown) != markdown:
        return None
    if len(markdown.encode("utf-8")) > _MAX_SKILL_MARKDOWN_BYTES:
        return None
    try:
        canonical_revision = json.dumps(
            revision,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError):
        return None
    if len(canonical_revision.encode("utf-8")) > _MAX_SKILL_REVISION_BYTES:
        return None
    # JSON round-tripping gives the caller a bounded, detached value.  Neither a
    # model nor a later mutation of the materializer result can rewrite it.
    detached_revision = json.loads(canonical_revision)
    if not _is_nfc_json(detached_revision):
        return None

    core_title = _core_title(skill_name)
    if core_title is None:
        return None
    return {
        "package": {
            "id": package_id,
            "version": version,
            "package_digest": package_digest,
        },
        "source": {
            "candidate_digest": candidate_digest,
            "skill_digest": skill_digest,
        },
        "agent_id": agent_id,
        "skill_name": skill_name,
        "core_title": core_title,
        "skill_revision": detached_revision,
        "skill_markdown": markdown,
    }


def _match_score(
    core_title: str,
    search_text: str,
    search_tokens: frozenset[str],
) -> tuple[int, int, int] | None:
    han_count = sum("\u3400" <= char <= "\u9fff" for char in core_title)
    title_tokens = _distinctive_latin_tokens(core_title)
    if _contains_core_phrase(core_title, search_text):
        if han_count >= 4 or len(title_tokens) >= 2:
            # Exact title matches intentionally share one score.  If the work
            # segment names two reviewed methods, it is ambiguous rather than a
            # license to prefer the longer or newer package.
            return (2, 0, 0)

    if len(title_tokens) < 2:
        return None
    overlap = title_tokens.intersection(search_tokens)
    required = max(2, math.ceil(len(title_tokens) / 2))
    if len(overlap) < required:
        return None
    coverage = len(overlap) / len(title_tokens)
    return (1, len(overlap), round(coverage * 1_000))


def _contains_core_phrase(core_title: str, search_text: str) -> bool:
    if any("\u3400" <= char <= "\u9fff" for char in core_title):
        return core_title in search_text
    return f" {core_title} " in f" {search_text} "


def _latest_intent_negates(
    core_title: str,
    normalized_user_messages: Sequence[str],
) -> bool:
    """Honor the segment's last *explicit* reuse intent for this method.

    A no-reuse instruction persists across ordinary follow-up turns and title
    mentions (including attachment-name explanations).  Only a later explicit
    positive ``复用/沿用/reuse <title>`` clears it.  This prevents a later
    filename or generic “继续分析” from silently restoring reuse.
    """

    latest: bool | None = None  # True = positive reuse; False = no reuse.
    for message in normalized_user_messages:
        title_is_present = core_title in message
        for verb_match in _REUSE_INTENT_VERB_RE.finditer(message):
            verb = verb_match.group(0)
            prefix = message[max(0, verb_match.start() - 24) : verb_match.start()]
            negated = (
                _CHINESE_NEGATOR_SUFFIX_RE.search(prefix) is not None
                or _ENGLISH_NEGATOR_SUFFIX_RE.search(prefix) is not None
            )
            if negated:
                tail = message[verb_match.end() : verb_match.end() + 96]
                bare_global = not tail.strip()
                explicit_global = _GLOBAL_NO_REUSE_SCOPE_RE.search(tail) is not None
                if title_is_present or bare_global or explicit_global:
                    latest = False
                continue
            if verb in _EXPLICIT_POSITIVE_REUSE_VERBS and _positive_reuse_targets_title(
                message,
                verb_start=verb_match.start(),
                verb_end=verb_match.end(),
                core_title=core_title,
            ):
                latest = True
    return latest is False


def _positive_reuse_targets_title(
    message: str,
    *,
    verb_start: int,
    verb_end: int,
    core_title: str,
) -> bool:
    """Require an unambiguous title-bound positive reuse instruction."""

    after = message[verb_end : verb_end + len(core_title) + 32].lstrip()
    for qualifier in (
        "这个",
        "该",
        "这套",
        "已批准的",
        "已有的",
        "现有的",
        "the ",
        "this ",
        "approved ",
        "existing ",
    ):
        if after.startswith(qualifier):
            after = after[len(qualifier) :].lstrip()
            break
    if after.startswith(core_title):
        return True

    before = message[max(0, verb_start - len(core_title) - 32) : verb_start]
    return (
        re.search(
            re.escape(core_title)
            + r"\s*(?:现在|已经|可以|可|继续|仍可|仍然|还是|允许|can|may)?\s*$",
            before,
        )
        is not None
    )


def _distinctive_latin_tokens(value: str) -> frozenset[str]:
    return frozenset(
        token
        for token in _LATIN_TOKEN_RE.findall(value)
        if len(token) >= 3 and token not in _LATIN_STOP_WORDS
    )


def _core_title(value: str) -> str | None:
    without_suffix = _REUSABLE_SUFFIX_RE.sub("", value)
    normalized = _search_text(without_suffix)
    return normalized or None


def _search_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value).casefold()
    normalized_chars = [char if char.isalnum() else " " for char in value]
    return " ".join("".join(normalized_chars).split())


def _bounded_identity(value: Any) -> str | None:
    return _bounded_text(value, max_chars=128)


def _bounded_text(value: Any, *, max_chars: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized or len(normalized) > max_chars or "\x00" in normalized:
        return None
    return normalized


def _required_digest(value: Any) -> str | None:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        return None
    return value


def _is_nfc_json(value: Any) -> bool:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value) == value
    if isinstance(value, list):
        return all(_is_nfc_json(item) for item in value)
    if isinstance(value, dict):
        return all(
            _is_nfc_json(key) and _is_nfc_json(item) for key, item in value.items()
        )
    return value is None or isinstance(value, (bool, int, float))


def _digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"
