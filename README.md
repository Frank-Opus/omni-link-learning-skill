# Omni Link Learning Skill

把一个链接或主题名整理成可复用的内容报告。主流程默认产出完整报告；学习计划是一项可选子功能。

## 当前能力

- 支持输入：`Douyin`、`Xiaohongshu`、`WeChat MP`、`X`、`X bookmarks`、`Jike`、`Bilibili`、`Xiaoyuzhou`、通用网页、主题词
- 支持输出：`manifest.json`、`source_read.md`、`transcript.txt`、`analysis_report.md`
- 可选输出：`study_plan.md`
- 视频链路：优先抓原始页面/结构化数据，必要时下载媒体做本地 ASR，再生成分析报告

## 默认用法

先安装依赖：

```bash
npm install
python3 -m pip install -r requirements.txt
```

```bash
python3 scripts/run_pipeline.py \
  --input "<url-or-topic>" \
  --outdir ./omni_learning_output \
  --asr-fallback \
  --asr-model large-v3-turbo \
  --asr-language zh
```

这会默认生成：

- `manifest.json`
- `source_read.md`
- `transcript.txt`（有字幕或 ASR 成功时）
- `analysis_report.md`

## 可选学习计划

只有在明确需要“一键学习”时，再加：

```bash
python3 scripts/run_pipeline.py \
  --input "<url-or-topic>" \
  --outdir ./omni_learning_output \
  --asr-fallback \
  --asr-model large-v3-turbo \
  --asr-language zh \
  --with-study-plan
```

这会额外生成 `study_plan.md`。

## 上传前建议

- 不要上传 `node_modules/`
- 不要上传 `tmp_*`、`omni_learning_output/`、测试产物、下载的媒体文件
- 不要上传 `config.json`、`memory/` 这类本地配置和工作日志
- 保留 `package.json`、`package-lock.json`、`requirements.txt`、`scripts/`、`references/`、`SKILL.md`、`README.md`

## 已知前提

- 小红书视频下载通常依赖本机 Chrome 已登录
- `x-bookmarks:` 依赖本地 `fieldtheory` 已完成同步
- 部分平台会受可见性、风控、登录态影响

## 可选旧方案

仓库里仍保留 `scripts/fetch_with_mcp.py`，但它是可选旧方案，不是默认主链路：

- 默认主链路优先走无 token / 本地能力
- 只有在你明确需要兼容某些 MCP 下载场景时，才使用它
- 若使用它，请基于 `config.example.json` 自行创建本地 `config.json`
