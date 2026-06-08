# Extraction pipeline — refactor reference

**Last surveyed:** 2026-05-25
**Scope:** `GemmaNye.extract()` and everything underneath it (`BaseExtractor`, `LLMTextQuery`).

## What this doc is

A snapshot of where the four-pass Gemini extraction actually does its work,
what the call chain looks like, and which pieces are duplication worth
collapsing vs. layering worth keeping. Read this before opening a refactor PR
on `app/agent_kit/agents/extractors/` or
`app/agent_kit/utility_classes/llm_text_query.py`.

**Pass-4 spell-check absorbed EditorAgent.** As of the four-pass cut,
`GemmaNye.extract()` runs a fourth Gemini pass (`spell_check`) that re-emits
the pass-2 anchors and pass-3 bullets with canonical Fall River spellings
applied. The canonical-names list is inlined into the pass-4 system
instructions; there is no longer a standalone `official_names.md` or
`official_names_loader` module. The legacy `EditorAgent` /
`/editor/spell-check*` HTTP surface has been removed in the same change —
spell-checking is now an extractor concern, not a post-hoc article fix.

Line numbers are accurate as of the date above; expect drift. The structural
claims should remain true even if specific lines shift — see the verification
checklist at the bottom.

## Where the LLM round-trip actually happens

One line — `client.models.generate_content(...)` inside
`gemini_generate_with_cache`:

`app/agent_kit/utility_classes/llm_text_query.py:388-392`

```python
response = client.models.generate_content(
    model=self.model_id,
    contents=turn_contents,
    config=types.GenerateContentConfig(**cfg_kwargs),
)
```

The fact-check *behavior* itself does not live in Python. It lives in:

- `app/agent_kit/agents/extractors/context_files/system_instructions/gemma_nye_fact_check_system_instructions.md`
- `app/agent_kit/agents/extractors/context_files/user_prompts/gemma_nye_fact_check_user_prompt.md`
- Plus the `draft_anchors_json` injection at `gemma_nye.py:305`.

The Python code never fact-checks anything; it ferries prompts to Gemini.

## Call chain (`extract()` to the SDK)

The transcript is cached once per extraction and reused by all four passes.
`extract()` owns the cache lifecycle (create once up front, delete once in a
`finally`); each pass only issues a generate against that shared cache,
folding its own system prompt into the user turn.

```
GemmaNye.extract                                  gemma_nye.py
  → BaseExtractor._create_extraction_cache        base_extractor.py   (once)
    → LLMTextQuery.gemini_create_cache            llm_text_query.py
  → _pass_extract / _pass_fact_check /            (each picks a pass-specific md pair
    _pass_bullets_and_committee /                  + injects whatever cross-pass payload
    _pass_spell_check                              that pass needs)
    → _run_pass_against_cache
      → BaseExtractor._call_cached_llm_and_parse  base_extractor.py
        → LLMTextQuery.gemini_generate_with_cache llm_text_query.py
          → client.models.generate_content        llm_text_query.py
  → BaseExtractor._delete_extraction_cache        base_extractor.py   (once, finally)
    → LLMTextQuery.gemini_delete_cache            llm_text_query.py
```

## Refactor targets (collapse these)

### 1. Merge `_call_llm_and_parse` and `_call_cached_llm_and_parse`

In `base_extractor.py`. They are ~80% the same code — envelope shape,
fence-strip, JSON parse, log write all duplicated. Collapse to one method with
a cached / non-cached strategy parameter, or split the LLM-call step from the
parse-and-log step and reuse parse-and-log across both paths.
Estimated savings: ~100 lines.

### 2. Declare passes as data, loop in `extract()`

`_pass_extract`, `_pass_fact_check`, `_pass_bullets_and_committee`, and
`_pass_spell_check` in `gemma_nye.py` are structurally identical. They
differ only in two prompt suffixes, a response schema, and a small set of
cross-pass injection keys. Express each pass as a record:

```python
PASSES = [
    PassSpec("extract",     ExtractEnvelope,     needs=()),
    PassSpec("fact_check",  FactCheckEnvelope,   needs=("draft_anchors_json",)),
    PassSpec("bullets",     BulletsAndCommittee, needs=("committee_list",)),
    PassSpec("spell_check", SpellCheckEnvelope,
             needs=("corrected_anchors_json", "bullets_json")),
]
```

Then loop in `extract()`. Adding a 5th pass becomes one row, not one method.

### 3. Pull `_render_named_user_prompt` up to `BaseExtractor`

`GemmaNye._render_named_user_prompt` duplicates `BaseExtractor._render_user_prompt`
— same code, just accepts a suffix. Add the suffix as an optional arg on the
base method and delete the GemmaNye copy.

### 4. Reconsider the SUBDIR + SUFFIX indirection

`SYSTEM_INSTRUCTION_SUBDIR` + `_FACT_CHECK_SYSTEM_SUFFIX` is heavy ceremony
when only one extractor uses it. Direct loaders
(`get_fact_check_system_instruction()`) would read cleaner.

**Trigger to keep the suffix machinery:** a second extractor lands that
genuinely shares the convention. Until then, the indirection costs more
than it saves.

## What NOT to collapse

`LLMTextQuery` → `BaseExtractor` → `GemmaNye` are three legitimately
different concerns:

- **`LLMTextQuery`** — provider SDK adapter. Knows Gemini cache create /
  generate / delete, xAI completion, Anthropic completion, HTTP shapes and
  API quirks (e.g. "Gemini rejects `system_instruction` on generate when
  `cached_content` is set").
- **`BaseExtractor`** — generic logged-call envelope. UUID `run_id`, JSON
  parse, per-pass log file under `logs/{youtube_id}/` (plus per-pass timing
  and token usage merged into `logs/{youtube_id}/metrics.json`, both via
  `app/agent_kit/utility_classes/run_logging.py`), error-envelope
  normalization. Reusable across any Gemini-based extractor.
- **`GemmaNye`** — agent-specific four-pass orchestration. Knows the
  *meaning* of "extract → fact-check → bullets-and-committee →
  spell-check" and the stitching between them.

Each hop does real work. Collapsing them would mix provider plumbing with
agent logic, which is exactly the trap to avoid as more extractors land.
**Refactor inside each box; don't refactor across boxes.**

## Estimated impact if all four targets land

- ~150–200 lines deleted.
- Adding a new extraction pass: from "write a 30-line method" to
  "add one `PassSpec` row".
- Adding a new non-Gemma extractor: unchanged (the layering is what makes
  that easy).
- Adding a new LLM provider: unchanged.

## How to verify this doc is still accurate

1. Open `gemma_nye.py` — confirm `_pass_extract`, `_pass_fact_check`,
   `_pass_bullets_and_committee`, and `_pass_spell_check` are still four
   structurally-identical methods.
2. Confirm `base_extractor.py` still has both `_call_llm_and_parse` and
   `_call_cached_llm_and_parse`.
3. Confirm `gemini_generate_with_cache` in `llm_text_query.py` is still
   where the SDK call lives.

If any of those is no longer true, this doc is stale — update or delete.
