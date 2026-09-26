# DramaForge / 爆剧引擎

[中文](README.md) · **English**

An agent skill for Claude Code, Codex, and similar tools that turns a premise into a complete, high-energy AI short drama with minimal human intervention.

DramaForge combines ideas distilled from six public short-drama skill sets with production scripts and the G00–G45 automated checks. It is a single skill that covers development (premise, genre cards, long-form series), adaptation (novels and multi-episode drafts), screenplay writing and revision, visual assets and reference-image prompts, storyboards and frozen keyframes, video prompts (H3, Seedance), production (the H3 gateway and official APIs, voice, music), review, retakes, editing, stage reviews, and multi-project oversight. The former eleven-skill short-drama suite has been merged into it. See the [credits](#credits) for the source projects.

```text
Premise (or novel / multi-episode draft → source analysis + adaptation contract) → series brief → episode beats → screenplay → visual assets → storyboard and frozen keyframes
→ opening frames → video → ASR, contact-sheet, and visual review → retakes → edited episode
```

Story and payoff take priority over image polish. Production runs one generation job at a time, keeps every take, and records decisions in the project log.

## Install

```bash
git clone https://github.com/iuydd/drama-forge.git ~/.agents/skills/drama-forge
ln -s ~/.agents/skills/drama-forge ~/.claude/skills/drama-forge   # Claude Code
python3 ~/.agents/skills/drama-forge/scripts/selftest.py          # Offline end-to-end check
```

Requirements: Python 3.10+, `requests`, `Pillow`, and ffmpeg/ffprobe. ASR review uses `faster-whisper`; set `ASR_PY` to a Python environment that has it installed.

Installation paths above are examples for the Claude environment; use the actual skill directory in other hosts. Offline tests skip ASR unless `SELFTEST_ASR=1` is explicitly set with a locally cached model. `python3 scripts/client_selftest.py` runs submission/recovery tests without media tools.

New projects leave generation profiles unset. Fill `drama.json.profiles` with the current project's accepted model/profile and resolution before production. The low-level CLI requires `--profile` and `--res`. Reconcile uncertain submissions before retrying; see [runtime boundaries and recovery](references/runtime-boundaries.md).

## Generation API

The scripts expect a self-hosted MiniMax H3 gateway. Set `H3_API` or `api_base` in `drama.json` for its address, and pass the token through `H3_STUDIO_TOKEN`. The token is read from the environment and is not saved to the project. The interface is implemented in `scripts/h3_client.py`:

| Endpoint | Purpose |
|---|---|
| `GET /api/status` | Check `running` and `queued` before submitting |
| `POST /api/v1/image` | Generate an image and return a job ID |
| `POST /api/v1/generate` | Generate a video from a keyframe and return a job ID |
| `GET /api/jobs/{id}` | Poll job status |
| `GET /api/jobs/{id}/image` or `/video` | Collect the result |

To use another generation service, adapt the four methods in `h3_client.py`. The other scripts rely on the submit, record, poll, and collect contract.

## Quick start

```bash
S="/actual/skill/path/drama-forge/scripts"
python3 "$S/project_tool.py" init <project-directory> --title "Title" --episodes 6 --dialogue-lang ja --genre 智斗复仇
python3 "$S/project_tool.py" next <project-directory>
```

Then ask your agent: “Use $drama-forge to make a complete short drama from this premise. Continue without asking me between stages and report the result.” `SKILL.md` defines the workflow; `references/pipeline-contract.md` defines the file formats and checks.

Existing projects retain the `short-drama-autopilot/*/v1` schema identifiers. The skill rename does not change project data formats.

## Contents

| Path | Purpose |
|---|---|
| `SKILL.md` | Agent entry point: hard rules, stages A0–J, and an index of deeper references |
| `references/pipeline-contract.md` | Directory layout, IDs, JSON fields, checks G00–G45, unnumbered lint scripts, and defaults |
| `references/runtime-boundaries.md` | Authorization scope, cost limits, and recovery of uncertain submissions |
| `references/market-hits.md`, `premise-novelty.md` | Market reference and premise novelty scoring |
| `references/story-engine.md` | Commercial short-drama story and payoff design |
| `references/genre-cards/` | Genre index and 12 genre cards |
| `references/series-long-form.md` | Long-form series and later seasons |
| `references/adaptation.md` | Novel analysis (stage A0), multi-episode draft intake, and the adaptation contract |
| `references/screenplay.md` | Screenplay format, normalization, dialogue, pacing, and revision passes |
| `references/visual-assets.md`, `image-prompts.md` | Character, location, prop, voice, and continuity references; reference-image prompts |
| `references/scene-state-and-reveal.md` | World facts, character knowledge, audience knowledge, and reveal planning |
| `references/storyboard-keyframes.md` | Shot planning and frozen keyframes |
| `references/video-prompts-general.md`, `video-prompts-h3.md`, `video-prompts-seedance.md` | Video prompt rules and model dialects |
| `references/providers.md` | Official API channels: MiniMax video, speech, and music; Seedance; GPT Image 2 |
| `references/production-and-review.md`, `quality-contract.md` | Production discipline, review, retakes, and review evidence |
| `references/edit-and-delivery.md` | Editing, subtitles, sound, color matching, and delivery |
| `references/styles.md` | Seven visual style presets, production-form cards, and system panel themes |
| `references/review-checklists.md` | Required review questions, severity levels, verdicts, and output format for every stage |
| `references/project-hub.md` | Multi-project overview, export, decision log, and rule priority |
| `scripts/project_tool.py` | Initialize projects and inspect progress |
| `scripts/shots_tool.py` | Validate and render shots |
| `scripts/produce.py`, `h3_client.py`, `providers.py` | Generation through the H3 gateway or official APIs, with a shared job ledger |
| `scripts/review_tool.py`, `review_quality.py` | Contact sheets, ASR, reports, review marks, and cut eligibility |
| `scripts/cut.py` | ffmpeg editing |
| `scripts/hub_tool.py` | Overview, export, delivery measurement, and color matching |
| `scripts/screenplay_lint.py`, `visual_lint.py`, `review_md_check.py` | Screenplay, prompt, and review-file lint |
| `scripts/novel_index.py`, `episode_intake.py` | Stable chapter and episode indexes for adaptation |
| `scripts/selftest.py`, `client_selftest.py`, `quality_selftest.py`, `merged_selftest.py` | Offline tests |
| `assets/` | Project templates, market data, and a synthetic example |

Offline tests:

```bash
python3 scripts/selftest.py            # end-to-end (ffmpeg/ffprobe, Pillow, requests; --no-media skips media)
python3 scripts/client_selftest.py     # submission and recovery
python3 scripts/quality_selftest.py    # review and cut contracts
python3 scripts/merged_selftest.py     # tools merged from the former suite; run one with merged_selftest.py <name>
```

## Credits

This skill distills and rewrites methods from these public projects. It does not copy their text verbatim.

| Project | License | Ideas used |
|---|---|---|
| short-drama eleven-skill suite | MIT | Rule priorities, H3 prompts, continuity, keyframes, story beats, and review |
| [eternityspring/shuohao-skills](https://github.com/eternityspring/shuohao-skills) | Apache-2.0 | Executable gates, payoff spacing, dialogue matching, and revision discipline |
| [doublesq97-ui/su-ai-short-drama](https://github.com/doublesq97-ui/su-ai-short-drama) | MIT | Payoff design, antagonist learning, episode functions, and handoffs |
| [CyberJ0605/cinematic-video-prompt-engineer-skill](https://github.com/CyberJ0605/cinematic-video-prompt-engineer-skill) | MIT | Expression timing, performance layers, and camera prompts |
| [s1dashu/director](https://github.com/s1dashu/director) | MIT | Job ledger, canary shot, and reference hierarchy |
| [POUND0423/AI-drama-pound](https://github.com/POUND0423/AI-drama-pound) | MIT | Failure-driven rules and review keep lists |

## License

MIT. See `LICENSE`.
