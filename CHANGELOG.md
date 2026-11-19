# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本。

## [Unreleased]

### Added
- 分层依赖清单：`requirements.txt`（轻量后处理）、`requirements-solidify.txt`（实体修复 / 减面）、`requirements-dev.txt`（开发工具链）；`pyproject.toml` 补充项目元数据与 `light` / `solidify` / `preview` / `dev` 可选依赖分组。
- 中英文 README、Codex 与 Claude Code 安装说明，以及 GitHub 版本发布指引。中文为默认入口。
- CI 打包校验与实体修复测试。推送匹配版本的 `vX.Y.Z` 标签后，检查通过会自动发布 Skill ZIP 和 SHA-256 校验文件。

### Changed
- 合并 `ark_3d.py` 中重复定义的 `MODEL_EXTS` 白名单（保留完整后缀，含 `.gltf`）。
- Skill 使用宿主提供的图像编辑与文件展示能力，凭据通过本地环境或密钥管理配置，保留付费生成前的参考图确认步骤。

### Fixed
- CI 使用支持 Python 3.9 的 Ubuntu 24.04，补齐 SciPy、NetworkX 依赖，并为 Python 3.9 选择兼容的减面依赖版本。
- 付费生成前检查本地打印处理依赖。修复下载根目录下的 OBJ 与配套贴图、取消任务后的轮询、网格朝上轴及落地。`doctor` 用任务列表接口验证凭据。
- 预览截图识别 Playwright 安装的 Chromium，HTML 预览正确转义标题和说明。
- 泊松重建使用单线程，规避 Open3D 并行重建中出现的原生崩溃。

## [0.2.9] - 2026-11-19

### Added
- **本地高精度修复档**（`pipeline.py` 默认开启）：方舟只出初版模型，精修在本地完成。
  - `print_prep.py --focus-head`：顶部比例区域内加密采样（默认 0.6× 额外点），脸与头发不被泊松平滑抹掉；实测在 512k 面输入上追加 480,000 个头部采样点。
  - `bake_color.py --sharpen-head`：脸部高度带 + 亮度下限内的顶点色反锐化，只提眼眉、唇线、鼻影，**不碰头发与深色边缘**（整段锐化会把头发压成死黑，已在实测中修正）。
  - 修复档参数：采样 80 万、泊松 depth 10、成品 60 万面、头部加密 0.22、面部锐化 0.22；`--no-refine` 回快档（68 秒）。
- 单测：头发（暗部）在锐化中保持原值，只有脸部顶点被改动。

### Changed
- 实测修复档后处理 3 分 12 秒（补实体 110 s + 上色 34 s + 预览 48 s），可打印件 599,988 面、水密、`printable: true`、体积 117 cm³；最近点误差 0.008 mm。
- SKILL 第 5 步改写为「本地高精度修复」，写明几何/颜色两处参数与「不想变慢就用 --no-refine」。

## [0.2.8] - 2026-11-18

### Changed
- 精细度默认值从 `medium`（50 万面）提到 `high`（100 万面）：`ark_3d.py --level`、`pipeline.py --level`、SKILL 第 4 步、README 参数表、`references/ark-3d-api.md` 请求体示例同步。
- SKILL 明确 `high` 的代价：obj 包体约大一倍、生成多等 2–4 分钟；打印链路仍简化到 25 万面，高精细度主要提升彩色版与预览。

## [0.2.7] - 2026-11-18

### Changed
- 生成阶段默认格式从 `glb` 改为 `obj`（`ark_3d.py --format` 默认值、SKILL 第 4 步、README 参数表与 `references/ark-3d-api.md` 同步）。obj 包自带 mtl 与贴图，补实体与上色直接可用；不再为了预览额外向方舟要一份 glb，glb 只在上色步骤本地导出。

## [0.2.6] - 2026-11-18

### Added
- `scripts/make_preview.py` + `assets/viewer.template.html`：把彩色 glb 包成**单文件 3D 查看器**（glb 以 base64 内联，双击即开，可旋转/缩放/线框/复位/下载），并在环境有 chromium + playwright 时顺手截一张预览图。
- `pipeline.py` 增加第 4 步「生成 3D 预览」，汇总 JSON 多出 `preview_html` / `preview_png`；`--no-preview` 可跳过。实测预览 38 秒，整链约 76 秒（不含 3D 任务）。
- `SKILL.md` 交付顺序改为**先预览后文件**：先交 `/预览.html`（点开即看），预览图用 RichMediaCard 内联，再交 obj/stl/glb。

### Changed
- 查看器文案改为动态：标题用模型名，说明默认通用文案，`--summary` 可注入尺寸/面数/是否可打印的实况。

## [0.2.5] - 2026-11-18

### Added
- `scripts/pipeline.py`：整条链路的编排入口。`--image` 跑「方舟出 obj → 补实体 → 上色」，默认交付四件（可打印 obj/stl、彩色 obj/glb）；`--skip-3d` 复用已有模型只补后续步骤，不重新计费。实测后处理 68 秒（补实体 50 s + 上色 18 s）。
- 单测新增 pipeline 串联用例（`--skip-3d --no-solidify --no-color`，离线可跑）。

### Fixed
- `bake_color.py` 支持 glb：贴图从 PBR 材质的 `baseColorTexture` 取（此前只认 obj 的 `material.image`，遇到只有 glb 的用户会直接失败）。
- `pipeline.py` 上色失败不再中断整条链路，改为降级交付素模并在 `warnings` 说明原因与补救路径。
- 实测：只有 glb 时 `--skip-3d figure-3d.glb` 也能跑出可打印件与彩色版，38 秒完成（补实体 23 s + 上色 15 s）。

### Changed
- `SKILL.md` 第 4 步默认改为 `pipeline.py`，并明确「不要只跑 glb」；第 5/6 步降级为分步重跑与参数细节；交付章节改为默认四件一起给。
- `README` 快速开始改用 `pipeline.py`，CLI 参考补 pipeline 说明。

## [0.2.4] - 2026-11-18

### Added
- `references/identity-prompt.md`：相似度控制专项。人物分割命令与返回字段、身份特征表（9 类字段 + 3 个识别锚点）、姿势还原规则、三套提示词模板（保姿势 / 指定动作 / 只修脸）、五项验收清单、六类边界情况（挡脸、侧脸、半身、合影、逆光）。
- `SKILL.md` 第 2 步重写为 2.1 分割 → 2.2 特征表 → 2.3 出图（默认还原原片姿势）→ 2.4 并排验收；遮挡面部时改为先问用户，不再默默改姿势。
- 第 3 步确认环节要求把「抠图后的原片 + 参考图」一起给用户看，用户说不像就回 2.4，不允许带着不像的脸建模。

### Changed
- `README` 增加「怎么保证像本人」四步说明，目录树补 `identity-prompt.md`。
- `docs/faq.md` 第 5 题改为指向新流程。

## [0.2.3] - 2026-11-18

### Changed
- `SKILL.md` 结构调整为「五步主链 + 两个可选收尾」：打印（第 5 步）、上色（第 6 步）、交付（第 7 步），打印常识并入打印小节，编号不再出现 5.5。
- `SKILL.md` 前置条件补齐开通与实名入口（模型详情页「快速接入」、实名认证页、Key 页），并写明 403 / `ModelNotOpen` 的处置。
- `references/ark-3d-api.md` 补 obj 包结构（obj + mtl + textures）、实测体量与耗时、开通链接与错误码。
- `README` 更新测试数（36 条）、skill 目录树与仓库目录树、实测耗时（glb 6 分 20 秒 / obj 3 分半）、开通入口直链。
- `docs/faq.md` 新增三条真实高频问题：满身裂纹打不出来、obj 打开是白的、彩色模型能否直接打印。
- `docs/architecture.md` 流程图补打印与上色两条可选分支。
- CI 装轻量依赖（trimesh / numpy / pillow / rtree），并检查三个脚本都在位。
- `ark_3d.py` 版本号对齐 0.2.3。

## [0.2.2] - 2026-11-18

### Added
- `scripts/bake_color.py`：把原始贴图的颜色搬回补实体后的网格。最近点 → 重心坐标 → UV → 采样贴图，写成顶点色，再两轮邻域去斑。输出 `-彩色.obj`（Z-up）与 `-彩色.glb`（Y-up 预览）。
- 单测增至 36 条（新增 bake_color 纯色贴图还原测试，缺依赖时跳过）。

### Notes
- 补实体丢 UV 是必然的，颜色必须二次烘焙；这不是 bug。
- 顶点色在切片软件里支持不一致，打印上色仍以分件换色 / 后期手涂为准。

## [0.2.1] - 2026-11-18

### Added
- `print_prep.py --solidify`：把开口壳体补成可打印的封闭实体。链路是「有向点云 → Open3D 泊松重建 → 二次误差减面 → pymeshfix 清残余非流形边」。实测 500,000 面的 obj：87,699 条开放边 / 1,124 条非流形边的非水密件 → **0 开放边 / 0 非流形边 / `watertight: true` / `printable: true`**，250,000 面，耗时约 50 秒。
- `print_prep.py` 自动把 STL 转成 Z-up 并落到 z=0，输出 `rotated_to_z_up`；此前导出的 STL 是 Y-up，进切片软件会躺倒。
- 输出新增 `solidify`（补实体前后缺陷数）、`volume_cm3`（水密件体积，并校验不超过包围盒）。
- 单测增至 35 条（新增 solidify 冒烟测试，缺 open3d/pymeshfix 时自动跳过）。

### Changed
- 打印主路径从「先试切片软件修复」改为「直接 `--solidify`」：切片软件的自动修复对 8 万多条开放边基本无效，Blender 也不在该链路里。

### Notes
- 试过但做不通的路子（勿重走）：`pymeshfix` 直接修开口壳会卡死（500k 面跑 10 分钟无结果，降到 150k 面仍 280 秒超时）；体素 `fill` 在开口壳上会漏成“模具外壳”，体积暴涨到包围盒之外；`trimesh.repair.fill_holes` 对 8.7 万条开放边无效。

## [0.2.0] - 2026-11-18

### Added
- **可打印出口**：`--format obj` 全链路支持。解包把 `pbr/` 整目录（obj + mtl + 贴图）一起带出来，`model_path` 指向主模型文件。
- `scripts/print_prep.py`：打印整理。按 Y-up 换算毫米尺度、统计边界边与非流形边、补洞与法线修复、可选减面，导出 `xxx-150mm.obj` 与 `.stl`，stdout 给 `watertight` / `printable` / `warnings`。
- 单测从 28 条增至 34 条（新增 obj 解包 2 条、打印整理 4 条）。

### Fixed
- `extract_model_bundle()` 之前只认 `.glb/.gltf`，obj 包会退回 zip 路径，`model_path` 实际不可用。

### Notes
- 实测（参考图 → obj）：包体 26 MB，解包后 obj 52 MB + 贴图 11 MB；512,997 面；150 mm 成品 53×48×150 mm。
- 图生 3D 的产物是**开口壳体**：实测 87,699 条开放边、1,124 条非流形边，`printable` 为 `false`。这是事实而非缺陷，切片前需自动修复或 Blender Remesh。

## [0.1.1] - 2026-11-18

### Fixed
- **产物是 zip 包而非裸 glb**：官方 `file_url` 返回 `.zip`（内含 `pbr/mesh_textured_pbr.glb`），但 `Content-Disposition` 可能写成 `.glb`，导致下载后被误命名。现改为按文件头（`PK` / `glTF`）识别真实格式、自动改后缀并解包出模型。
- `run` / `download` 输出新增 `model_path`（可直接使用的模型路径）与 `path`（原始包体）。

### Added
- `sniff_ext()` / `extract_model_bundle()` 及 5 条对应单测（共 28 条）

## [0.1.0] - 2026-11-18

### Added
- 初始版本：照片 → 卡通参考图 → 火山方舟 Seed3D 图生 3D → glb 的完整链路
- `scripts/ark_3d.py` 零依赖 CLI，含 `create` / `status` / `run` / `download` / `doctor` 子命令
- `doctor` 免费自检：区分"未配置 / Key 无效 / 被接受"三种状态
- `--dry-run` 只打印请求体，便于排查参数与鉴权问题
- Key 三级查找：`--key` > `ARK_API_KEY` > `.ark_key` 文件
- 参考图提示词模板（面向"可建模"而非"好看"）
- 内嵌嵌入图片约束、面数档位、24 小时链接时效等官方限制的校验与提示
- 23 个离线单元测试
- GitHub Actions CI（Python 3.9–3.12 + ruff）
- 文档：`README.md`、`docs/architecture.md`、`docs/faq.md`、`references/ark-3d-api.md`、`examples/prompts.md`

### Notes
- 401/403/429 与任务 `failed` 各自有明确处置策略，避免无效重试产生额外费用
