# 贡献指南

欢迎通过 [GitHub Issues](https://github.com/zgx949/photo-to-3d/issues) 报告问题或讨论功能。提交错误报告时，请带上 Python 版本、操作系统、可复现的命令和脱敏后的错误输出。提交模型问题时，可附一个可公开的最小复现样例。

## 本地检查

从源码目录运行以下命令。如果要验证实体修复，再安装 `requirements-solidify.txt`。测试使用本地样例和模拟响应，无需方舟 API Key。

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
make lint
make test
make package
```

修改行为时，更新对应的测试和用法。`ark_3d.py` 仅使用标准库。脚本的 JSON 结果写入 stdout，进度和日志写入 stderr。修改命令或输出字段时，同步检查两份 README 和 `SKILL.md`。保留参考图确认步骤，提交给 CI 的测试使用示例数据或模拟响应即可。

## 提交 PR

从 `main` 新建分支。在 PR 中说明改动、复现或验证方式，以及是否影响 Skill 的使用。请脱敏日志里的 Key、带签名的下载链接和任何私人照片。

## 发布新版本

1. 更新 `pyproject.toml` 和 `scripts/ark_3d.py` 的版本号，把 `CHANGELOG.md` 中对应改动归入新版本。
2. 合并版本改动，确认 `main` 上的 CI 通过。从包含版本改动的提交创建并推送带 `v` 前缀的标签。以下以 `0.2.10` 为例。

   ```bash
   git tag -a v0.2.10 -m "Release v0.2.10"
   git push origin v0.2.10
   ```

3. 标签触发 CI。验证通过后，GitHub Actions 创建 Release，附上可直接安装的 `photo-to-3d.zip` 和 SHA-256 校验文件 `photo-to-3d.zip.sha256`。在 Actions 和 Releases 页面查看状态。[CI](https://github.com/zgx949/photo-to-3d/actions/workflows/ci.yml) · [Releases](https://github.com/zgx949/photo-to-3d/releases)

下载两份文件到同一目录后，可运行 `shasum -a 256 -c photo-to-3d.zip.sha256` 校验压缩包。在 Linux 上也可使用 `sha256sum -c photo-to-3d.zip.sha256`。
