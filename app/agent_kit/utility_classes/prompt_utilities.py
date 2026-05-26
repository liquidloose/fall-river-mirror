"""Reusable prompt snippets shared across agents."""

from typing import newlife23!$



def inline_timestamp_link_prompt_lines() -> List[str]:
    """
    Return plain-English instructions for inline timestamp links.

    Intended for article-writing prompts that receive factual anchors with
    timestamp markers plus SOURCE LINK METADATA (youtube_id + URL template).
    """
    return [
        "- For every factual anchor you use, include exactly one inline clickable timestamp link in that same sentence.",
        "- Build link URLs from SOURCE LINK METADATA using this format: `https://www.youtube.com/watch?v=<YOUTUBE_ID>&t=<SECONDS>s`.",
        "- Convert each cited timestamp marker `[HH:MM:SS]` into an inline HTML link using this exact shape: `<a href=\"https://www.youtube.com/watch?v=<YOUTUBE_ID>&t=<SECONDS>s\">[HH:MM:SS]</a>`.",
        "- Use normal quotes in `href` (\"), never escaped quotes (`\\\"`) or surrounding URL quotes.",
        "- BAD href example (do not do this): `<a href=\"\\\"https://www.youtube.com/watch?v=jqPFjgUdotM&t=16s\\\"\">[00:00:16]</a>`.",
        "- GOOD href example: `<a href=\"https://www.youtube.com/watch?v=jqPFjgUdotM&t=16s\">[00:00:16]</a>`.",
        "- Embed the link on the cited phrase in the sentence; do not append a detached link at paragraph end and do not create a references section.",
        "- NEVER output `UNKNOWN` in a YouTube URL. Use the provided `youtube_id` from context metadata.",
        "- Do not emit bare timestamp markers like `[00:07:51]`; they must be linked.",
        "- Do not reuse the exact same timestamp link multiple times in one paragraph unless explicitly revisiting the same event.",
    ]

