# 贡献指南

欢迎 issue 和 PR。这个项目很小，规则也简单。

## 提交前

```bash
make test      # 必须全绿
make lint      # ruff，可选但建议
```

测试全部离线，不会调真实接口，也不需要 Key。**不要在测试里发网络请求**——需要网络能力的部分请用纯函数拆出来测。

## 提 PR 的流程

1. 先开 issue 说清要改什么、为什么（文档错漏可以直接提 PR）
2. 从 `main` 拉分支：`feat/xxx`、`fix/xxx`、`docs/xxx`
3. 提交信息用约定式前缀：`feat: ...` / `fix: ...` / `docs: ...` / `test: ...` / `chore: ...`
4. PR 描述里写清：改了什么、怎么验证、有没有影响到 `SKILL.md` 描述的流程

## 硬性约束

- **零第三方依赖**：`scripts/ark_3d.py` 只允许标准库。要引依赖先开 issue 讨论
- **不改协议形态**：stdout 只输出 JSON 结果，日志走 stderr，否则会破坏 Agent 与管道的解析
- **不提交任何密钥**：`.ark_key`、测试里的真实 Key、含 Key 的截图，一律不要进仓库
- **不伪造测试**：涉及网络的逻辑用 `--dry-run` 或纯函数覆盖，不要靠 mock 假装跑通全链路

## 加新模型 / 新格式

模型差异记在 `references/ark-3d-api.md`，CLI 侧只加 `--model` 的可选项并在 README 参数表补一行即可。产物后缀白名单在 `MODEL_EXTS`，加格式记得补一条单测。

## 改 `SKILL.md` 的注意点

`SKILL.md` 是给 Agent 读的执行手册，不是给人看的介绍文档。改动时保持：

- 命令与参数和 CLI 实际行为一致
- 硬性闸门（如"未确认不提交 3D"）不要被软化
- 篇幅精简，细节放 `references/`
