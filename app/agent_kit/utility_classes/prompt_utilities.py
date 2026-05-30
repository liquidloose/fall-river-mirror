"""Reusable prompt snippets shared across agents."""

from typing import List

VIDEO_JUMP_LINK_CLASS = "video-jump-link"


def format_bracket_timestamp(seconds: int) -> str:
    """Format whole seconds as a bracketed video timestamp label."""
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
    return f"[{minutes:02d}:{secs:02d}]"


def inline_timestamp_link_prompt_lines() -> List[str]:
    """
    Return plain-English instructions for inline timestamp links.

    Intended for article-writing prompts that receive factual anchors with
    timestamp markers plus SOURCE LINK METADATA (youtube_id + URL template).
    """
    link_class = VIDEO_JUMP_LINK_CLASS
    example_href = "https://www.youtube.com/watch?v=jqPFjgUdotM&t=96s"
    example_label = format_bracket_timestamp(96)
    link_shape = (
        f'<a class="{link_class}" href="{example_href}" '
        f'aria-label="Jump to video at 01:36">{example_label}</a>'
    )
    return [
        "- For every factual anchor you use, include exactly one YouTube deep-link in that same sentence.",
        "- Each factual anchor line in ANCHOR CONTEXT includes a bracket timestamp (e.g. `[01:36]`) and a source_url= with the full watch URL.",
        "- Copy the href from the **same anchor line** whose facts that sentence cites — never borrow a source_url from a different anchor.",
        "- Copy the href from source_url exactly. The link's ONLY visible text is the bracket timestamp — never a word from the sentence.",
        f"- Link shape: `{link_shape}`.",
        f'- The visible link text must be the bracket timestamp from that anchor (e.g. `{example_label}`) — never "watch", never a name, never a number from the prose.',
        f'- Always include `class="{link_class}"` and an `aria-label` such as `Jump to video at 01:36` (time without brackets).',
        "- Place the link at the end of the cited sentence, immediately before the closing period.",
        "- Put exactly one ASCII space before the `<a>` tag so the timestamp is never glued to the previous word.",
        f"- GOOD: `The council approved the contract {link_shape}.`",
        "- NEVER wrap words, names, places, or phrases inside the link. The sentence words stay plain text; only the bracket timestamp is linked.",
        f'- BAD: `A plan to use the <a href=\"...\">Liberal Club</a> as a polling site.` (linked words inside the sentence).',
        f'- BAD: `{example_label} ...approved the contract.` (bare timestamp, not linked).',
        f'- BAD: `...approved the contract.{link_shape}` (period before the timestamp link).',
        f'- BAD: `...approved the contract{link_shape}.` (no space before the link).',
        "- Do not put timestamp links in headings, bullet lists, or a Summary section — only in `<p>` body paragraphs.",
        "- NEVER output `UNKNOWN` in a YouTube URL. Use the provided `youtube_id` from context metadata.",
        "- Do not emit bare bracket timestamps outside of a link; bracket times appear only inside `<a class=\"video-jump-link\">`.",
        "- Use one video jump link per anchor cited; reuse the same link only when the same anchor is cited again in a later sentence.",
    ]
