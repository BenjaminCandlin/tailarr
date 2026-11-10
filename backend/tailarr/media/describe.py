"""Friendly names for codecs, channel layouts, picture sizes and HDR formats.

The raw tools speak in codes ("A_TRUEHD", "dvhe.08", "SMPTE ST 2094 App 4");
the owner should see "Dolby TrueHD Atmos 7.1", "Dolby Vision profile 8.1" and
"HDR10+".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# -- video ---------------------------------------------------------------------

_VIDEO_CODECS = {
    "V_MPEGH/ISO/HEVC": "HEVC (H.265)",
    "V_MPEG4/ISO/AVC": "H.264 (AVC)",
    "V_AV1": "AV1",
    "V_VP9": "VP9",
    "V_VP8": "VP8",
    "V_MPEG2": "MPEG-2",
    "V_MPEG1": "MPEG-1",
    "V_MS/VFW/FOURCC": "Video for Windows",
    "V_MPEG4/ISO/ASP": "MPEG-4 (DivX/Xvid)",
    "V_MPEG4/ISO/SP": "MPEG-4",
    "V_REAL/RV40": "RealVideo",
    "V_THEORA": "Theora",
    "V_PRORES": "ProRes",
}
# mkvmerge's own codec names, for files that aren't MKV (MP4, AVI, ...).
_VIDEO_BY_NAME = (
    ("HEVC", "HEVC (H.265)"),
    ("H.265", "HEVC (H.265)"),
    ("AVC", "H.264 (AVC)"),
    ("H.264", "H.264 (AVC)"),
    ("AV1", "AV1"),
    ("VP9", "VP9"),
    ("MPEG-4p2", "MPEG-4 (DivX/Xvid)"),
    ("MPEG-1/2", "MPEG-2"),
    ("VC-1", "VC-1"),
)

# -- audio -------------------------------------------------------------------------

_AUDIO_CODECS = {
    "A_TRUEHD": "Dolby TrueHD",
    "A_MLP": "Dolby TrueHD",
    "A_EAC3": "Dolby Digital Plus",
    "A_AC3": "Dolby Digital",
    "A_AC3/BSID9": "Dolby Digital",
    "A_AC3/BSID10": "Dolby Digital",
    "A_DTS": "DTS",
    "A_DTS/EXPRESS": "DTS Express",
    "A_DTS/LOSSLESS": "DTS-HD Master Audio",
    "A_FLAC": "FLAC",
    "A_OPUS": "Opus",
    "A_VORBIS": "Vorbis",
    "A_MPEG/L3": "MP3",
    "A_MPEG/L2": "MP2",
    "A_MPEG/L1": "MP1",
    "A_PCM/INT/LIT": "PCM (uncompressed)",
    "A_PCM/INT/BIG": "PCM (uncompressed)",
    "A_PCM/FLOAT/IEEE": "PCM (uncompressed)",
    "A_ALAC": "ALAC (lossless)",
    "A_TTA1": "TTA (lossless)",
    "A_WAVPACK4": "WavPack (lossless)",
}
_AUDIO_BY_NAME = (
    ("TrueHD", "Dolby TrueHD"),
    ("MLP", "Dolby TrueHD"),
    ("E-AC-3", "Dolby Digital Plus"),
    ("AC-3", "Dolby Digital"),
    ("DTS-HD Master Audio", "DTS-HD Master Audio"),
    ("DTS-HD High Resolution", "DTS-HD High Resolution"),
    ("DTS-ES", "DTS-ES"),
    ("DTS", "DTS"),
    ("AAC", "AAC"),
    ("FLAC", "FLAC"),
    ("Opus", "Opus"),
    ("Vorbis", "Vorbis"),
    ("MP3", "MP3"),
    ("PCM", "PCM (uncompressed)"),
)

# -- subtitles ---------------------------------------------------------------------

# (friendly name, picture-based?)
_SUBTITLE_CODECS = {
    "S_TEXT/UTF8": ("SRT", False),
    "S_TEXT/ASCII": ("SRT", False),
    "S_TEXT/ASS": ("ASS (styled text)", False),
    "S_TEXT/SSA": ("SSA (styled text)", False),
    "S_ASS": ("ASS (styled text)", False),
    "S_SSA": ("SSA (styled text)", False),
    "S_TEXT/WEBVTT": ("WebVTT", False),
    "S_TEXT/USF": ("USF", False),
    "S_HDMV/PGS": ("PGS", True),
    "S_HDMV/TEXTST": ("Blu-ray text", False),
    "S_VOBSUB": ("VobSub", True),
    "S_DVBSUB": ("DVB", True),
    "S_KATE": ("Kate", False),
}


def _match_name(codec: str, table: tuple[tuple[str, str], ...]) -> str | None:
    for needle, friendly in table:
        if needle.lower() in codec.lower():
            return friendly
    return None


def video_codec_name(codec_id: str, codec: str) -> str:
    return _VIDEO_CODECS.get(codec_id) or _match_name(codec, _VIDEO_BY_NAME) or codec or "Unknown"


def subtitle_codec_name(codec_id: str, codec: str) -> tuple[str, bool]:
    """Returns (friendly name, picture-based?)."""
    if codec_id in _SUBTITLE_CODECS:
        return _SUBTITLE_CODECS[codec_id]
    lower = codec.lower()
    if "pgs" in lower:
        return "PGS", True
    if "vobsub" in lower:
        return "VobSub", True
    if "srt" in lower or "subrip" in lower:
        return "SRT", False
    if "ass" in lower or "ssa" in lower:
        return "ASS (styled text)", False
    if "webvtt" in lower:
        return "WebVTT", False
    if "timed text" in lower or "tx3g" in lower:
        return "MP4 text", False
    return codec or "Unknown", False


def audio_codec_name(
    codec_id: str, codec: str, commercial: str = "", features: str = "", fmt: str = ""
) -> str:
    """Name an audio codec, including Atmos and DTS:X when MediaInfo detects them.

    `commercial`, `features` and `fmt` are MediaInfo's Format_Commercial_IfAny,
    Format_AdditionalFeatures and Format.
    """
    base = codec_id.split("-")[0] if codec_id.startswith("A_AAC") else codec_id
    name = _AUDIO_CODECS.get(base)
    if base == "A_AAC" or codec_id.startswith("A_AAC"):
        name = "AAC"
    if name is None:
        name = _match_name(codec, _AUDIO_BY_NAME) or codec or "Unknown"
    if name in ("DTS", "DTS-ES"):
        # Plain "A_DTS" covers DTS, DTS-HD MA and DTS-HD HRA; mkvmerge's name tells them apart.
        name = _match_name(codec, _AUDIO_BY_NAME[4:8]) or name
    hint = f"{commercial} {features}"
    if "DTS" in name and ("DTS:X" in commercial or re.search(r"\bXLL X\b", features)):
        name = "DTS:X"
    if name in ("Dolby TrueHD", "Dolby Digital Plus") and (
        "Atmos" in commercial or "16-ch" in features or "JOC" in features
    ):
        name += " Atmos"
    if name == "AAC" and ("HE-AAC" in hint or "SBR" in features):
        name = "HE-AAC"
    if fmt == "MLP FBA" and "Dolby TrueHD" not in name:
        name = "Dolby TrueHD"
    return name


def channel_layout(channels: int | None, layout: str = "") -> str:
    """6 channels -> '5.1'; 2 -> 'Stereo'. Uses MediaInfo's layout to spot the LFE channel."""
    if not channels:
        return ""
    if channels == 1:
        return "Mono"
    if channels == 2:
        return "Stereo"
    if layout:
        lfe = sum(1 for part in layout.split() if part.upper().startswith("LFE"))
        if lfe and lfe < channels:
            return f"{channels - lfe}.{lfe}"
        if not lfe:
            return f"{channels}.0"
    defaults = {3: "2.1", 4: "4.0", 5: "5.0", 6: "5.1", 7: "6.1", 8: "7.1"}
    return defaults.get(channels, f"{channels} channels")


# -- picture size --------------------------------------------------------------------


def resolution_label(width: int | None, height: int | None) -> str | None:
    """Wide films are often cropped (3840×1600), so the width counts most."""
    if not width or not height:
        return None
    if width >= 3200 or height >= 2000:
        return "4K"
    if width >= 1800 or height >= 1000:
        return "1080p"
    if width >= 1200 or height >= 700:
        return "720p"
    if height >= 560:
        return "576p"
    if height >= 470:
        return "480p"
    return "SD"


# -- HDR ------------------------------------------------------------------------------

DV = "Dolby Vision"
HDR10 = "HDR10"
HDR10_PLUS = "HDR10+"
HLG = "HLG"


@dataclass
class HdrInfo:
    """What kind of HDR a video track has.

    `formats` lists every HDR format present, in the order Dolby Vision,
    HDR10+, HDR10, HLG. An empty list means SDR (normal picture).
    """

    formats: list[str] = field(default_factory=list)
    dv_profile: int | None = None
    dv_compatibility: int | None = None  # 1 = HDR10, 2 = SDR, 4 = HLG, 6 = Blu-ray (profile 7)
    dv_dual_layer: bool = False

    @property
    def dv_label(self) -> str | None:
        """'8.1', '7', '5'."""
        if self.dv_profile is None:
            return None
        if self.dv_profile == 8 and self.dv_compatibility in (1, 2, 4):
            return f"8.{self.dv_compatibility}"
        return str(self.dv_profile)

    @property
    def dv_fallback(self) -> str | None:
        """What players without Dolby Vision show: HDR10, SDR, HLG, or None (wrong colours)."""
        if self.dv_profile is None:
            return None
        if self.dv_profile == 5:
            return None
        if self.dv_profile == 7:
            return HDR10
        if self.dv_profile in (8, 10):
            return {1: HDR10, 2: "SDR", 4: HLG}.get(self.dv_compatibility or 0)
        if self.dv_profile in (4, 9):
            return "SDR"
        return None

    @property
    def can_remove_dv(self) -> bool:
        """Whether a 'copy without Dolby Vision' would leave a correct picture."""
        return self.dv_profile is not None and self.dv_fallback is not None


def _segments(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split("/")]


def detect_hdr(video: dict) -> HdrInfo:
    """Read HDR information from one MediaInfo video track (its JSON fields)."""
    formats = _segments(video.get("HDR_Format"))
    profiles = _segments(video.get("HDR_Format_Profile"))
    compat = _segments(video.get("HDR_Format_Compatibility"))
    settings = _segments(video.get("HDR_Format_Settings"))
    transfer = (video.get("transfer_characteristics") or "").upper()

    info = HdrInfo()
    has_dv = has_plus = has_hdr10 = has_hlg = False
    for i, fmt in enumerate(formats):
        profile = profiles[i] if i < len(profiles) else ""
        compatible = compat[i] if i < len(compat) else ""
        if fmt.startswith("Dolby Vision"):
            has_dv = True
            match = re.search(r"\.(\d+)", profile)
            if match:
                info.dv_profile = int(match.group(1))
            info.dv_compatibility = {
                "HDR10": 1,
                "SDR": 2,
                "HLG": 4,
                "Blu-ray": 6,
            }.get(compatible)
            # "BL+EL+RPU": a second (enhancement) video layer, as on UHD Blu-rays.
            info.dv_dual_layer = "EL+" in (settings[i] if i < len(settings) else "")
        elif "2094" in fmt or "HDR10+" in compatible:
            has_plus = True
        elif "2086" in fmt:
            has_hdr10 = True
        elif "HLG" in fmt:
            has_hlg = True
        if "HDR10+" in compatible:
            has_plus = True
        elif "HDR10" in compatible:
            has_hdr10 = True
    if transfer == "PQ" and not has_dv:
        has_hdr10 = True  # PQ without mastering metadata still plays as HDR10
    if transfer == "HLG" or "ARIB" in transfer:
        has_hlg = True
    if has_dv and info.dv_profile == 5:
        # Profile 5 has no HDR10 picture underneath: never call it HDR10.
        has_hdr10 = has_plus = False
    if has_dv and info.dv_profile == 8 and info.dv_compatibility is None and has_hdr10:
        info.dv_compatibility = 1
    if has_dv and info.dv_profile == 7 and info.dv_compatibility is None:
        info.dv_compatibility = 6
    if has_dv and info.dv_profile in (7, 8) and info.dv_compatibility in (1, 6):
        has_hdr10 = True
    if has_dv:
        info.formats.append(DV)
    if has_plus:
        info.formats.append(HDR10_PLUS)
    if has_hdr10:
        info.formats.append(HDR10)
    if has_hlg:
        info.formats.append(HLG)
    return info
