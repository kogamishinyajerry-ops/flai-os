"""Closed server-side registry for promotable design asset slots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath


class TargetRegistryError(ValueError):
    pass


DEDICATED_PNG_TARGETS: dict[str, tuple[str, str]] = {
    "task_review_summary": (
        "open_design_task_review_summary_v1",
        "frontend/src/assets/open-design/task-review-summary.png",
    ),
    "agent_activity_indicator": (
        "open_design_agent_activity_indicator_v1",
        "frontend/src/assets/open-design/agent-activity-indicator.png",
    ),
    "workflow_monitor_sidebar": (
        "open_design_workflow_monitor_sidebar_v1",
        "frontend/src/assets/open-design/workflow-monitor-sidebar.png",
    ),
}


def validate_relative_png_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise TargetRegistryError("target path must be a nonempty POSIX relative path")
    if len(value) > 240 or "//" in value:
        raise TargetRegistryError("target path is outside the closed path bounds")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise TargetRegistryError("target path must be relative")
    if any(part in {"", ".", ".."} for part in posix.parts):
        raise TargetRegistryError("target path contains an unsafe segment")
    if posix.suffix.casefold() != ".png":
        raise TargetRegistryError("P2.8 v1 targets are PNG-only")
    return value


@dataclass(frozen=True)
class CurrentFrame:
    slot_id: str
    relative_path: str
    viewport_width: int
    viewport_height: int
    dpr: int
    state: str
    theme: str
    locale: str

    def __post_init__(self) -> None:
        if not self.slot_id or len(self.slot_id) > 128:
            raise TargetRegistryError("frame slot_id is invalid")
        validate_relative_png_path(self.relative_path)
        if not 1 <= self.viewport_width <= 4096 or not 1 <= self.viewport_height <= 4096:
            raise TargetRegistryError("frame viewport is outside the closed bounds")
        if not 1 <= self.dpr <= 4:
            raise TargetRegistryError("frame dpr is outside the closed bounds")
        if self.theme not in {"light", "dark"}:
            raise TargetRegistryError("frame theme is outside the allowlist")
        if not self.state or len(self.state) > 64 or not self.locale or len(self.locale) > 32:
            raise TargetRegistryError("frame state or locale is invalid")

    @property
    def matrix_key(self) -> tuple[object, ...]:
        return (
            self.slot_id,
            self.viewport_width,
            self.viewport_height,
            self.dpr,
            self.state,
            self.theme,
            self.locale,
        )


@dataclass(frozen=True)
class AssetTarget:
    target_id: str
    asset_slot: str
    relative_path: str
    frames: tuple[CurrentFrame, ...]

    def __post_init__(self) -> None:
        if not self.target_id or len(self.target_id) > 128:
            raise TargetRegistryError("target_id is invalid")
        if not self.asset_slot or len(self.asset_slot) > 128:
            raise TargetRegistryError("asset_slot is invalid")
        validate_relative_png_path(self.relative_path)
        expected = DEDICATED_PNG_TARGETS.get(self.asset_slot)
        if expected is None or expected != (self.target_id, self.relative_path):
            raise TargetRegistryError(
                "asset slot must use its dedicated server-owned PNG target"
            )
        if not self.frames:
            raise TargetRegistryError("target requires at least one current frame")
        keys = [frame.matrix_key for frame in self.frames]
        if len(set(keys)) != len(keys):
            raise TargetRegistryError("target has duplicate current-frame matrix keys")


class TargetRegistry:
    def __init__(self, targets: tuple[AssetTarget, ...] = ()) -> None:
        by_id: dict[str, AssetTarget] = {}
        by_slot: dict[str, AssetTarget] = {}
        for target in targets:
            if target.target_id in by_id or target.asset_slot in by_slot:
                raise TargetRegistryError("target ids and asset slots must be unique")
            by_id[target.target_id] = target
            by_slot[target.asset_slot] = target
        self._by_id = by_id
        self._by_slot = by_slot

    @property
    def targets(self) -> tuple[AssetTarget, ...]:
        return tuple(self._by_id.values())

    def by_slot(self, asset_slot: str) -> AssetTarget:
        try:
            return self._by_slot[asset_slot]
        except KeyError as exc:
            raise TargetRegistryError("asset slot is not server-allowlisted") from exc

    def by_id(self, target_id: str) -> AssetTarget:
        try:
            return self._by_id[target_id]
        except KeyError as exc:
            raise TargetRegistryError("target id is not server-allowlisted") from exc
