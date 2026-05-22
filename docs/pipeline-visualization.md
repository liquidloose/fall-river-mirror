# Pipeline visualization

This document visualizes the Fall River Mirror content pipeline end-to-end, with a deep dive into how the **extraction pass** pulls in data and where its output lives.

The main pipeline runs as **three sequential sections** against a shared SQLite store:

1. **Ingestion** — discover videos and pull transcripts into the `transcripts` table.
2. **Extraction** — turn each transcript into structured "anchor" rows via GemmaNye (4-pass Gemini).
3. **Content creation** — journalists, bullet points, art, and WordPress publish, fed by extraction output.

Extraction sits **between** ingestion and content creation: it consumes the raw transcript and produces the structured grounding that downstream content agents are designed to read from. The wiring that auto-chains these three sections inside `POST /pipeline/run` is not complete in code yet — today extraction is invoked manually via `POST /extract/anchors/{youtube_id}` — see [§5 Open seams](#5-open-seams).

---

## 1. End-to-end map (main pipeline)

```mermaid
flowchart LR
  subgraph ingest [1 · Ingestion]
    direction TB
    YT[YouTube channel]:::ext
    YT --> QM[VideoQueueManager<br/>queue_new_videos]
    QM --> CAP{captions on YouTube?<br/>_check_captions via<br/>youtube-transcript-api}
    CAP -->|yes| F1[transcript_available = 1]
    CAP -->|no| F0[transcript_available = 0<br/>Whisper required at fetch]
    F1 --> VQ[(video_queue)]
    F0 --> VQ
    VQ --> TM[TranscriptManager<br/>reads transcript_available flag<br/>→ youtube-transcript-api OR Whisper]
    TM --> TR[(transcripts)]
  end

  subgraph extract [2 · Extraction · GemmaNye 4-pass Gemini]
    direction TB
    P0[[Gemini CachedContent<br/>transcript + per-pass system instructions<br/>TTL 900s · created on entry to section 2]]:::cache
    P1[Pass 1 · extract<br/>schema: ExtractEnvelope<br/>→ draft factual_anchor_items]
    P2[Pass 2 · fact_check<br/>input: draft_anchors_json<br/>schema: FactCheckEnvelope<br/>→ verified anchors + removed_drafts]
    P3[Pass 3 · bullets + committee<br/>input: committee_list<br/>schema: BulletsAndCommittee<br/>→ executive_summary + primary_committee]
    AN[(anchors)]
    FCR[(fact_check_removals)]
    P1 -->|draft anchors| P2
    P2 -->|verified anchors| P3
    P2 ==>|doc_type=factual_anchor| AN
    P2 --> FCR
    P3 ==>|doc_type=executive_summary| AN
    AN -.->|embedded_at NULL<br/>no consumer yet| VS[(future vector store)]:::future
  end

  subgraph create [3 · Content creation]
    J[Journalist agent<br/>xAI Grok]
    J --> AR[(articles)]
    AR --> BP[AureliusStone<br/>bullet-points pass]
    BP --> AR
    AR --> IMG[FRA1 / SpectraVeritas<br/>image agent]
    IMG --> ART[(art)]
    ART --> WP[WordPressSyncService]:::ext
  end

  TR ==>|gemini cache| P0
  AN -. intended feed,<br/>not yet wired .-> J

  classDef ext fill:#0b3954,color:#fff,stroke:#0b3954
  classDef future fill:#f2f2f2,color:#666,stroke-dasharray: 4 4
  classDef cache fill:#fff4d6,color:#7a5a00,stroke:#7a5a00
```

**Hard stop**: if `run_bulk_fetch_transcripts` returns zero new transcripts, `/pipeline/run` short-circuits before any article/image/WP work (`app/routers/pipeline.py` ~L193).

---

## 2. Main pipeline — sequencing and gates

```mermaid
flowchart TD
  A[POST /pipeline/run] --> B{queue_mode}
  B -->|Use Whisper| C[run_build_queue<br/>YouTube Data API → video_queue]
  B -->|Skip Whisper| D[skip queue build]
  C --> E[run_bulk_fetch_transcripts<br/>video_queue ⊖ transcripts]
  D --> E
  E -->|0 fetched| STOP[/return success=false/]:::stop
  E -->|≥1 fetched| X[run_extract_anchors<br/>per new transcript<br/>GemmaNye 4-pass Gemini<br/>writes anchors + fact_check_removals]:::planned
  X --> F[run_bulk_write_articles<br/>transcripts ⊖ articles<br/>planned: read anchors as context]:::partplanned
  F --> G[run_bullet_points_batch<br/>articles WHERE bullet_points empty]
  G --> H[run_image_batch<br/>articles WITH bullets, no art row]
  H --> I{sync_to_wordpress?}
  I -->|yes| J[wordpress_sync_service.sync_one_article<br/>per new art]
  I -->|no| K[skip WP sync]

  classDef stop fill:#fde2e2,color:#a31919,stroke:#a31919
  classDef planned fill:#eef4ff,color:#0b3954,stroke:#0b3954,stroke-dasharray: 5 4
  classDef partplanned fill:#fffbe6,color:#7a5a00,stroke:#7a5a00,stroke-dasharray: 5 4
```

**Legend.** Solid boxes = wired in `/pipeline/run` today. Dashed blue box = step in the intended sequence that exists as a route (`POST /extract/anchors/{youtube_id}`) but is not yet auto-invoked by `/pipeline/run`. Dashed yellow box = step that runs today but is **partially** complete — it executes, but does not yet consume the upstream `anchors` rows it's meant to be grounded in.

**No central status column.** Each stage's eligibility is a SQL anti-join on the next table. Progress is implicit in which tables hold which rows for a given `youtube_id`.

| Stage | "Ready when…" | Code |
| --- | --- | --- |
| Queue | YouTube ID not in `transcripts` | `app/services/pipeline_service.py` ~L268 |
| Transcript | row in `video_queue`, not in `transcripts` | `~L307` |
| **Extraction** *(planned auto-invoke)* | `transcripts.content` non-empty for `youtube_id`; no `anchors` row for this run | `~L949` |
| Article | `transcripts` LEFT JOIN `articles` WHERE `a.id IS NULL` | `~L550` |
| Bullets | `articles.bullet_points` empty/null | `~L698` |
| Art | bullets non-empty, no `art.article_id` | `~L780` |
| WP sync | article has content + bullets + art; not on WP | `app/services/wordpress_sync_service.py` ~L656 |

---

## 3. Extraction pass — how it pulls in data

The extraction pass is `PipelineService.run_extract_anchors()` (`app/services/pipeline_service.py` ~L864) dispatching to `GemmaNye.extract()` (`app/agent_kit/agents/extractors/gemma_nye.py`).

### 3a. Data sources consumed

```mermaid
flowchart LR
  subgraph inputs [Inputs read at extract time]
    direction TB
    REQ[Path param<br/>youtube_id]
    TRC[(transcripts)<br/>content, yt_published_date]
    ENUM[Committee enum<br/>app/data/enum_classes.py]
    SI[System instructions .md<br/>extract / fact_check / bullets]
    UP[User prompts .md<br/>extract / fact_check / bullets]
    BIO[Bio + description .md<br/>identity context]
  end

  subgraph agent [GemmaNye agent]
    LOAD[load_transcript_for_youtube_id<br/>pipeline_service ~L949]
    META[meeting_date =<br/>yt_published_date 0..10]
    PROMPT[render user prompts<br/>youtube_video_id, meeting_date,<br/>draft_anchors_json, committee_list]
    CACHE[Gemini CachedContent<br/>TTL 900s, base_extractor ~L428]
  end

  REQ --> LOAD --> META
  TRC --> LOAD
  LOAD --> CACHE
  SI --> CACHE
  UP --> PROMPT
  BIO --> CACHE
  ENUM --> PROMPT
  PROMPT --> CACHE
```

**Not consumed:** WordPress posts, crawled pages, prior `anchors` rows, article bodies, external URLs at runtime. The agent works only from the SQLite transcript plus the prompt scaffolding bundled in the repo.

### 3b. Four-pass Gemini choreography

```mermaid
sequenceDiagram
  participant R as Router
  participant PS as PipelineService
  participant G as GemmaNye
  participant CC as Gemini CachedContent
  participant API as Gemini API
  participant AM as AnchorManager

  R->>PS: run_extract_anchors(youtube_id)
  PS->>PS: SELECT content, yt_published_date FROM transcripts
  PS->>G: extract(youtube_video_id, transcript, meeting_date)

  rect rgba(180,210,240,0.4)
    Note over G,CC: Pass 0 — cache create<br/>(transcript + per-pass system instructions)
    G->>CC: create_cache(transcript, system_instructions)
  end

  rect rgba(200,230,200,0.4)
    Note over G,API: Pass 1 — extract<br/>schema = ExtractEnvelope
    G->>API: generate(user_prompt, cached_content)
    API-->>G: factual_anchor_items (draft)
  end

  rect rgba(240,220,180,0.4)
    Note over G,API: Pass 2 — fact_check<br/>schema = FactCheckEnvelope
    G->>API: generate(user_prompt + draft_anchors_json)
    API-->>G: fact_checked items + removed_drafts
  end

  rect rgba(220,200,240,0.4)
    Note over G,API: Pass 3 — bullets + committee<br/>schema = BulletsAndCommittee
    G->>API: generate(user_prompt + committee_list)
    API-->>G: executive_summary_bullets + primary_committee
  end

  G->>G: stitch timestamp_seconds + text_to_embed
  G-->>PS: envelope{ run_id, success, data }
  PS->>AM: insert_from_envelope(envelope)
  AM->>AM: INSERT INTO anchors (factual_anchor rows)
  AM->>AM: INSERT INTO anchors (executive_summary rows)
  AM->>AM: INSERT INTO fact_check_removals
  AM-->>R: counts + run_id
```

Each pass writes a debug JSON to `logs/extractions/{ts}_yt{id}_r{run_id}_p{pass_label}.json` (`app/agent_kit/agents/extractors/base_extractor.py` ~L381). Re-extraction does **not** overwrite — it gets a fresh `run_id` UUID and appends.

### 3c. Output shape and persistence

```mermaid
flowchart LR
  subgraph env [GemmaNye envelope]
    FAI[factual_anchor_items&lbrack;&rbrack;<br/>timestamp_string, headline, text,<br/>has_official_vote, roll_call_type,<br/>fact_check_note, timestamp_seconds,<br/>text_to_embed]
    ESB[executive_summary_bullets&lbrack;&rbrack;<br/>5–8 strings]
    PC[primary_committee<br/>Committee enum value]
    RD[removed_drafts&lbrack;&rbrack;<br/>headline, text, removal_reason]
  end

  FAI -->|doc_type=factual_anchor| AT[(anchors)]
  ESB -->|doc_type=executive_summary| AT
  PC -.->|currently unused on insert| AT
  RD --> FCR[(fact_check_removals)]

  AT -. embedded_at NULL .-> VS[future vector store]:::future

  classDef future fill:#f2f2f2,color:#666,stroke-dasharray: 4 4
```

**`anchors` columns written** (`app/data/anchor_manager.py` ~L147):
`youtube_id, run_id, doc_type, timestamp_string, timestamp_seconds, anchor_headline, anchor_text, has_official_vote, roll_call_type, fact_check_note, text_to_embed, extractor_name, model, created_at`.

**Placeholder, never populated yet:** `embedded_at`, `embedding_id` (`app/data/create_database.py` ~L292) — these signal a planned vector-store push that has no producer in `app/` today.

---

## 4. Data sources & sinks at a glance

| Stage | Reads | Writes |
| --- | --- | --- |
| Queue build | YouTube Data API, `transcripts` | `video_queue` |
| Transcript fetch | `video_queue`, YouTube captions / Whisper | `transcripts`; DELETE `video_queue` |
| Article write | `transcripts`, `articles`, `journalists` | `articles` |
| Bullet points | `articles` | `articles.bullet_points` |
| Image batch | `articles`, `art` | `art` (binary PNG) |
| WordPress sync | `articles`, `transcripts`, `art`, `journalists` | WordPress REST (external) |
| **Extraction** | `transcripts`, Committee enum, prompt `.md` | `anchors`, `fact_check_removals` |
| Editor spell-check | `articles` | `articles.spell_checked`, optional WP |
| Editor fact-check | `articles` | read-only report (no writes) |

---

## 5. Open seams

The three-section design above is the target; the code wiring is partially there. These are the gaps that turn the intended sequence into the current reality:

- **Extraction is not yet chained inside `/pipeline/run`.** The intended order is ingestion → extraction → content creation, but today `/pipeline/run` jumps straight from transcript fetch to article writing. Extraction has to be triggered separately via `POST /extract/anchors/{youtube_id}`. Wiring it in between `run_bulk_fetch_transcripts` and `run_bulk_write_articles` is the missing link.
- **Content creation does not yet read from `anchors`.** Journalists currently consume raw `transcripts.content` (`app/services/pipeline_service.py` ~L613). The whole point of extraction is to feed them structured, fact-checked anchors and an executive summary instead — that consumer is the next thing to build.
- **No embedder.** `anchors.embedded_at` / `embedding_id` exist on the schema but nothing writes them. The Typesense index in the WordPress theme covers published articles, not anchor-level RAG.
- **No status column on `transcripts` / `articles`.** Progress is inferred from anti-joins, so a failed stage shows up as "row not yet present in the next table." Useful to know when debugging stuck items.

---

## Files referenced

- Orchestration: `app/services/pipeline_service.py`, `app/routers/pipeline.py`, `app/routers/extractions.py`
- Extraction agent: `app/agent_kit/agents/extractors/gemma_nye.py`, `base_extractor.py`, `schemas.py`
- Extraction context: `app/agent_kit/agents/extractors/context_files/{system_instructions,user_prompts,bios,descriptions}/`
- Persistence: `app/data/anchor_manager.py`, `app/data/create_database.py`, `app/data/transcript_manager.py`
- Sync: `app/services/wordpress_sync_service.py`
