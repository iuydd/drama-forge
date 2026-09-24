# DramaForge / 爆剧引擎

[中文](README.md) · **English**

An agent skill for Claude Code, Codex, and similar tools that turns a premise into a complete, high-energy AI short drama with minimal human intervention.

DramaForge combines ideas distilled from six public short-drama skill sets with production scripts and 27 automated checks. The workflow runs from premise and episode beats through scripts, visual references, storyboards, keyframes, generated video, review, retakes, and final editing. See the [credits](#credits) for the source projects.

```text
Premise → series brief → episode beats → screenplay → visual assets → storyboard and frozen keyframes
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
S=~/.agents/skills/drama-forge/scripts
python3 $S/project_tool.py init <project-directory> --title "Title" --episodes 6 --dialogue-lang ja --genre 智斗复仇
python3 $S/project_tool.py next <project-directory>
```

Then ask your agent: “Use $drama-forge to make a complete short drama from this premise. Continue without asking me between stages and report the result.” `SKILL.md` defines the workflow; `references/pipeline-contract.md` defines the file formats and checks.

Existing projects retain the `short-drama-autopilot/*/v1` schema identifiers. The skill rename does not change project data formats.

## Contents

| Path | Purpose |
|---|---|
| `SKILL.md` | Agent entry point and stages A–J |
| `references/pipeline-contract.md` | Directory layout, IDs, JSON fields, 27 checks, and defaults |
| `references/story-engine.md` | Commercial short-drama story and payoff design |
| `references/screenplay.md` | Screenplay format, dialogue, pacing, and review |
| `references/visual-assets.md` | Character, location, prop, and continuity references |
| `references/storyboard-keyframes.md` | Shot planning and frozen keyframes |
| `references/video-prompts-h3.md` | H3 prompt structure, lip sync, performance, and camera movement |
| `references/production-and-review.md` | Production discipline, review, and retakes |
| `references/edit-and-delivery.md` | Editing, subtitles, sound, and delivery |
| `scripts/project_tool.py` | Initialize projects and inspect progress |
| `scripts/shots_tool.py` | Validate and render shots |
| `scripts/produce.py` | Generate references, opening frames, and videos |
| `scripts/review_tool.py` | Contact sheets, ASR, reports, and review marks |
| `scripts/cut.py` | ffmpeg editing |
| `scripts/h3_client.py` | Gateway client and job ledger |
| `scripts/selftest.py` | Offline end-to-end check |
| `assets/` | Project templates and a synthetic example |

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
