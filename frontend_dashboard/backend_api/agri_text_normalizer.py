from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextInterpretation:
    original: str
    normalized: str
    corrected: bool
    replacements: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "original": self.original,
            "normalized": self.normalized,
            "corrected": self.corrected,
            "replacements": [
                {"original": source, "normalized": target}
                for source, target in self.replacements
            ],
        }


_WATER_HOMOPHONE = re.compile(r"(?<!教我)([教交叫娇焦])([一1]下)?水(?!费|电|单|表)")
_VOICE_WATER_HOMOPHONE = re.compile(r"(?<!教我)([教交叫娇焦胶])([一1]下)?水(?!费|电|单|表)")

_ADHESIVE_CONTEXT_MARKERS = (
    "粘", "黏", "胶棒", "胶带", "强力胶", "固体胶", "热熔胶", "粘合剂", "固化", "脱胶",
    "胶水品牌", "胶水成分", "买胶水", "购买胶水", "胶水怎么用", "胶水是什么",
)
_AGRICULTURE_CONTEXT_MARKERS = (
    "农业", "农田", "温室", "大棚", "作物", "植物", "土壤", "苗", "秧", "叶", "花", "果",
    "番茄", "西红柿", "草莓", "黄瓜", "辣椒", "茄子", "玉米", "水稻", "小麦", "果树",
    "水泵", "水枪", "灌溉", "浇水", "施肥", "除草", "杀虫", "喷洒",
)


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _replace_literal(
    text: str,
    source: str,
    target: str,
    replacements: list[tuple[str, str]],
) -> str:
    if source not in text:
        return text
    count = text.count(source)
    replacements.extend((source, target) for _ in range(count))
    return text.replace(source, target)


def normalize_agri_text(text: str, *, voice_input: bool = False) -> TextInterpretation:
    """Correct high-confidence agriculture ASR homophones.

    The normalizer intentionally stays conservative.  It only rewrites a
    phrase when the surrounding characters make an agricultural interpretation
    highly likely. Voice transcripts receive a stronger agriculture bias because
    ASR commonly substitutes homophones; typed text remains conservative.
    """

    original = str(text or "").strip()
    if not original:
        return TextInterpretation(original=original, normalized=original, corrected=False)

    replacements: list[tuple[str, str]] = []

    def replace_water(match: re.Match[str]) -> str:
        source = match.group(0)
        middle = match.group(2) or ""
        target = f"浇{middle}水"
        replacements.append((source, target))
        return target

    water_pattern = _VOICE_WATER_HOMOPHONE if voice_input else _WATER_HOMOPHONE
    allow_glue_as_watering = voice_input and not _has_any(original, _ADHESIVE_CONTEXT_MARKERS)
    if allow_glue_as_watering:
        normalized = water_pattern.sub(replace_water, original)
    else:
        normalized = _WATER_HOMOPHONE.sub(replace_water, original)

    if voice_input:
        # These forms are either characteristic ASR substitutions or become
        # unambiguous inside an agricultural sentence.
        for source in ("罐盖", "罐概", "灌盖", "灌概"):
            normalized = _replace_literal(normalized, source, "灌溉", replacements)

        agriculture_context = _has_any(normalized, _AGRICULTURE_CONTEXT_MARKERS)
        action_frame = re.search(r"(?:给|对|向|往|帮|为).{1,12}(?:是非|施飞|湿非)", normalized)
        if agriculture_context or action_frame:
            for source in ("是非", "施飞", "湿非"):
                normalized = _replace_literal(normalized, source, "施肥", replacements)

        if agriculture_context or len(normalized) <= 6:
            normalized = _replace_literal(normalized, "喷谁", "喷水", replacements)

        normalized = _replace_literal(normalized, "土壤适度", "土壤湿度", replacements)
        normalized = _replace_literal(normalized, "空气适度", "空气湿度", replacements)
        normalized = _replace_literal(normalized, "环境适度", "环境湿度", replacements)
    return TextInterpretation(
        original=original,
        normalized=normalized,
        corrected=normalized != original,
        replacements=tuple(replacements),
    )
