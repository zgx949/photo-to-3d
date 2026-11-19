# photo-to-3d

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.9-blue.svg)]()
[![CI](https://github.com/OWNER/photo-to-3d/actions/workflows/ci.yml/badge.svg)](.github/workflows/ci.yml)

把一张真人照片变成可用的 3D 模型。链路是：**照片质检 → 人物分割 → 卡通参考图（保身份、保姿势） → 人工确认 → 火山方舟 Seed3D 图生 3D → 下载 glb / obj →（要打印）补成封闭实体 →（要颜色）把贴图搬回实体**。

它同时是一个 **Agent Skill**（给豆包 / Claude 这类 Agent 直接调用）和一个**零依赖命令行工具**。

> 推到 GitHub 后，把上面 CI badge 里的 `OWNER` 替换成实际仓库所有者即可。

---

## 为什么需要中间那一步卡通化

直接把真人照片丢给图生 3D，结果通常很糟：皮肤和衣物细节被抹平、背景被当成主体、人脸变成塑料泥。原因是这类模型吃的是"单主体、轮廓清晰、可读拓扑"的输入。

所以本项目在中间加了一层**参考图重制**：用图像编辑模型把照片转成"全身、单主体、纯色背景、四肢分离、服饰简化成色块"的卡通角色图——本质是把实拍照片翻译成模型能读懂的形态，再送去做 3D。

这一步是免费的，可以反复重出直到轮廓干净；真正花钱的 3D 生成放在最后，且必须经人工确认才触发。

## 怎么保证像本人

相似度不靠提示词运气，靠四个固定动作（细节见 [references/identity-prompt.md](references/identity-prompt.md)）：

1. **先分割**：`mediakit-cli image remove-image-background --scene human` 抠出主体，去掉背景杂物对生成的干扰；
2. **先填特征表**：脸型、眉眼（含眼距）、鼻、嘴、发型发色、肤色、体型、服装，逐项对着照片写，看不清写"被遮挡"，禁止脑补；
3. **默认还原原片姿势**：重心脚、肩线、身体朝向、手臂位置、视线都写进提示词；用户点了具体动作才换，并说明会降低相似度；
4. **并排验收**：参考图与抠图后的原片比对五项，有一条不过就重出；脸不对但体型对，用"只修脸"的二次编辑再救一次。

## 特性

- **零依赖**：`scripts/ark_3d.py` 只用标准库，拷走就能跑（后处理脚本另需 trimesh 等）
- **一条命令全链路**：`scripts/pipeline.py` 串起「生成 obj → 本地高精度修复（补实体 + 头部加密 + 面部锐化）→ 上色 → 预览页」，默认交付可打印件与可直接点开的 3D 查看器
- **本地修复，重点在脸**：方舟只给初版模型；本地在头部高度带追加 0.6× 采样点（总密度约 1.6×）、成品保留 60 万面，并在脸部高度带做顶点色反锐化（头发与深色区域不动）
- **能打印**：`--format obj` 出口 + `scripts/print_prep.py --solidify`（泊松补实体、校尺度、转 Z-up、导出 STL）
- **能上色**：`scripts/bake_color.py`（贴图 → 顶点色搬回实体，出彩色 obj / glb）
- **双形态**：既是 Agent Skill（`SKILL.md` 定义流程），也是普通 CLI（可进 CI / 批处理）
- **像本人**：先人物分割去掉背景干扰，再填身份特征表（脸型/眉眼/鼻嘴/发型/体型/服装）+ 3 个识别锚点写进提示词；用户没指定动作就还原原片姿势，不默认 A-pose
- **确认闸门**：参考图未确认不提交 3D 任务，避免无效计费
- **结构化输出**：所有结果以 JSON 打到 stdout，日志走 stderr，便于管道消费
- **自检**：`doctor` 子命令免费校验 Key 是否被服务端接受
- **语义化错误**：401/403/429/任务失败分别有明确处置策略
- **可测**：39 个离线单元测试，不需要网络、不产生调用费用

## 快速开始

生成阶段默认向方舟要 `obj`：包内自带 mtl 与贴图，补实体、上色都直接吃得下，不需要为了预览再单独生成 glb（glb 由上色步骤在本地导出）。

要求 Python 3.9+。依赖按功能分层，核心 CLI 零第三方库：

| 分组 | 用途 | 安装 |
|---|---|---|
| 核心 | 建任务 / 轮询 / 下载 / doctor | 无需安装 |
| 轻量后处理 | 尺度诊断、上色、预览页 | `pip install -r requirements.txt` |
| 实体修复 | `--solidify` 补封闭实体、减面 | `pip install -r requirements-solidify.txt` |
| 开发 | lint / 测试 | `pip install -r requirements-dev.txt` |

> 只跑 `ark_3d.py` 完全不需要第三方库；`pipeline.py` / `print_prep.py` / `bake_color.py` / `make_preview.py` 才需要上面的后处理依赖。

### 方式一：作为 Agent Skill

把整个仓库目录放进 Agent 的 skills 目录（通常是 `.../workspace/.user_skills/`）：

```
workspace/.user_skills/photo-to-3d/
├── SKILL.md                 # Agent 入口：流程、闸门、提示词、打印与上色
├── scripts/
│   ├── ark_3d.py            # 建任务 / 轮询 / 下载 / doctor（零依赖）
│   ├── pipeline.py          # 全链路编排：生成 → 补实体 → 上色 → 预览
│   ├── print_prep.py        # 补实体 + 尺度 + Z-up + STL（需 trimesh / open3d / pymeshfix）
│   ├── bake_color.py        # 贴图 → 顶点色（需 trimesh / rtree / pillow）
│   └── make_preview.py      # glb → 单文件 3D 查看器（可选 playwright 出缩略图）
└── references/ark-3d-api.md
```

Agent 读到 `SKILL.md` 后会自动按流程执行，包括照片质检、参考图提示词模板、确认闸门和交付规则。

### 方式二：作为命令行工具

```bash
git clone <repo-url> photo-to-3d && cd photo-to-3d

export ARK_API_KEY="你的方舟 Key"
python3 scripts/ark_3d.py doctor                       # 自检，免费

python3 scripts/pipeline.py --image ./cartoon-ref.png --out ./out --name model
#   = 方舟出 obj → 本地高精度修复 → 上色 → 预览页，一次给齐：可打印 obj/stl、彩色 obj/glb、预览 html
#   嫌慢加 --no-refine（25 万面快档），想更细加 --faces 800000
```

成功输出：

```json
{"task_id":"cgt-...","status":"succeeded","file_url":"https://...",
 "path":"./out/model-cgt-....zip","model_path":"./out/model-cgt-....glb","bytes":21826481}
```

> **产物是 zip 包**：方舟返回的 `file_url` 指向压缩包，包内是 `pbr/mesh_textured_pbr.glb`（带 PBR 贴图）。CLI 会按文件头识别真实格式、自动改后缀并解包，`model_path` 就是能直接用的模型，`path` 是原始包体。

> 实测参考：1330×1773 的参考图、`medium`（50 万面）——`glb` 约 6 分 20 秒（26 MB / 499,994 面），`obj` 约 3 分半（解包后 52 MB / 512,997 面）。

## 配置 API Key

Key 查找优先级：`--key` > 环境变量 `ARK_API_KEY` > 仓库根目录 `.ark_key` 文件。

| 方式 | 适用场景 | 命令 |
|---|---|---|
| 环境变量 | CI、临时会话 | `export ARK_API_KEY="..."` |
| `.ark_key` 文件 | 长期使用、不想每次 export | `printf '%s' '<KEY>' > .ark_key && chmod 600 .ark_key` |

`.ark_key` 已在 `.gitignore` 中，不会被提交。**不要把 Key 写进代码、文档或对话截图**；它等同于账号额度，泄露就去方舟控制台删除重建。

还没开通 3D 模型时，创建任务会返回 `403` / `ModelNotOpen`。开通入口在模型详情页，页内点「快速接入」：

- Seed3D 2.0：<https://console.volcengine.com/ark/region:cn-beijing/model/detail?name=doubao-seed3d-2-0>
- 实名认证：<https://console.volcengine.com/user/authentication/detail/>
- API Key：<https://console.volcengine.com/ark/region:cn-beijing/apikey>

## CLI 参考

| 子命令 | 作用 |
|---|---|
| `create` | 提交任务，返回 `task_id`（异步，不阻塞） |
| `status` | 查询单个任务，成功则返回 `file_url` |
| `run` | `create` + 轮询 + 下载，一步到位 |
| `download` | 按已有 `file_url` 补下载 |
| `doctor` | 校验 Key 是否被服务端接受，不产生费用 |

`pipeline.py` 是整条链路的编排入口：`--image` 出全新模型，`--skip-3d <obj>` 只补后续步骤（不重新计费）；`--height`、`--no-color`、`--no-solidify` 可按需裁剪。

关键参数：

| 参数 | 取值 | 默认 |
|---|---|---|
| `--model` | `doubao-seed3d-2-0-260328` / `hyper3d-gen2-260112` / `hitem3d-2-0-251223` | Seed3D 2.0 |
| `--format` | `obj` / `glb` / `usd` / `usdz` | `obj` |
| `--level` | `high`(100万面) / `medium`(50万) / `low`(10万) | `high` |
| `--image` | 公网 URL、本地路径或 `data:` URI | 必填 |
| `--poll-interval` / `--timeout` | 轮询间隔秒 / 总超时秒（仅 `run`） | 15 / 1500 |

`create` 支持 `--dry-run`：只打印将要发送的请求体，不真实调用，也不需要 Key。

## 3D 打印（obj / stl）

方舟原生支持 `--format obj`，包里是 `pbr/mesh_textured_pbr.obj` + `.mtl` + 贴图，CLI 会整目录解出来。

但**能打印不等于换个后缀**，要过四关：尺度、封闭性、面数、朝向。一条命令全做完：

```bash
pip install -r requirements.txt            # 轻量：trimesh / numpy / pillow / rtree
pip install -r requirements-solidify.txt    # 实体修复：open3d / pymeshfix / fast-simplification

python3 scripts/ark_3d.py run --image ./cartoon-ref.png --out ./out --format obj
python3 scripts/print_prep.py "$(echo ./out/model-*.obj)" --height 150 --out ./print --solidify
```

> open3d 装不上时可先只做尺度诊断（去掉 `--solidify`），或走下文退路。

输出 `xxx-150mm.obj` 与 `xxx-150mm.stl`（STL 已转 Z-up 并落到 z=0），并给出：

```json
{"solidified":true,"triangles":249988,"size_mm":{"width":53.44,"depth":47.93,"height":150.0},
 "watertight":true,"boundary_edges":0,"nonmanifold_edges":0,"volume_cm3":117.03,
 "printable":true,"rotated_to_z_up":true,"warnings":[]}
```

- `--solidify`：**补成封闭实体**，打印必须开。做法是「有向点云 → 泊松重建 → 减面 → pymeshfix 清残余坏边」。
- `--height`：成品高度（毫米），默认 150；按 `--up`（默认 `y`，方舟产物 Y-up）量。
- `--samples` / `--depth`：补实体的采样点数与泊松深度（默认 50 万点 / 9），越大越细也越慢。
- `--decimate`：减面目标（补实体默认 25 万面），切片明显更快，成品看不出差别。
- `--keep-source-units`：不缩放，只做检查与导出。

**为什么必须 `--solidify`**：图生 3D 的产物是**开口壳体**——一层皮肤，不是实心体。实测 500,000 面的 obj 有 87,699 条开放边，在任何查看器里都是满身裂纹，切片软件补不干净。补实体后：

| 项 | 补实体前 | 补实体后 |
|---|---|---|
| 开放边 | 87,699 | 0 |
| 非流形边 | 1,124 | 0 |
| 水密 | false | true |
| 面数 | 512,997 | 249,988 |
| 耗时 | — | 约 50 s（含读 52 MB obj） |

代价是贴图上的眼白、唇色这类“画上去的细节”会丢，因为是纯几何重建；要还原得上色（分件打印或后期喷涂）。

> open3d 装不上的退路：Bambu Studio / PrusaSlicer / Cura 的自动修复，或 Blender `Remesh(Voxel 0.3 mm) → Smooth → Decimate`。
>
> 另：STL 没有“哪边朝上”的定义，切片软件默认 Z 轴竖直，所以脚本会把 Y-up 模型转成 Z-up 并落到 z=0，别自己再转一次。

> 实测：1330×1773 参考图 → `obj` 包 26 MB（解包后 obj 52 MB + 贴图 11 MB）→ 150 mm 成品 53×48×150 mm，51.3 万面，87,699 条开放边。

## 上色（把贴图搬回实体）

补实体弃掉 UV 与贴图，产物是素模。要把颜色拿回来：

```bash
python3 scripts/bake_color.py --solid ./print/model-150mm.obj \
    --textured ./out/pbr/mesh_textured_pbr.obj --out ./color --name model
```

| 步骤 | 做法 |
|---|---|
| 对位 | 带贴图的壳按高度缩放、转 Z-up、落地并水平居中，实测最近点平均 0.02 mm |
| 取色 | 最近三角形 → 重心坐标 → 插值 UV → 采样漫反射贴图 |
| 去斑 | 两轮邻域中位色校正，清掉最近点错配产生的零星色点 |
| 出口 | `-彩色.obj`（Z-up，打印链路）+ `-彩色.glb`（Y-up，浏览器 / Blender 预览） |

实测：249,988 面 / 124,992 顶点，10 秒内完成，去斑修正约 3,000 个顶点。

> 顶点色在切片软件里支持不一致，打印上色仍建议分件换色或后期手涂；眼白这类小面积细节会偏软。

## 输入图片要求（方舟侧硬约束）

| 项 | 要求 |
|---|---|
| 数量 | 1 张，且只生成图中主体 |
| 格式 | jpeg / png / webp / bmp / tiff / gif |
| 宽高比 | 0.4 – 2.5 |
| 边长 | 300 – 6000 px |
| 大小 | 单张 < 30 MB，请求体 < 64 MB（大图请先上传换 URL，不要 base64） |

## 计费、限流与时效

- 3D 生成**按次计费**，耗时数分钟到十几分钟，单次失败也可能产生费用——所以有确认闸门和"同图默认只提交一次"的纪律。
- Seed3D 2.0：最高 300 RPM、5 并发；超限返回 `429`，CLI 自动退避重试。
- 任务数据与产物链接**仅保留 24 小时**，务必即时下载；任务记录 7 天内可查。

## 目录结构

```
photo-to-3d/
├── SKILL.md                 # Agent 入口：流程、闸门、提示词模板
├── README.md
├── LICENSE
├── CHANGELOG.md
├── CONTRIBUTING.md
├── Makefile
├── pyproject.toml           # 项目元数据 + 分层可选依赖 + ruff 配置
├── requirements.txt          # 轻量后处理依赖
├── requirements-solidify.txt # 实体修复 / 减面重依赖
├── requirements-dev.txt      # 开发工具链
├── scripts/
│   ├── pipeline.py          # 一条命令：生成 obj → 补实体 → 上色 → 预览
│   ├── make_preview.py      # glb → 单文件 3D 查看器（+ 可选缩略图）
│   ├── ark_3d.py            # 零依赖 CLI：create / status / run / download / doctor
│   ├── print_prep.py        # 打印整理：泊松补实体 / 尺度 / Z-up / STL
│   └── bake_color.py        # 上色：贴图 → 顶点色，出彩色 obj / glb
├── assets/viewer.template.html  # 单文件 3D 查看器模板
├── references/
│   ├── ark-3d-api.md        # 接口字段、产物包结构、错误码
│   └── identity-prompt.md   # 相似度控制：分割 / 特征表 / 姿势 / 提示词 / 验收
├── examples/
│   └── prompts.md           # 四种风格的参考图提示词样例
├── docs/
│   ├── architecture.md      # 设计取舍与状态机
│   └── faq.md
└── tests/
    ├── test_ark_3d.py
    ├── test_print_prep.py
    ├── test_bake_color.py
    ├── test_make_preview.py
    ├── test_pipeline.py
    └── fixtures/tiny.png
```

## 开发

```bash
make test     # python3 -m unittest discover -s tests -v
make lint     # ruff check .
make doctor   # 校验 Key（需要已配置）
make package  # 打发布压缩包到 dist/
```

测试全部离线运行：不发网络请求、不需要 Key、不产生任何方舟费用。提交前请保证 `make test` 全绿。

## 常见问题

见 [docs/faq.md](docs/faq.md)，以及 [docs/architecture.md](docs/architecture.md) 里关于"为什么先卡通化""为什么必须人工确认"的设计说明。

## 免责声明

本项目是社区实现，**不是火山引擎官方项目**，与火山引擎无隶属关系。模型能力、计费与条款以官方为准；使用前请自行确认账号权限与预算。

## License

[MIT](LICENSE)
