# Omni Link Learning - 抖音抓取改进说明

## 问题分析 (2026-02-21)

### 原始问题
用户请求分析抖音视频链接：`https://v.douyin.com/Ia9ZzpVhpdU/`

**失败原因：**
1. ❌ **r.jina.ai 超时** - 抖音重度 JS 渲染 + 反爬机制，导致 Jina Reader 抓取超时
2. ❌ **Metadata 提取失败** - `fetch_douyin_metadata()` 依赖 Jina Reader 返回内容
3. ❌ **无 URL 重定向处理** - 抖音短链接 `v.douyin.com` 需要跟随重定向
4. ❌ **ASR fallback 未自动启用** - 需要手动指定 `--asr-fallback` 参数

## 改进方案

### 1. 增强 HTTP 请求处理

**文件：** `scripts/fetch_source.py`

**改进：**
- ✅ 添加自动重定向处理（最多 5 次）
- ✅ 增加超时时间（默认 30s → 60s，抖音自动延长至 90s）
- ✅ 添加重试机制（指数退避：2^attempt 秒）

```python
def http_get_text(url: str, timeout: int, headers: dict[str, str] | None = None, allow_redirects: bool = True)
```

### 2. 多层 Metadata 提取策略

**原方案：** 单一依赖 Jina Reader
**新方案：** 三层降级策略

```python
Strategy 1: Jina Reader (r.jina.ai)
    ↓ 失败
Strategy 2: 抖音移动 Web API (m.douyin.com)
    - 尝试解析 window._ROUTER_DATA
    - 提取 HTML meta 标签
    ↓ 失败
Strategy 3: 备用 Reader 服务
    - r.jina.ai/http/ 前缀
    - 更长超时
    ↓ 失败
Graceful Degradation: 标记 degradation_mode=True
```

### 3. 抖音平台特殊处理

**自动 ASR fallback：**
```python
# 对于抖音，总是建议启用 ASR
if platform == "douyin":
    manifest["notes"].append("Douyin platform detected: subtitles typically unavailable, will proceed to ASR fallback.")

should_try_asr = (
    (not subtitle_result["transcript_path"] and args.asr_fallback) or
    (platform == "douyin" and args.asr_fallback)
)
```

### 4. 增强的错误报告

**Manifest 新增字段：**
```json
{
  "strategies_tried": ["jina_reader", "douyin_mobile_api", "alternative_readers"],
  "strategy_success": "douyin_mobile_api",
  "degradation_mode": true,
  "asr_quality": {
    "text_length": 1234,
    "cjk_ratio": 0.15,
    "assessment": "high",
    "notes": ["Good CJK ratio (0.15), high confidence"]
  }
}
```

## 使用建议

### 标准用法（推荐）
```bash
python3 scripts/fetch_source.py \
  --input "https://v.douyin.com/Ia9ZzpVhpdU/" \
  --outdir ./omni_learning_output \
  --asr-fallback \
  --asr-model large-v3-turbo \
  --asr-language zh \
  --timeout 90 \
  --retry 2
```

### 快速模式（仅元数据）
```bash
python3 scripts/fetch_source.py \
  --input "https://v.douyin.com/xxxxx" \
  --outdir ./output \
  --timeout 60
```

### GPU 加速 ASR（如有 NVIDIA GPU）
```bash
# 检查 GPU
nvidia-smi

# 运行（自动检测 GPU）
python3 scripts/fetch_source.py \
  --input "https://v.douyin.com/xxxxx" \
  --outdir ./output \
  --asr-fallback \
  --asr-model large-v3-turbo
```

## 预期行为对比

| 场景 | 改进前 | 改进后 |
|------|--------|--------|
| 抖音短链接 | ❌ 超时 | ✅ 自动重定向 + 延长超时 |
| Jina Reader 失败 | ❌ 直接报错 | ✅ 降级到移动 API |
| 无字幕视频 | ❌ 无转录 | ✅ 自动 ASR fallback |
| 网络波动 | ❌ 立即失败 | ✅ 重试 2 次（指数退避） |
| ASR 质量差 | ⚠️ 无提示 | ✅ CJK 比率检测 + 质量评级 |

## 依赖检查清单

```bash
# 必需
python3 --version  # Python 3.10+
pip show yt-dlp    # 视频/音频下载

# ASR fallback（可选但推荐）
# 安装 faster-whisper skill
~/.codex/skills/faster-whisper/scripts/transcribe --help

# GPU 加速（可选）
nvidia-smi  # 检查 NVIDIA GPU
```

## ⚠️ 抖音下载限制

**问题：** 抖音需要登录 Cookie 才能下载视频（yt-dlp 报错：`Fresh cookies are needed`）

**解决方案：**

### 方案 1：使用浏览器 Cookie（推荐）
```bash
# yt-dlp 会自动尝试从 Chrome 读取 Cookie
yt-dlp --cookies-from-browser chrome "https://v.douyin.com/xxxxx"

# 或使用其他浏览器
yt-dlp --cookies-from-browser firefox "https://v.douyin.com/xxxxx"
```

### 方案 2：导出 Cookie 文件
```bash
# 使用浏览器插件导出 cookies.txt
# 然后指定给 yt-dlp
yt-dlp --cookies cookies.txt "https://v.douyin.com/xxxxx"
```

### 方案 3：手动下载视频
```bash
# 在抖音 App 或网页版下载视频
# 然后直接对本地文件运行 ASR
python3 scripts/fetch_source.py \
  --input "/path/to/local/video.mp4" \
  --outdir ./output \
  --asr-fallback
```

### 方案 4：仅使用 Jina Reader 内容
```bash
# 如果 Jina Reader 能抓取到文字内容
# 可以直接分析 source_read.md，跳过 ASR
python3 scripts/fetch_source.py \
  --input "https://v.douyin.com/xxxxx" \
  --outdir ./output
# 然后手动分析 ./output/source_read.md
```

**改进后的行为：**
- ✅ 自动尝试多种 URL 格式（短链接 → 桌面版 → 移动版）
- ✅ 自动尝试从 Chrome 读取 Cookie
- ✅ 详细的下载尝试日志（记录每次尝试的结果）
- ✅ 优雅降级（下载失败时明确提示）

## 后续优化方向

1. **集成抖音官方 API** - 如果有 API 访问权限
2. **缓存机制** - 避免重复抓取相同视频
3. **批量处理** - 支持多个链接同时处理
4. **进度条** - 长时间 ASR 任务显示进度
5. **字幕时间戳对齐** - 改进学习体验

## 测试用例

```bash
# 测试 1: 标准抖音视频
python3 scripts/fetch_source.py --input "https://v.douyin.com/Ia9ZzpVhpdU/" --outdir ./test1 --asr-fallback

# 测试 2: 哔哩哔哩（验证未破坏现有功能）
python3 scripts/fetch_source.py --input "https://b23.tv/souSczX" --outdir ./test2 --asr-fallback

# 测试 3: 小红书
python3 scripts/fetch_source.py --input "https://www.xiaohongshu.com/explore/xxxxx" --outdir ./test3

# 测试 4: 主题搜索
python3 scripts/fetch_source.py --input "AI 视频剪辑教程" --outdir ./test4
```

---

**更新日期：** 2026-02-21  
**更新者：** 小灰灰 🐺  
**版本：** omni-link-learning v1.2
