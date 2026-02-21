# 🎯 阿里云百炼 API Key 配置指南

## 为什么需要 API Key？

抖音/小红书 MCP server 使用**阿里云百炼 API**进行：
- 🎵 抖音视频 ASR 语音转写
- 📹 小红书视频语音识别
- 🔗 视频下载链接解析（部分功能）

**无需 API Key 的功能**：
- ✅ 获取小红书文案
- ✅ 获取小红书图片
- ✅ 基础视频信息解析

**需要 API Key 的功能**：
- ⚠️ 抖音视频完整转写
- ⚠️ 小红书视频语音转写
- ⚠️ 高质量下载链接获取

---

## 📝 步骤 1：获取阿里云百炼 API Key

### 1.1 访问阿里云百炼
打开：https://help.aliyun.com/zh/model-studio/get-api-key?

### 1.2 登录/注册
- 使用阿里云账号登录
- 没有账号？先注册（需要手机号验证）

### 1.3 开通服务
1. 进入**模型服务灵积**控制台
2. 点击**开通服务**
3. 同意服务协议

### 1.4 创建 API Key
1. 进入**API-KEY 管理**页面
2. 点击**创建新的 API-KEY**
3. 复制生成的 key（格式：`sk-xxxxxxxxxxxxxxxx`）

**⚠️ 重要**：API Key 只显示一次，请立即保存！

---

## 🔧 步骤 2：配置到 omni-link-learning

### 2.1 编辑配置文件
文件位置：`~/.openclaw/skills/omni-link-learning/config.json`

当前内容：
```json
{
  "api_key": "",
  "model": "paraformer-v2",
  "language_hints": ["zh", "en"],
  "temp_dir": "/home/ericjiang0318/.openclaw/skills/omni-link-learning/temp"
}
```

### 2.2 填入 API Key
将 `api_key` 改为你的 key：
```json
{
  "api_key": "sk-your-actual-api-key-here",
  "model": "paraformer-v2",
  "language_hints": ["zh", "en"],
  "temp_dir": "/home/ericjiang0318/.openclaw/skills/omni-link-learning/temp"
}
```

### 2.3 保存文件
保存并关闭编辑器。

---

## ✅ 步骤 3：测试配置

### 测试命令
```bash
cd ~/.openclaw/skills/omni-link-learning
python3 scripts/fetch_with_mcp.py \
  --input "https://v.douyin.com/Cy1JSsfRS_A/" \
  --outdir ./omni_learning_output \
  --config ./config.json
```

### 成功输出
```
🎯 Platform: Douyin
📥 Input: https://v.douyin.com/Cy1JSsfRS_A/
✓ Video info parsed: [视频标题]
✓ Download link obtained
✓ Text extracted (XXXX chars)

✅ Results saved to: ...

📊 Summary:
✓ Transcript: XXXX chars
✓ Title: [视频标题]
```

---

## 💰 费用说明

### 免费额度
- 新用户：**免费 100 万 tokens**（约 100+ 小时音频转写）
- 每月赠送：一定额度（具体看官方政策）

### 收费标准
- **Paraformer-v2 模型**：约 ¥0.02/分钟音频
- 1 小时视频 ≈ ¥1.2
- 10 小时视频 ≈ ¥12

**非常便宜！** 完全够用。

### 查看用量
访问：https://bailian.console.aliyun.com/
- 左侧菜单：**用量查询**
- 查看当前周期用量和费用

---

## 🚀 使用示例

### 示例 1：分析抖音视频
```bash
python3 scripts/fetch_with_mcp.py \
  --input "https://v.douyin.com/xxxxx/" \
  --outdir ./output_douyin \
  --config ./config.json
```

**输出文件**：
- `douyin_mcp_result.json` - 完整结果
- 包含：视频信息、下载链接、转写文本

---

### 示例 2：分析小红书笔记
```bash
python3 scripts/fetch_with_mcp.py \
  --input "https://www.xiaohongshu.com/explore/xxxxx" \
  --outdir ./output_xhs \
  --config ./config.json
```

**输出文件**：
- `xiaohongshu_mcp_result.json` - 完整结果
- 包含：笔记信息、图片、文案、语音转写（如果是视频）

---

## 🔍 故障排查

### 问题 1：仍然提示 "未设置 DASHSCOPE_API_KEY"
**检查**：
1. config.json 中的 `api_key` 是否正确填写
2. API Key 格式是否正确（应该以 `sk-` 开头）
3. 是否有多余的空格或引号

**解决**：
```json
// ❌ 错误
"api_key": " sk-xxxxx "
"api_key": sk-xxxxx

// ✅ 正确
"api_key": "sk-xxxxx"
```

---

### 问题 2：API Key 无效/过期
**症状**：返回 "Invalid API Key" 错误

**解决**：
1. 登录阿里云百炼控制台
2. 检查 API Key 状态
3. 重新创建新的 API Key
4. 更新 config.json

---

### 问题 3：余额不足
**症状**：返回 "Insufficient balance" 错误

**解决**：
1. 访问阿里云控制台
2. 充值账户
3. 确保百炼服务有可用额度

---

### 问题 4：网络连接失败
**症状**：Timeout 或 Connection error

**解决**：
1. 检查网络连接
2. 尝试访问 https://bailian.console.aliyun.com/ 确认服务正常
3. 如果是公司网络，可能需要配置代理

---

## 📊 完整工作流

### 1. 获取抖音/小红书链接
- 打开抖音/小红书 App
- 找到想要分析的视频/笔记
- 点击**分享** → **复制链接**

### 2. 运行 MCP 脚本
```bash
python3 scripts/fetch_with_mcp.py \
  --input "[你的链接]" \
  --outdir ./omni_learning_output \
  --config ./config.json
```

### 3. 查看结果
打开 `omni_learning_output/[platform]_mcp_result.json`

### 4. 用 omni-link-learning 分析
```bash
# 脚本会自动使用 MCP 获取的内容
python3 scripts/fetch_source.py \
  --input "[你的链接]" \
  --outdir ./omni_learning_output \
  --asr-fallback  # 如果 MCP 没有转写，用本地 ASR 备用
```

### 5. 生成分析报告
- `deep_analysis.md` - 深度分析
- `action_items.md` - 行动清单
- `study_plan.md` - 学习计划

---

## 🎁  bonus：环境变量方式（可选）

除了 config.json，也可以用环境变量：

### Bash/Zsh
```bash
export DASHSCOPE_API_KEY="sk-your-api-key"
```

### 添加到 ~/.bashrc 或 ~/.zshrc
```bash
echo 'export DASHSCOPE_API_KEY="sk-your-api-key"' >> ~/.bashrc
source ~/.bashrc
```

### 永久生效
这样所有使用百炼 API 的工具都能自动使用这个 key。

---

## 📞 获取帮助

### 官方文档
- 阿里云百炼：https://help.aliyun.com/zh/model-studio/
- MCP Server: https://github.com/yzfly/douyin-mcp-server

### 常见问题
- API Key 管理：https://bailian.console.aliyun.com/
- 用量查询：同上
- 技术支持：阿里云工单系统

---

## 🎯 下一步

配置好 API Key 后，就可以：

1. ✅ 分析抖音 AI 电商视频
2. ✅ 分析小红书创业笔记
3. ✅ 批量获取竞品内容
4. ✅ 建立行业情报库

**老板，配置好后告诉我，我立即帮你分析那个抖音视频！** 🚀

---

*最后更新：2026-02-19*  
*基于 dy-xhs-mcp-server v1.2.1*
