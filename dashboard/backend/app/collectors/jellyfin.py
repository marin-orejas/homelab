from __future__ import annotations

from typing import Any

from app.collectors.http import ServiceError, get_json

JellyfinError = ServiceError


def auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f'MediaBrowser Token="{api_key}"',
        "Accept": "application/json",
    }


def _transcode_summary(session: dict[str, Any]) -> dict[str, Any] | None:
    """Why is this stream being transcoded, and how hard."""
    info = session.get("TranscodingInfo")
    if not info:
        return None
    return {
        "reasons": info.get("TranscodeReasons", []),
        "is_video_direct": info.get("IsVideoDirect"),
        "is_audio_direct": info.get("IsAudioDirect"),
        "video_codec": info.get("VideoCodec"),
        "audio_codec": info.get("AudioCodec"),
        "container": info.get("Container"),
        "bitrate": info.get("Bitrate"),
        "framerate": info.get("Framerate"),
        "completion_percentage": info.get("CompletionPercentage"),
        "hardware_acceleration": info.get("HardwareAccelerationType"),
    }


def _format_session(session: dict[str, Any]) -> dict[str, Any]:
    item = session.get("NowPlayingItem") or {}
    play_state = session.get("PlayState") or {}

    runtime_ticks = item.get("RunTimeTicks")
    position_ticks = play_state.get("PositionTicks")
    progress = None
    if runtime_ticks and position_ticks is not None:
        progress = round(position_ticks / runtime_ticks * 100, 1)

    title = item.get("Name")
    if item.get("Type") == "Episode":
        parts = [item.get("SeriesName")]
        season, episode = item.get("ParentIndexNumber"), item.get("IndexNumber")
        if season is not None and episode is not None:
            parts.append(f"S{season:02d}E{episode:02d}")
        parts.append(item.get("Name"))
        title = " - ".join(p for p in parts if p)

    return {
        "session_id": session.get("Id"),
        "user": session.get("UserName"),
        "client": session.get("Client"),
        "device": session.get("DeviceName"),
        "remote_endpoint": session.get("RemoteEndPoint"),
        "item": {
            "title": title,
            "type": item.get("Type"),
            "year": item.get("ProductionYear"),
            "runtime_ticks": runtime_ticks,
        }
        if item
        else None,
        "play_state": {
            "is_paused": play_state.get("IsPaused"),
            "position_ticks": position_ticks,
            "progress_percent": progress,
            "play_method": play_state.get("PlayMethod"),
            "audio_stream_index": play_state.get("AudioStreamIndex"),
            "subtitle_stream_index": play_state.get("SubtitleStreamIndex"),
        },
        "transcoding": _transcode_summary(session),
    }


async def collect_sessions(
    base_url: str, api_key: str, timeout: float = 5.0
) -> dict[str, Any]:
    """Sessions that are actively playing something."""
    sessions = await get_json(
        f"{base_url.rstrip('/')}/Sessions",
        headers=auth_headers(api_key),
        params={"ActiveWithinSeconds": 300},
        timeout=timeout,
    )
    playing = [s for s in sessions if s.get("NowPlayingItem")]
    formatted = [_format_session(s) for s in playing]

    transcoding = sum(1 for s in formatted if s["transcoding"])
    return {
        "active_count": len(formatted),
        "transcoding_count": transcoding,
        "direct_play_count": len(formatted) - transcoding,
        "idle_client_count": len(sessions) - len(playing),
        "sessions": formatted,
    }


async def collect_library(
    base_url: str, api_key: str, timeout: float = 5.0
) -> dict[str, Any]:
    """Item counts plus basic server identity."""
    base = base_url.rstrip("/")
    headers = auth_headers(api_key)
    counts = await get_json(f"{base}/Items/Counts", headers=headers, timeout=timeout)
    info = await get_json(f"{base}/System/Info", headers=headers, timeout=timeout)

    return {
        "counts": {
            "movies": counts.get("MovieCount"),
            "series": counts.get("SeriesCount"),
            "episodes": counts.get("EpisodeCount"),
        },
        "server": {
            "name": info.get("ServerName"),
            "version": info.get("Version"),
            "has_pending_restart": info.get("HasPendingRestart"),
            "has_update_available": info.get("HasUpdateAvailable"),
        },
    }
