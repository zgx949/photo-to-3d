# photo-to-3d

[简体中文](README.md) · **English**

[![CI](https://github.com/zgx949/photo-to-3d/actions/workflows/ci.yml/badge.svg)](https://github.com/zgx949/photo-to-3d/actions/workflows/ci.yml)
[![GitHub Releases](https://img.shields.io/github/v/release/zgx949/photo-to-3d?label=release)](https://github.com/zgx949/photo-to-3d/releases)
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Turn one portrait into a stylized 3D character with an STL for slicing, a colored GLB, and a browser preview. The project ships as both an [Agent Skill](SKILL.md) and a Python CLI.

**Portrait → stylized reference → user approval → Seed3D generation → local mesh repair, color baking, and preview**

The skill guides the agent through checking the source photo, preserving recognizable features and pose, and showing the reference for approval before submitting a billable job. The CLI starts from a prepared reference image and can also post-process an existing model locally.

## Install the Agent Skill

Download `photo-to-3d.zip` from [GitHub Releases](https://github.com/zgx949/photo-to-3d/releases). Extract the whole `photo-to-3d/` directory into your agent’s skills directory. You can also clone the repository and put the checkout in the same location.

| Agent | User-level directory | Project-level directory |
| --- | --- | --- |
| Codex | `~/.agents/skills/photo-to-3d/` | `.agents/skills/photo-to-3d/` |
| Claude Code | `~/.claude/skills/photo-to-3d/` | `.claude/skills/photo-to-3d/` |

Keep `SKILL.md` alongside `scripts/`, `assets/`, and `references/`. For other compatible agents, follow the host’s skill-loading instructions. [Codex skills documentation](https://developers.openai.com/codex/skills) · [Claude Code skills documentation](https://code.claude.com/docs/en/skills)

Install the Python dependencies below in the environment where the agent runs scripts. Creating or querying Ark tasks requires an API key. You can post-process an existing model locally without one. Attach a photo and ask for something like “Turn this full-body photo into a chibi figurine. Show me the reference first, then generate an STL and a colored GLB after I approve it.” Preparing the reference requires image editing in the host, or you can supply a prepared reference. The agent can use the host’s segmentation tools when available.

## CLI quick start

### 1. Get the files and set up Python

For a source checkout, run the commands from the repository root. With a Release download, run the remaining commands from the extracted `photo-to-3d/` directory.

```bash
git clone https://github.com/zgx949/photo-to-3d.git
cd photo-to-3d
```

The core CLI, `scripts/ark_3d.py`, uses the standard library on Python 3.9 or later. For the full pipeline with solidification, use Python 3.11 or 3.12 and check that an Open3D wheel is available for your platform. [Open3D installation documentation](https://www.open3d.org/docs/0.19.0/getting_started.html)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-solidify.txt
```

| Task | Dependencies |
| --- | --- |
| Create, query, or download a generation task and check credentials | Python standard library |
| Scale and inspect meshes and bake colors | `requirements.txt` |
| Reconstruct and simplify a watertight mesh | `requirements.txt` and `requirements-solidify.txt` |
| Optional preview screenshot | `python -m pip install playwright`, followed by `python -m playwright install chromium` |

### 2. Configure your Ark API key

Create an Ark API key and enable Seed3D 2.0 in the model console. Ark bills generation tasks according to its terms. Reference-image preparation costs depend on your image service. [API key management](https://console.volcengine.com/ark/region:cn-beijing/apikey) · [Seed3D 2.0](https://console.volcengine.com/ark/region:cn-beijing/model/detail?name=doubao-seed3d-2-0) · [Ark 3D API](https://docs.volcengine.com/docs/ark/create-3d-generation-task-api)

Set `ARK_API_KEY` in the runtime environment or through your host’s secrets manager. You can also store the key on one line in `.ark_key` next to `SKILL.md` and run `chmod 600 .ark_key` on Unix. The core CLI looks for the global `--key` argument first, then `ARK_API_KEY`, then `.ark_key`. Keep the key on your machine or in a secrets manager.

```bash
printf 'Enter your Ark API key: '
IFS= read -r -s ARK_API_KEY
printf '\n'
export ARK_API_KEY
python scripts/ark_3d.py doctor
```

`doctor` checks credentials through the task-list endpoint without creating a generation task. For `401`, check your key. For `403`, check your account and model access.

### 3. Generate a model from an approved reference

Use a full-body reference with one subject and a clear silhouette. The CLI sends a local image, public image URL, or `data:` URI to Ark for processing. A PNG or JPEG with each side between 300 and 6,000 pixels, an aspect ratio of 0.4–2.5, and a file size under 30 MB works as input. [Full image constraints and generation parameters](references/ark-3d-api.md)

```bash
# Inspect the request without a key or a live submission
python scripts/ark_3d.py create --image ./cartoon-ref.png --dry-run

# Generate the model, repair the mesh, bake colors, and create the preview
python scripts/pipeline.py --image ./cartoon-ref.png --out ./out --name model
```

By default, the pipeline requests an `obj` at `high` detail and scales the repaired mesh to 150 mm with a target of about 600,000 faces. Use `--level medium` for a lower-detail Ark output and `--no-refine` for the faster local profile that targets about 250,000 faces. The scripts write JSON results to stdout and logs to stderr. Inspect `files` for actual output paths and `printable`, `watertight`, and `warnings` for mesh status.

| Output | Default directory | Use |
| --- | --- | --- |
| Source OBJ, MTL, and textures | `out/3d/` | Preserve the original materials or rerun local post-processing |
| Repaired OBJ and STL | `out/print/` | The STL is Z-up and rests on the build plane for inspection in a slicer |
| Vertex-colored OBJ and GLB | `out/color/` | Use GLB in Blender, browsers, and other 3D tools |
| HTML viewer and optional PNG | `out/preview/` | The HTML embeds the model and loads three.js over the network |

Color baking requires textures in the source model. Vertex color support varies by slicer. Check supports, thin walls, and dimensions in your slicer before printing.

## Common commands

```bash
# Generate and download the original GLB, with standard library only
python scripts/ark_3d.py run --image ./cartoon-ref.png --format glb --out ./out

# Query an existing task
python scripts/ark_3d.py status --task-id "TASK_ID"

# Rerun local post-processing on an existing textured OBJ or GLB
python scripts/pipeline.py --skip-3d ./mesh_textured_pbr.obj --out ./out --height 120

# Inspect dimensions and export an existing mesh without solidification dependencies
python scripts/pipeline.py --skip-3d ./mesh_textured_pbr.obj --out ./out --no-solidify --no-color
```

Use `create`, `status`, and `download` separately for asynchronous jobs, or `run` for all three. In download results, `path` points to the original download and `model_path` to the importable model. Save results before the temporary URL expires and keep OBJ files with their MTL files and textures.

```bash
python scripts/ark_3d.py --help
python scripts/pipeline.py --help
```

## Documentation and contributing

- [Skill instructions](SKILL.md) · [Identity and reference templates](references/identity-prompt.md) · [Example prompts](examples/prompts.md)
- [FAQ](docs/faq.md) · [Architecture](docs/architecture.md) · [Ark API reference](references/ark-3d-api.md)
- [Contributing and releasing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)

Run the following from a source checkout. CI checks require no Ark API key.

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
make test
make lint
make package
```

`make package` builds `dist/photo-to-3d.zip` and `dist/photo-to-3d.zip.sha256`. Push a `vX.Y.Z` tag matching the project and CLI versions. When checks pass, GitHub Actions attaches both files to a GitHub Release. [Release procedure](CONTRIBUTING.md#发布新版本)

## License

This community-maintained project is released under the [MIT License](LICENSE). Volcengine’s terms apply to Ark models and services.
