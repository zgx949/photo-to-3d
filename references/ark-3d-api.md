# 火山方舟 3D 生成 API 参考

## 接口

| 用途 | 方法与路径 |
|---|---|
| 创建任务（异步） | `POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks` |
| 查询任务 | `GET https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/{task_id}` |
| 鉴权 | `Authorization: Bearer $ARK_API_KEY`，`Content-Type: application/json` |

## 创建任务请求体

```json
{
  "model": "doubao-seed3d-2-0-260328",
  "content": [
    {"type": "text", "text": "--subdivisionlevel high --fileformat obj"},
    {"type": "image_url", "image_url": {"url": "<公网URL 或 data:image/png;base64,...>"}}
  ]
}
```

- `text` 只承载参数，不能用来描述内容生成；`--subdivisionlevel` / `--fileformat` 为弱校验，写错会被忽略。
- `subdivision_level`、`file_format` 也可以作为顶层字段传（官方 body 参数里有），脚本统一走 `--[parameters]` 文本方式。

## 图片约束（单张）

- 格式：jpeg、png、webp、bmp、tiff、gif
- 宽高比（宽/高）：0.4 – 2.5
- 边长：300 – 6000 px
- 大小：单张 < 30 MB；请求体 < 64 MB（大图不要用 base64，先传公网 URL）
- 数量：1 张，且只生成图中主体

## 产物参数

- `--fileformat`：`obj`（默认）、`glb`、`usd`、`usdz`
- `--subdivisionlevel`：`high`=100 万面（默认）、`medium`=50 万面、`low`=10 万面

## 产物形态（实测）

`content.file_url` 指向的是一个 **zip 压缩包**（URL 以 `.zip` 结尾），包内结构随 `--fileformat` 变化：

```
# glb
pbr/mesh_textured_pbr.glb
# obj
pbr/mesh_textured_pbr.obj
pbr/mesh_textured_pbr.mtl
pbr/textures/Material_0_diffuse.png
```

- 虽然 `Content-Disposition` 可能写成 `.glb`，但**以文件头为准**：`PK\x03\x04` 是 zip，`glTF` 才是裸模型。
- CLI 已内置处理：按文件头识别、自动改名、解包出 glb，输出里的 `model_path` 即最终可用模型，`path` 是原始包体。
- 解包后的 glb 自带 PBR 贴图，可直接进 Blender / three.js / Unity；obj 需要 mtl 与贴图同目录才显示颜色。
- 实测体量：`glb` 26.28 MB / 499,994 面；`obj` 52 MB 文本 / 512,997 面，另有 11 MB 贴图。
- 实测耗时：`glb` 6 分 20 秒，`obj` 约 3 分半（同一张参考图、`medium`）。

## 查询响应关键字段

```json
{"id":"cgt-...","model":"...","status":"succeeded",
 "content":{"file_url":"https://..."},
 "error":{...},"created_at":1234567890,"updated_at":1234567890}
```

- `status` 枚举：`queued` / `running` / `succeeded` / `failed`。
- 成功取 `content.file_url`；失败看 `error.code` / `error.message`。
- 任务数据与产物链接**仅保留 24 小时**（任务 ID 从创建起 7 天内可查），过期需重新生成——务必下载转存。

## 限流

- Seed3D 2.0：最大 RPM 300，最大并发任务 5；超限返回 `429 Too Many Requests`。
- 查询类接口账号级 QPS：查询任务 20、查询任务列表 1、取消/删除 20。

## 常见错误

| 现象 | 原因 | 处理 |
|---|---|---|
| 401 `AuthenticationError` | Key 格式错误或失效 | 换 Key，不重试 |
| 403 / AccessDenied / `ModelNotOpen` | 账号未开通该 3D 模型 | 控制台「快速接入」开通 |
| 429 | 触发限流 | 退避后重试 |
| `failed` + 内容相关 error | 图片含敏感内容或主体不可识别 | 换图 |
| `failed` + 服务异常 | 平台侧问题 | 最多重试 1 次 |

## 开通与账号

首次使用要走完两步，都只能用户自己在控制台点：

1. **实名认证**：<https://console.volcengine.com/user/authentication/detail/>
2. **开通 Seed3D**：<https://console.volcengine.com/ark/region:cn-beijing/model/detail?name=doubao-seed3d-2-0>，页内点「快速接入」

API Key 在同域控制台的 `apikey` 页创建。注意控制台链接要带 `region:cn-beijing`，写成 `region:ark+cn-beijing` 或 `?Id=` 会跳空页。

## 其他模型差异

- `hyper3d-gen2-260112`：文生 3D + 图生 3D；三角面 500–1,000,000，四边面 1,000–200,000；glb/obj/stl/fbx/usdz。
- `hitem3d-2-0-251223`（数美）：图生 3D，标准白膜 / 标准纹理 / 高精白膜 / 高精纹理；面数 100,000–2,000,000；glb/obj/stl/fbx/usdz；分辨率 1536。
