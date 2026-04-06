"""
Fact-check agent: compare article (or bullet points) to its linked transcript and return
a structured report on factual accuracy, numbers, and libel/defamation risk. No article edits.
"""
import json
import re
import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi.responses import JSONResponse

from app.content_department.creation_tools.xai_text_query import XAITextQuery

logger = logging.getLogger(__name__)


def _normalize_timestamp_to_hms(value: Any) -> Optional[str]:
    """Convert a timestamp string (e.g. M:SS, MM:SS, H:MM:SS, or seconds) to HH:MM:SS. Returns None for null/empty/invalid."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        total_sec = int(value)
        if total_sec < 0:
            return None
        h, r = divmod(total_sec, 3600)
        m, s = divmod(r, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    parts = s.split(":")
    try:
        if len(parts) == 1:
            total_sec = int(parts[0])
            if total_sec < 0:
                return None
            h, r = divmod(total_sec, 3600)
            m, sec = divmod(r, 60)
            return f"{h:02d}:{m:02d}:{sec:02d}"
        if len(parts) == 2:
            m, sec = int(parts[0]), int(parts[1])
            if m < 0 or sec < 0 or sec > 59:
                return s
            return f"00:{m:02d}:{sec:02d}"
        if len(parts) == 3:
            h, m, sec = int(parts[0]), int(parts[1]), int(parts[2])
            if h < 0 or m < 0 or sec < 0 or m > 59 or sec > 59:
                return s
            return f"{h:02d}:{m:02d}:{sec:02d}"
    except (ValueError, TypeError):
        pass
    return s if s else None

FACT_CHECK_SYSTEM_PROMPT = """You are a senior media lawyer + journalism fact-checker reviewing a local government meeting summary for legal, ethical, and accuracy risks.

Your ONLY source of truth is the provided TRANSCRIPT (public record). Do NOT use external knowledge, prior articles, or assumptions.

The ARTICLE is provided in three parts: ARTICLE TITLE, ARTICLE CONTENT, and ARTICLE BULLET POINTS. Fact-check all three against the TRANSCRIPT (same criteria: factual accuracy, numbers, attribution, problematic language). Flags may refer to text from the title, the main content, or the bullet points. Always evaluate the ARTICLE TITLE for tone and emotional/inflammatory language; do not skip title checks when content or bullet points are long.

Tasks:
1. FACTUAL ACCURACY: Extract every factual claim, decision, vote, outcome, date, number, and especially every direct or paraphrased quote/speaker attribution in the ARTICLE (title, content, and bullet points).
   - Verify against TRANSCRIPT only.
   - Flag any incorrect information: wrong facts, wrong numbers, misattributed quotes, invented details, altered meaning, or quotes that do not appear or are materially different from the transcript.

2. PROBLEMATIC LANGUAGE: Check for tone, wording, or framing issues that could create legal or ethical risk (even if factually accurate).
   - Defamatory risk, inflammatory/emotionally loaded language, non-neutral tone, bias indicators, privacy flags (as defined below).

Categories to flag (only if clearly present in the ARTICLE):
- factual_inaccuracy: Wrong info, erroneous quote, misattribution, invented detail, altered outcome/vote.
- defamatory: Statement that could harm reputation and is presented as fact (not properly attributed) or deviates from transcript.
- inflammatory: Words/phrases that provoke (outrageous, sham, disgraceful, blatant lie, corrupt scheme, etc.).
- non_neutral: Editorializing, sarcasm, exaggeration, value judgments.
- bias: Uneven framing or loaded adjectives favoring/opposing anyone.
- other: Privacy or irrelevant personal details.

Rules:
- TITLE: Do NOT flag the article title as inflammatory or non_neutral. If the transcript contains ANY heated discussion, emotional language, raised voices, dramatic moments, or strong reactions, a headline that reflects that (e.g. "Fiery Finale") is accurate — do NOT flag it. Only flag the title if the transcript is entirely calm and the title invents drama that is not in the transcript.
- Only add a flag when there is an actual error or risk. If the article's facts and attribution match the transcript, do NOT add a flag. Do not flag items "for awareness" or with "no change needed."
- Read the FULL article before flagging. If the article explicitly states the correct outcome elsewhere (e.g. that an item was "tabled," "rejected," or "deferred"), do NOT flag another paragraph as implying the opposite (e.g. approval). Do not flag "omissions" or "implications" that the article already corrects in another section.
- Fair report privilege applies: Accurate summaries of what was actually said/decided are protected — do NOT flag neutral paraphrases. If the TRANSCRIPT contains dramatic, metaphorical, or emotionally charged language, or describes heated debate, raised voices, or strong reactions (e.g. a speaker says "dumpster fire," "fiery," or gives an emotional speech), the article or its TITLE may reflect that tone; do NOT flag the title (or article) as inflammatory or non_neutral when it is accurately reflecting what occurred or was said in the meeting.
- Do NOT flag misspelled names (officials, people, places). Name spelling is out of scope and handled separately by spell-check. If the only difference between article and transcript is a name spelling, do not flag it.
- Quotes: A quote is erroneous if the words, speaker, or meaning do not match the transcript (even slightly) — but ignore spelling differences in names when judging this.
- Be conservative: Neutral journalistic phrasing (e.g., "Councilor X said…", "The motion passed 5-2") gets a pass unless it misrepresents the transcript.
- For every flag: Quote the exact problematic text from the ARTICLE, show the correct transcript evidence (or "no evidence"), explain the issue, suggest a fix, and provide the TIMESTAMP in the transcript or video where the relevant passage occurs (use the same format as in the transcript, or null if unavailable).

Output STRICT JSON only:
{"overall_risk": "LOW"|"MEDIUM"|"HIGH", "overall_status": "CLEAN"|"MINOR_ISSUES"|"CRITICAL_ISSUES", "flags": [{"category": "...", "problem_text": "...", "transcript_evidence": "...", "timestamp": "string or null", "explanation": "...", "severity": "low"|"medium"|"high", "suggested_fix": "..."}], "summary": "..."}
"""


class FactCheckAgent:
    """
    Fact-checks an article (or bullet points only) against its linked transcript.
    Returns an advisory report. Does not modify the article.
    """

    def __init__(self, db: Any) -> None:
        self._db = db
        self._xai = XAITextQuery()

    def fact_check(self, article_id: int, scope: Literal["article", "bullet_points"] = "article") -> Dict[str, Any]:
        """
        Load article and its linked transcript, send to AI for fact-check, return report.

        Args:
            article_id: Article to fact-check.
            scope: "article" = fact-check title + content only; "bullet_points" = fact-check bullet points only.

        Returns:
            Dict with success, message, report (parsed JSON). No DB or WordPress updates.
        """
        logger.info("Fact-check started for article_id=%s, scope=%s", article_id, scope)
        article = self._db.get_article_by_id(article_id)
        if not article:
            logger.warning("Fact-check article not found: article_id=%s", article_id)
            return {"success": False, "message": "Article not found", "report": None}
        transcript_id = article.get("transcript_id")
        if not transcript_id:
            logger.warning("Fact-check article has no linked transcript: article_id=%s", article_id)
            return {"success": False, "message": "Article has no linked transcript", "report": None}
        transcript_row = self._db.get_transcript_by_id(transcript_id)
        if not transcript_row:
            logger.warning("Fact-check transcript not found: transcript_id=%s", transcript_id)
            return {"success": False, "message": "Transcript not found", "report": None}
        transcript_content = (transcript_row[3] or "").strip() if len(transcript_row) > 3 else ""
        article_title = (article.get("title") or "").strip()
        article_content = article.get("content") or ""
        article_bullet_points = article.get("bullet_points") or ""
        if scope == "article":
            user_message = (
                f"TRANSCRIPT:\n{transcript_content}\n\n"
                f"ARTICLE TITLE:\n{article_title}\n\n"
                f"ARTICLE CONTENT:\n{article_content}\n\n"
                f"ARTICLE BULLET POINTS:\n(not provided)"
            )
            logger.info("Fact-check calling AI (scope=article): article_id=%s, transcript_len=%s, title_len=%s, content_len=%s", article_id, len(transcript_content), len(article_title), len(article_content))
        else:
            user_message = (
                f"TRANSCRIPT:\n{transcript_content}\n\n"
                f"ARTICLE TITLE:\n(not provided)\n\n"
                f"ARTICLE CONTENT:\n(not provided)\n\n"
                f"ARTICLE BULLET POINTS:\n{article_bullet_points}"
            )
            logger.info("Fact-check calling AI (scope=bullet_points): article_id=%s, transcript_len=%s, bullet_points_len=%s", article_id, len(transcript_content), len(article_bullet_points))
        try:
            out = self._xai.get_raw_response(FACT_CHECK_SYSTEM_PROMPT, user_message)
        except Exception as e:
            logger.exception("Fact-check AI request failed for article_id=%s", article_id)
            return {"success": False, "message": f"AI request failed: {e!s}", "report": None}
        if isinstance(out, JSONResponse):
            try:
                body = out.body.decode("utf-8")
                err_payload = json.loads(body)
                err_msg = err_payload.get("error", body) or "Unknown error"
            except Exception:
                err_msg = "AI returned an error response"
            logger.warning("Fact-check AI error for article_id=%s: %s", article_id, err_msg)
            return {"success": False, "message": f"AI request failed: {err_msg}", "report": None}
        raw = (out or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```\s*$", "", raw)
        try:
            report = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("Fact-check invalid JSON for article_id=%s: %s", article_id, e)
            return {"success": False, "message": f"Invalid JSON from AI: {e!s}", "report": None}
        report = {k: v for k, v in report.items() if k != "article_id"}
        report.setdefault("overall_risk", "LOW")
        report.setdefault("overall_status", "CLEAN")
        flags: List[Dict[str, Any]] = report.get("flags") or []
        if not isinstance(flags, list):
            flags = []
        for flag in flags:
            if isinstance(flag, dict):
                flag["timestamp"] = _normalize_timestamp_to_hms(flag.get("timestamp"))
        def is_no_change_flag(f: Dict[str, Any]) -> bool:
            fix = (f.get("suggested_fix") or "").strip().lower()
            expl = (f.get("explanation") or "").lower()
            if "no change needed" in fix:
                return True
            if "accurate" in expl and "no inaccuracies" in expl:
                return True
            if "accurate summary" in expl and "no change" in fix:
                return True
            return False
        def is_name_spelling_only_flag(f: Dict[str, Any]) -> bool:
            fix = (f.get("suggested_fix") or "").lower()
            expl = (f.get("explanation") or "").lower()
            if "correct the spelling" in fix and ("match the transcript" in fix or "to match" in fix):
                return True
            if "misspell" in expl and "name" in expl and ("per instructions" in expl or "spelling" in expl):
                return True
            return False
        flags = [f for f in flags if isinstance(f, dict) and not is_no_change_flag(f) and not is_name_spelling_only_flag(f)]
        report["flags"] = flags
        report.setdefault("summary", "")
        logger.info("Fact-check complete for article_id=%s: overall_risk=%s, flags_count=%s", article_id, report.get("overall_risk"), len(flags))
        return {"success": True, "message": "Fact-check complete", "report": report}
