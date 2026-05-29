"""Tests for video jump link HTML repair."""

from app.agent_kit.utility_classes.video_jump_links import repair_video_jump_links


def test_repair_moves_word_wrapped_link_to_sentence_end():
    html = (
        '<p>A plan to use the <a class="video-jump-link" '
        'href="https://www.youtube.com/watch?v=abc&t=1577s">Liberal Club</a> '
        "as a polling site.</p>"
    )
    fixed = repair_video_jump_links(html)
    assert "Liberal Club as a polling site" in fixed
    assert fixed.endswith(
        '<a class="video-jump-link" href="https://www.youtube.com/watch?v=abc&t=1577s" '
        'aria-label="Jump to video at 26:17">[26:17]</a>.</p>'
    )
    assert fixed.count("video-jump-link") == 1


def test_repair_leaves_correct_bracket_link_untouched():
    html = (
        '<p>The board approved the motion '
        '<a class="video-jump-link" href="https://www.youtube.com/watch?v=abc&t=96s" '
        'aria-label="Jump to video at 01:36">[01:36]</a>.</p>'
    )
    assert repair_video_jump_links(html) == html
