---
name: photo-to-3d
description: 将单张人物照片转换为卡通角色参考图，经用户确认后调用火山方舟 Seed3D 生成 3D 模型，并按需输出可切片的 STL、彩色 GLB 和浏览器预览。用于照片转 3D、制作人像手办或潮玩、修复开口网格、迁移贴图颜色，以及查询或下载既有 3D 任务。
---

# 照片转 3D

从照片开始时，先制作参考图并与用户确认，再提交一次付费生成。用户已提供带贴图的 OBJ 或 GLB 时，可用 `--skip-3d` 直接做本地处理，无需方舟 Key。查询或下载既有任务时，直接用 `ark_3d.py` 对应子命令。

## 运行环境

在本技能目录中运行示例命令，并用用户工作区的路径保存输出。

- `ark_3d.py` 使用 Python 3.9+ 和标准库。网格处理和上色需要 `requirements.txt`，默认的封闭实体重建还需要 `requirements-solidify.txt`。完整流水线建议用有 Open3D 预编译包的 Python 3.11 或 3.12。安装命令见 [README](README.md)。
- Key 从运行环境的 `ARK_API_KEY` 或技能目录下的 `.ark_key` 读取。缺少 Key 时，引导用户在运行环境或宿主的密钥管理器设置它。`.ark_key` 也可由用户在本地创建，并限制为仅自己可读写。请通过这些渠道配置凭据，避免将其发到聊天或写进日志。
- 首次使用需要在方舟开通 Seed3D。用 `python3 scripts/ark_3d.py doctor` 检查凭据，这一步只查任务列表。`401` 时检查 Key，`403` 或 `ModelNotOpen` 时检查账号与模型开通状态。[API Key 管理](https://console.volcengine.com/ark/region:cn-beijing/apikey) · [Seed3D 模型开通](https://console.volcengine.com/ark/region:cn-beijing/model/detail?name=doubao-seed3d-2-0)

## 1. 检查照片并制作参考图

优先使用单主体、头脚完整、轮廓清楚的照片。多人、强逆光、明显透视变形或严重遮挡时，请用户换图、裁切或补拍。手或手机挡脸时，先确认是换图还是去掉遮挡物。已有合格参考图时，可跳到确认步骤。

1. 风格以用户指定为准。缺少风格信息时，可给出 Q 版潮玩、二次元、扁平贴纸等简短选项。
2. 优先用宿主的人物分割工具清理背景。若 `mediakit-cli` 可用，可调用 `mediakit-cli image remove-image-background --image-url "<路径或 URL>" --scene human --need-crop-background=true`。检查分割结果是否保留头脚以及轮廓。分割能力不可用时，用原图制图，并在提示词要求仅保留一人和纯浅灰背景。
3. 按 [人物特征表与提示词模板](references/identity-prompt.md) 抽取可见特征，选择三个辨识度高的特征放进提示词。用宿主可用的图像编辑工具生成参考图，保留原片姿势和服饰主色。宿主没有图像编辑能力时，将填好的模板交给用户，并请其提供参考图。
4. 对照原图检查脸型、五官位置、眉眼、发型、体型和服装。脸不准而体型和姿势正确时，使用参考文档的二次修脸模板。确认参考图只有一个人物，全身完整、背景单纯、四肢轮廓清晰。

## 2. 展示参考图并取得明确确认

用宿主的图片展示能力并排呈现原照或分割照与参考图。请用户确认人物相似度、姿势和风格，说明参考图将发送给火山方舟，生成任务可能计费。确认指向当前这张参考图后，再提交 3D 任务。更换参考图后再次确认。

## 3. 生成与后处理

```bash
python3 scripts/pipeline.py --image "<参考图路径或 URL>" --out "<输出目录>" --name "<名字>"
```

- CLI 可将合格的本地参考图编码进方舟请求。已有兼容的公网 URL 也可直接传入。只有确需外部托管且用户同意时，才把图片上传到额外的服务。[图片约束与接口参数](references/ark-3d-api.md)
- 默认使用 `doubao-seed3d-2-0-260328`，请求 `obj` 与 `high`，一次获取带 MTL 和贴图的模型。流水线在本地生成彩色 GLB。
- 默认成品高 150 mm，使用 80 万采样点、泊松深度 10、约 60 万面，并对顶部 22% 的区域加密和锐化。`--height 200` 可设高度，`--faces 400000` 可改面数，`--no-refine` 可切换到约 25 万面的快速修复档。`--no-color` 或 `--no-preview` 按需跳过对应步骤。
- 已有带贴图的 OBJ 或 GLB 时，使用 `python3 scripts/pipeline.py --skip-3d "<模型路径>" --out "<输出目录>" --height 120`，其中 `120` 可替换为目标高度。OBJ 需要保留匹配的 MTL 和贴图。若 Open3D 不可用，可加 `--no-solidify` 做尺度检查与导出，并按网格报告交付。
- 如只需要原始模型，用 `ark_3d.py run --image "<参考图>" --out "<目录>"`，必要时加 `--format glb`。如需异步执行，先 `create`，再 `status --task-id "<任务 ID>"`，成功后用 `download --file-url "<URL>" --task-id "<任务 ID>" --out "<目录>"` 保存。
- `401` 和 `403` 需要先处理凭据或权限。脚本会对 `429` 做有限退避。超时后按已知任务 ID 查询，避免重复提交。任务失败时读取 `error` 并解释原因。若需重新创建付费任务，先让用户确认。

## 4. 检查并交付

读取流水线 JSON 中的 `files` 与 `warnings`，以实际生成的文件为准。报告尺寸、面数、水密性、开放边与 `printable`。如果 `printable` 为 `false`，说明当前网格需要修复或检查。即使网格通过检查，实际打印仍要在切片软件中确认支撑和薄壁。

1. 优先交付 `files.preview_html`。HTML 内嵌模型，加载查看器需要联网。有 `files.preview_png` 时，用宿主的图片展示能力附上缩略图。
2. 提供 `files.printable_obj`、`files.printable_stl` 和生成的彩色 OBJ、GLB。STL 以 Z 轴朝上并落地。顶点色是否能用于打印取决于切片软件。
3. 保留原始带贴图的 OBJ、MTL 和贴图目录，或提供原始下载包。任务结果中的 `model_path` 指向解包后的模型，`path` 指向原始下载。方舟的临时链接应及时转存。

要单独重做网格、颜色或预览时，分别使用 `print_prep.py`、`bake_color.py` 或 `make_preview.py`。用 `--help` 查看参数和输出配置。
