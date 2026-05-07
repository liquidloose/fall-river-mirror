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


def _normalize_for_substring_match(text: str) -> str:
    """
    Normalize text for tolerant substring matching: strip HTML tags, decode common
    entities, fold curly quotes / em-dashes to ASCII, lowercase, and collapse whitespace.

    Used to verify that a flag's ``problem_text`` actually appears verbatim in the article
    that was sent to the model -- the only reliable defense against the model fabricating
    a quote that isn't in the article.
    """
    if not text:
        return ""
    s = re.sub(r"<[^>]+>", " ", text)
    s = (
        s.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&#x27;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    s = (
        s.replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


FACT_CHECK_SYSTEM_PROMPT = """You are a senior media lawyer + journalism fact-checker reviewing a local-news article that summarizes a public meeting, for legal, ethical, and accuracy risks.

Your ONLY source of truth is the provided TRANSCRIPT (public record). Do NOT use external knowledge, prior articles, or assumptions.

IMPORTANT: The ARTICLE is a NEWS ARTICLE, not a verbatim transcript or stenographer's record. It is expected to read like real reporting — with scene-setting, narrative structure, synthesis paragraphs, and contextual or analytical framing that helps the reader understand what happened and why it matters. That kind of writing is normal and is NOT a flag on its own. Only flag editorial framing when it actually distorts what occurred, takes a side on a contested matter, attacks a named person, or invents facts.

The ARTICLE is provided in three parts: ARTICLE TITLE, ARTICLE CONTENT, and ARTICLE BULLET POINTS. Fact-check all three against the TRANSCRIPT (same criteria: factual accuracy, numbers, attribution, problematic language). Flags may refer to text from the title, the main content, or the bullet points. Always evaluate the ARTICLE TITLE for tone and emotional/inflammatory language; do not skip title checks when content or bullet points are long.

Tasks:
1. FACTUAL ACCURACY: Extract every factual claim, decision, vote, outcome, date, number, and especially every direct or paraphrased quote/speaker attribution in the ARTICLE (title, content, and bullet points).
   - Verify against TRANSCRIPT only.
   - Flag any incorrect information: wrong facts, wrong numbers, misattributed quotes, invented details, altered meaning, or quotes that do not appear or are materially different from the transcript.

2. PROBLEMATIC LANGUAGE: Check for tone, wording, or framing issues that could create legal or ethical risk (even if factually accurate).
   - Defamatory risk, inflammatory/emotionally loaded language about specific people, biased framing that favors or attacks a named party, privacy flags (as defined below).

Categories to flag (only if clearly present in the ARTICLE):
- factual_inaccuracy: Wrong info, erroneous quote, misattribution, invented detail, altered outcome/vote, fabricated specifics (numbers, dates, votes, names).
- defamatory: Statement that could harm a named person's or organization's reputation, presented as fact (not properly attributed) and not supported by the transcript.
- inflammatory: Words/phrases aimed at specific people that provoke or accuse without transcript support (e.g., "corrupt scheme," "blatant lie," "sham," "disgraceful conduct" applied to a named person when the transcript does not support that characterization).
- non_neutral: Editorializing that takes a SIDE on a contested matter, sarcasm aimed at participants, exaggerated value judgments about people or decisions ("a stunning betrayal," "the obviously wrong call"), or claims of motive that the transcript does not support. Do NOT flag synthesis, narrative framing, scene-setting, contextual paragraphs, or "broader implications"-style analysis as non_neutral merely because they go beyond the transcript's literal words.
- bias: Uneven treatment of named parties — favoring one side's arguments while suppressing or denigrating the other's, or applying loaded adjectives to one named person/group but not their counterparts in the same dispute.
- other: Privacy concerns or irrelevant personal details.

Rules:
- News-article framing is allowed: Analytical paragraphs, scene-setting, synthesis, contextual background, and observations about the gathering's tone or broader significance are normal news-writing devices. Do NOT flag them as long as they (a) do not contradict the transcript, (b) do not attribute motives or statements to specific people that the transcript does not support, and (c) do not take a side on a contested decision. Phrases like "the meeting underscored," "the gathering reflected," "broader implications," "the analytical lens reveals," or paragraphs that synthesize what speakers said are acceptable when grounded in what actually happened.
- TITLE: Do NOT flag the article title as inflammatory or non_neutral. If the transcript contains ANY heated discussion, emotional language, raised voices, dramatic moments, or strong reactions, a headline that reflects that (e.g. "Fiery Finale") is accurate — do NOT flag it. Only flag the title if the transcript is entirely calm and the title invents drama that is not in the transcript.
- Only add a flag when there is an actual error or risk. If the article's facts and attribution match the transcript, do NOT add a flag. Do not flag items "for awareness" or with "no change needed."
- Read the FULL article before flagging. If the article explicitly states the correct outcome elsewhere (e.g. that an item was "tabled," "rejected," or "deferred"), do NOT flag another paragraph as implying the opposite (e.g. approval). Do not flag "omissions" or "implications" that the article already corrects in another section.
- Fair report privilege applies: Accurate summaries of what was actually said/decided are protected — do NOT flag neutral paraphrases. If the TRANSCRIPT contains dramatic, metaphorical, or emotionally charged language, or describes heated debate, raised voices, or strong reactions (e.g. a speaker says "dumpster fire," "fiery," or gives an emotional speech), the article or its TITLE may reflect that tone; do NOT flag the title (or article) as inflammatory or non_neutral when it is accurately reflecting what occurred or was said in the meeting.
- NAMES ARE ENTIRELY OUT OF SCOPE. Do NOT flag any difference in how a person's, official's, or place's name is spelled or formatted between the ARTICLE and the TRANSCRIPT, regardless of category. This includes:
  - Different spellings of the same name (e.g. "Coogan" vs "Kugan", "Howlett" vs "Wulette", "Peckham" vs "Peekham").
  - Missing or added middle initials (e.g. "Christopher M. Peckham" vs "Chris Peekham").
  - Missing or added suffixes (Jr., Sr., II, III).
  - Missing or added titles or roles (Mayor, Councilor, Sergeant, etc.).
  - Full first name vs nickname (e.g. "Christopher" vs "Chris").
  The TRANSCRIPT is generated by YouTube auto-captions, which routinely mangle proper nouns; the ARTICLE'S spelling is the canonical version. NEVER reclassify a name difference as "factual_inaccuracy", "invented detail", "fabricated specifics", "altered detail", "invented specifics", or any other category — name handling is the spell-checker's job, not yours. The ONLY exception is misattribution: if the article attributes a quote, vote, or action to person A but the transcript clearly attributes it to a different person B, that IS "factual_inaccuracy" and should be flagged.
- Quotes: A quote is erroneous if the words, speaker, or meaning do not match the transcript (even slightly) — but ignore spelling differences in names when judging this.
- Be conservative: Neutral journalistic phrasing (e.g., "Councilor X said…", "The motion passed 5-2") gets a pass unless it misrepresents the transcript. Likewise, common news-feature devices (an opening scene, a closing reflection, a "what this means" paragraph) get a pass unless they invent facts or take a contested side.
- For every flag: Quote the exact problematic text from the ARTICLE, show the correct transcript evidence (or "no evidence"), explain the issue, suggest a fix, and provide the TIMESTAMP in the transcript or video where the relevant passage occurs (use the same format as in the transcript, or null if unavailable).
- VERBATIM QUOTING IS MANDATORY. The "problem_text" field MUST be a verbatim, copy-paste substring of the ARTICLE TITLE, ARTICLE CONTENT, or ARTICLE BULLET POINTS — same words, same order, same casing. Do NOT paraphrase, summarize, normalize, translate, or reconstruct the problem_text from the transcript or from your own memory. The transcript is auto-caption text and often differs from the article in ways that are not actually problems (e.g., transcript says "title wave" while article correctly says "Operation Desert Storm"); never put transcript text into problem_text.
- SELF-CHECK BEFORE EMITTING: For every flag you are about to include, locate the exact problem_text inside the ARTICLE you were given. If you cannot find it as a verbatim substring of the ARTICLE TITLE, ARTICLE CONTENT, or ARTICLE BULLET POINTS, DROP the flag entirely — do not output it, do not modify it, do not "approximate" it. A flag whose problem_text is not actually in the ARTICLE is a hallucination and is worse than no flag at all.

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

    def fact_check(
        self, article_id: int, scope: Literal["article", "bullet_points"] = "article"
    ) -> Dict[str, Any]:
        """
        Load article and its linked transcript from the local DB, send to AI for fact-check, return report.

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
            logger.warning(
                "Fact-check article has no linked transcript: article_id=%s", article_id
            )
            return {
                "success": False,
                "message": "Article has no linked transcript",
                "report": None,
            }
        transcript_row = self._db.get_transcript_by_id(transcript_id)
        if not transcript_row:
            logger.warning(
                "Fact-check transcript not found: transcript_id=%s", transcript_id
            )
            return {"success": False, "message": "Transcript not found", "report": None}
        transcript_content = (
            (transcript_row[3] or "").strip() if len(transcript_row) > 3 else ""
        )
        return self.fact_check_with_data(
            title=article.get("title") or "",
            content=article.get("content") or "",
            bullet_points=article.get("bullet_points") or "",
            transcript_content=transcript_content,
            scope=scope,
            log_label=f"article_id={article_id}",
        )

    def fact_check_with_data(
        self,
        title: str,
        content: str,
        bullet_points: str,
        transcript_content: str,
        scope: Literal["article", "bullet_points"] = "article",
        log_label: str = "<unknown>",
    ) -> Dict[str, Any]:
        """
        Run a fact-check using article + transcript data passed in directly.

        Use this when the article body lives outside the local DB (e.g. fetched from
        WordPress) but the transcript is available as a string. Behavior, prompt, and
        return shape match :meth:`fact_check`.

        Args:
            title: Article title.
            content: Article HTML/markdown body. Used when scope="article".
            bullet_points: Article bullet points. Used when scope="bullet_points".
            transcript_content: Full transcript text (the only ground truth).
            scope: "article" or "bullet_points".
            log_label: Free-form identifier for logs (e.g. "youtube_id=abc123").
        """
        article_title = (title or "").strip()
        article_content = content or ""
        article_bullet_points = bullet_points or ""
        transcript_text = (transcript_content or "").strip()
        if not transcript_text:
            logger.warning("Fact-check skipped, empty transcript: %s", log_label)
            return {"success": False, "message": "Transcript is empty", "report": None}
        if scope == "article":
            user_message = (
                f"TRANSCRIPT:\n{transcript_text}\n\n"
                f"ARTICLE TITLE:\n{article_title}\n\n"
                f"ARTICLE CONTENT:\n{article_content}\n\n"
                f"ARTICLE BULLET POINTS:\n(not provided)"
            )
            logger.info(
                "Fact-check calling AI (scope=article): %s, transcript_len=%s, title_len=%s, content_len=%s",
                log_label,
                len(transcript_text),
                len(article_title),
                len(article_content),
            )
        else:
            user_message = (
                f"TRANSCRIPT:\n{transcript_text}\n\n"
                f"ARTICLE TITLE:\n(not provided)\n\n"
                f"ARTICLE CONTENT:\n(not provided)\n\n"
                f"ARTICLE BULLET POINTS:\n{article_bullet_points}"
            )
            logger.info(
                "Fact-check calling AI (scope=bullet_points): %s, transcript_len=%s, bullet_points_len=%s",
                log_label,
                len(transcript_text),
                len(article_bullet_points),
            )
        try:
            out = self._xai.get_raw_response(FACT_CHECK_SYSTEM_PROMPT, user_message)
        except Exception as e:
            logger.exception("Fact-check AI request failed for %s", log_label)
            return {
                "success": False,
                "message": f"AI request failed: {e!s}",
                "report": None,
            }
        if isinstance(out, JSONResponse):
            try:
                body = out.body.decode("utf-8")
                err_payload = json.loads(body)
                err_msg = err_payload.get("error", body) or "Unknown error"
            except Exception:
                err_msg = "AI returned an error response"
            logger.warning("Fact-check AI error for %s: %s", log_label, err_msg)
            return {
                "success": False,
                "message": f"AI request failed: {err_msg}",
                "report": None,
            }
        raw = (out or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```\s*$", "", raw)
        try:
            report = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("Fact-check invalid JSON for %s: %s", log_label, e)
            return {
                "success": False,
                "message": f"Invalid JSON from AI: {e!s}",
                "report": None,
            }
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
            if "correct the spelling" in fix and (
                "match the transcript" in fix or "to match" in fix
            ):
                return True
            if (
                "misspell" in expl
                and "name" in expl
                and ("per instructions" in expl or "spelling" in expl)
            ):
                return True
            return False

        if scope == "article":
            haystack_raw = f"{article_title}\n{article_content}"
        else:
            haystack_raw = article_bullet_points
        haystack_normalized = _normalize_for_substring_match(haystack_raw)

        def is_hallucinated_problem_text(f: Dict[str, Any]) -> bool:
            """
            True when ``problem_text`` is not a verbatim substring of the article we
            actually sent to the model -- almost always a fabricated quote.
            """
            raw_needle = (f.get("problem_text") or "").strip()
            if not raw_needle:
                return False
            raw_needle = raw_needle.strip("\"'\u2018\u2019\u201c\u201d")
            needle = _normalize_for_substring_match(raw_needle)
            if not needle:
                return False
            return needle not in haystack_normalized

        kept: List[Dict[str, Any]] = []
        for f in flags:
            if not isinstance(f, dict):
                continue
            if is_no_change_flag(f) or is_name_spelling_only_flag(f):
                continue
            if is_hallucinated_problem_text(f):
                logger.warning(
                    "Fact-check dropping hallucinated flag for %s (problem_text not in article): %r",
                    log_label,
                    (f.get("problem_text") or "")[:160],
                )
                continue
            kept.append(f)
        flags = kept
        report["flags"] = flags
        report.setdefault("summary", "")
        logger.info(
            "Fact-check complete for %s: overall_risk=%s, flags_count=%s",
            log_label,
            report.get("overall_risk"),
            len(flags),
        )
        return {"success": True, "message": "Fact-check complete", "report": report}
