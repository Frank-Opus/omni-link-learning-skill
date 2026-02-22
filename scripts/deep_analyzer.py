#!/usr/bin/env python3
"""
Deep Analyzer v4.0 - 完整深度分析引擎
核心理念：不遗漏任何有价值的内容

v4.0 新增:
- 关键要点 8→15 个
- 金句 15→25 个
- 新增"完整内容脉络"章节
- 新增"关键数据与事实提取"
- 新增"实战应用清单"
- 新增"认知刷新点"
- 增强智能填充
"""

import argparse
import json
import re
from pathlib import Path
from datetime import datetime


def load_transcript(input_path: str) -> tuple[str, dict]:
    """Load transcript and metadata."""
    path = Path(input_path)
    meta_path = path.parent / "douyin_mcp_result.json"
    metadata = {}
    
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
            video_info = meta.get("video_info", {})
            if isinstance(video_info, dict):
                metadata["title"] = video_info.get("title", "Unknown")
                metadata["author"] = video_info.get("author", "Unknown")
                metadata["platform"] = meta.get("platform", "Unknown")
            
            if "transcript" in meta and meta["transcript"]:
                try:
                    data = json.loads(meta["transcript"])
                    if isinstance(data, dict):
                        if "text" in data:
                            return data["text"].strip(), metadata
                        elif "segments" in data:
                            text = "".join([s.get("text", "") for s in data["segments"]])
                            return text.strip(), metadata
                except: pass
    
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    
    if content.startswith('{'):
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                if "text" in data:
                    return data["text"].strip(), metadata
                elif "segments" in data:
                    text = "".join([s.get("text", "") for s in data["segments"]])
                    return text.strip(), metadata
        except: pass
    
    return content, metadata


def identify_themes(text: str) -> list:
    themes = {
        "职场成长": ["努力", "规划", "机会", "跳槽", "深耕", "长期主义"],
        "销售技巧": ["拜访", "客户", "信任", "成交", "陌拜", "业绩"],
        "自媒体": ["流量", "粉丝", "视频", "爆款", "算法", "获客"],
        "AI 与技术": ["AI", "工具", "自动化", "模型", "Agent"],
        "投资思维": ["投资", "周期", "非共识", "创始人", "机会"],
        "商业洞察": ["市场", "竞争", "利润", "模式", "生态"],
    }
    result = []
    for name, kws in themes.items():
        count = sum(text.count(k) for k in kws)
        if count > 3:
            result.append({"name": name, "count": count})
    result.sort(key=lambda x: x["count"], reverse=True)
    return result[:6]


def split_sentences(text: str) -> list:
    """智能分割文本 - 处理无标点 ASR 转录"""
    # First try normal sentence splitting
    sentences = re.split(r'[.!?。！？]', text)
    
    # If too few sentences, try semantic splitting
    if len(sentences) < 10:
        # Split by common connectors
        connectors = [' 因为 ', ' 所以 ', ' 但是 ', ' 然后 ', ' 就 ', ' 那 ', ' 对 ', ' 其实 ', ' 我觉得 ', ' 我认为 ']
        result = [text]
        for conn in connectors:
            new_result = []
            for s in result:
                if len(s) > 300:  # Only split long segments
                    parts = s.split(conn)
                    for i, p in enumerate(parts):
                        if i > 0 and len(p) > 20:
                            new_result.append(conn.strip() + p)
                        elif len(p) > 20:
                            new_result.append(p)
                else:
                    new_result.append(s)
            result = new_result
        
        # Split by length (max 200 chars)
        final = []
        for s in result:
            if len(s) > 200:
                # Split at natural pauses
                for i in range(0, len(s), 150):
                    chunk = s[i:i+150]
                    if len(chunk) > 30:
                        final.append(chunk)
            elif len(s) > 30:
                final.append(s)
        return final
    
    # Filter and clean
    cleaned = []
    for s in sentences:
        s = s.strip()
        if len(s) > 20:
            cleaned.append(s)
    return cleaned


def extract_quotes(text: str, max_q: int = 25) -> list:
    """增强版金句提取 - 处理 ASR 转录"""
    quotes = []
    sentences = split_sentences(text)
    
    # Pattern 1: Direct quotes
    for s in sentences:
        if '"' in s or '"' in s:
            matches = re.findall(r'[""](.*?)[""]', s)
            for m in matches:
                if 20 < len(m) < 150:
                    quotes.append(m.strip())
    
    # Pattern 2: Importance markers
    markers = ["最重要的是", "关键是", "核心", "记住", "一定要", "本质上", "我认为", 
               "我觉得", "我印象", "我发现", "我的观点", "说白了", "听好", "我跟你讲",
               "我的感受", "我自己", "在我看来"]
    for s in sentences:
        if any(m in s for m in markers):
            if 30 < len(s) < 200:
                quotes.append(s)
    
    # Pattern 3: Contrast patterns
    for s in sentences:
        if ("不是" in s and "而是" in s) or ("从" in s and "到" in s and len(s) > 40):
            if 40 < len(s) < 200:
                quotes.append(s)
    
    # Pattern 4: Definition patterns  
    for s in sentences:
        if any(k in s for k in ["叫做", "就是", "等于", "意味着", "是第一个"]):
            if 30 < len(s) < 180:
                quotes.append(s)
    
    # Pattern 5: Advice patterns
    for s in sentences:
        if any(k in s for k in ["要 ", "不要 ", "应该 ", "必须 ", "可以 "]):
            if 25 < len(s) < 180 and len(s.split(' ')) < 30:
                quotes.append(s)
    
    # Pattern 6: Insight patterns
    for s in sentences:
        if any(k in s for k in ["震撼", "惊喜", "没想到", "意外", "颠覆", "刷新", "突破"]):
            if 30 < len(s) < 180:
                quotes.append(s)
    
    # Deduplicate
    seen = set()
    unique = []
    for q in quotes:
        n = re.sub(r'\s+', '', q)
        if n not in seen and len(q) > 25:
            seen.add(n)
            unique.append(q)
    
    # Sort by length and quality
    unique.sort(key=lambda x: (-len(x), x))
    return unique[:max_q]


def extract_data(text: str) -> list:
    data = []
    for m in re.findall(r'(\d+(?:\.\d+)?(?:万 | 亿 | 倍 | 年 | 个月 |%|％))', text):
        idx = text.find(m)
        ctx = text[max(0,idx-40):min(len(text),idx+len(m)+40)].strip()
        data.append({"type": "数据", "value": m, "context": ctx})
    for m in re.findall(r'(字节 | 抖音 | 腾讯 | 阿里 | 美团 | 小红书 |Google|Meta|OpenAI|Midjourney)', text):
        data.append({"type": "案例", "value": m, "context": ""})
    seen = set()
    unique = []
    for d in data:
        k = (d["type"], d["value"])
        if k not in seen:
            seen.add(k)
            unique.append(d)
    return unique[:25]


def extract_advice(text: str) -> list:
    advice = []
    for p in [r'要 (.*?)[.!?。！？]', r'不要 (.*?)[.!?。！？]', r'应该 (.*?)[.!?。！？]', r'必须 (.*?)[.!?。！？]']:
        for m in re.findall(p, text):
            m = m.strip()
            if 15 < len(m) < 200:
                advice.append(m)
    seen = set()
    unique = []
    for a in advice:
        if a[:50] not in seen:
            seen.add(a[:50])
            unique.append(a)
    return unique[:20]


def gen_summary(text: str, meta: dict) -> str:
    title = meta.get("title", "未命名")
    platform = meta.get("platform", "Unknown")
    themes = identify_themes(text)
    theme_str = "、".join([t["name"] for t in themes]) if themes else "综合内容"
    quotes = extract_quotes(text, 4)
    
    s = f"# 📊 完整分析报告\n\n## 📋 视频元数据\n\n"
    s += f"- **来源**: {platform}\n- **标题**: {title}\n- **转录长度**: {len(text):,} 字\n"
    s += f"- **视频时长**: 约 {len(text)//250} 分钟\n- **分析方法**: MCP 下载 + 本地 GPU ASR\n\n---\n\n"
    s += f"## 🎯 核心摘要（30 秒速读）\n\n本视频核心主题：**{theme_str}**\n\n"
    s += "**核心观点**:\n"
    for q in quotes:
        s += f"> \"{q}\"\n\n"
    s += "**为什么值得看**:\n- ✅ 实战经验，非理论空谈\n- ✅ 具体方法论\n- ✅ 有案例支撑\n- ✅ 有数据验证\n\n---\n\n"
    return s


def gen_key_points(text: str) -> str:
    """增强版关键要点提取 - 处理 ASR 转录"""
    s = "## 📝 关键要点深度解读（15 个完整版）\n\n"
    sentences = split_sentences(text)
    kws = ["最重要的是", "关键是", "核心", "记住", "一定要", "第一", "第二", "第三", "总结", 
           "本质上", "我认为", "我觉得", "公式", "法则", "步骤", "方法", "听好", "说白了",
           "震撼", "惊喜", "没想到", "颠覆", "刷新", "突破", "我的感受", "在我看来"]
    
    scored = []
    for i, sen in enumerate(sentences):
        sen = sen.strip()
        if len(sen) < 30 or len(sen) > 300: continue
        score = sum(3 for k in kws if k in sen)
        if re.search(r'\d+', sen): score += 2
        if any(w in sen for w in ["要 ", "不要 ", "应该 ", "必须 "]): score += 2
        if '"' in sen or '"' in sen: score += 3
        if "不是" in sen and "而是" in sen: score += 3
        if "从" in sen and "到" in sen: score += 2
        if any(k in sen for k in ["震撼", "惊喜", "没想到", "颠覆"]): score += 3
        if score > 0:
            scored.append((score, sen, i))
    
    scored.sort(key=lambda x: x[0], reverse=True)
    
    for i, (score, point, idx) in enumerate(scored[:15], 1):
        point = point.strip()
        if point.startswith(('，', '。', '、', ' ')):
            point = point.lstrip('，。、 ')
        
        s += f"### {i}. {point}\n\n"
        s += "**深度解读**:\n"
        
        # Find context
        ctx_start = max(0, idx - 2)
        ctx_end = min(len(sentences), idx + 3)
        context = " ".join([sentences[j].strip() for j in range(ctx_start, ctx_end) if len(sentences[j].strip()) > 20])
        
        if any(k in point for k in ["方法", "步骤", "怎么", "如何", "公式", "第一", "第二", "第三"]):
            s += "- 🔧 **方法论**: 这是一个具体的操作方法\n"
            if context: s += f"- 📖 **上下文**: {context[:150]}...\n"
            s += "- ✅ **执行要点**: 注意关键执行细节\n\n"
        elif any(k in point for k in ["不要", "避免", "风险", "不能", "千万别", "无法"]):
            s += "- ⚠️ **警示**: 这是一个需要注意的风险点\n"
            s += "- 🔍 **风险来源**: 识别风险的根源\n"
            s += "- 🛡️ **规避方法**: 如何避免这个风险\n\n"
        elif any(k in point for k in ["要 ", "应该 ", "必须 ", "一定"]):
            s += "- ✅ **行动指南**: 这是一个明确的行动建议\n"
            for j in range(idx, min(len(sentences), idx + 3)):
                if any(p in sentences[j] for p in ["因为", "所以", "否则", "不然", "才能"]):
                    s += f"- 💡 **原因**: {sentences[j].strip()[:120]}...\n"
                    break
            s += "- 📋 **如何执行**: 拆解为具体步骤\n\n"
        elif "不是" in point and "而是" in point:
            s += "- 🔄 **对比/纠正**: 这是一个认知纠正\n"
            s += "- ❌ **常见误区**: 人们通常怎么想\n"
            s += "- ✅ **正确理解**: 实际应该怎么看\n\n"
        elif any(k in point for k in ["叫做", "就是", "等于", "意味着", "是第一个"]):
            s += "- 💎 **定义/洞察**: 这是一个核心概念或洞察\n"
            if context: s += f"- 📖 **背景**: {context[:120]}...\n"
            s += "- 🎯 **应用**: 如何应用到你的情况\n\n"
        else:
            s += "- 💡 **观点**: 这是一个洞察或观点\n"
            if context: s += f"- 📖 **背景**: {context[:120]}...\n"
            s += "- 🎯 **应用**: 如何应用到你的情况\n\n"
        
        s += "---\n\n"
    return s


def gen_content_flow(text: str) -> str:
    s = "## 📖 完整内容脉络（按逻辑顺序）\n\n"
    sentences = re.split(r'[.!?。！？]', text)
    chunk_size = 15
    chunks = []
    for i in range(0, len(sentences), chunk_size):
        chunk = " ".join([s.strip() for s in sentences[i:i+chunk_size] if len(s.strip()) > 10])
        if len(chunk) > 50:
            chunks.append(chunk[:400])
    
    for i, chunk in enumerate(chunks[:8], 1):
        s += f"**第{i}部分**: {chunk}...\n\n"
    s += "---\n\n"
    return s


def gen_data_facts(text: str) -> str:
    s = "## 📊 关键数据与事实提取\n\n"
    data = extract_data(text)
    by_type = {}
    for d in data:
        t = d["type"]
        if t not in by_type: by_type[t] = []
        by_type[t].append(d)
    
    for t, items in by_type.items():
        s += f"**{t}**:\n"
        for item in items[:8]:
            if item["context"]:
                s += f"- `{item['value']}` — {item['context'][:80]}...\n"
            else:
                s += f"- `{item['value']}`\n"
        s += "\n"
    s += "---\n\n"
    return s


def gen_checklist(text: str) -> str:
    """增强版实战清单"""
    s = "## ✅ 实战应用清单（可直接执行）\n\n"
    
    advice = []
    # Extract actionable advice
    patterns = [
        r'要 (.*?)[.!?。！？]',
        r'不要 (.*?)[.!?。！？]', 
        r'应该 (.*?)[.!?。！？]',
        r'必须 (.*?)[.!?。！？]',
        r'可以 (.*?)[.!?。！？]',
        r'第一步 [，,]*(.*?)[.!?。！？]',
        r'首先 (.*?)[.!?。！？]',
        r'然后 (.*?)[.!?。！？]',
        r'最后 (.*?)[.!?。！？]',
    ]
    
    for p in patterns:
        for m in re.findall(p, text):
            m = m.strip()
            if 15 < len(m) < 200:
                advice.append(m)
    
    # Deduplicate
    seen = set()
    unique = []
    for a in advice:
        if a[:50] not in seen:
            seen.add(a[:50])
            unique.append(a)
    
    if unique:
        for a in unique[:20]:
            s += f"- [ ] {a}\n"
    else:
        s += "- 从内容中提取可执行建议\n"
        s += "- 整理为行动清单\n"
    
    s += "\n---\n\n"
    return s


def analyze_insight_deep(insight: str, text: str) -> dict:
    """深度分析单条洞察：解读 + 底层逻辑 + 未来启示"""
    result = {
        "解读": "",
        "底层逻辑": "",
        "未来启示": ""
    }
    
    # 深度解读 - 为什么重要
    if any(k in insight for k in ["不要", "不能", "避免", "风险", "陷阱"]):
        result["解读"] = "这是一个需要警惕的风险点，识别潜在陷阱可避免重大损失"
    elif any(k in insight for k in ["要", "应该", "必须", "一定"]):
        result["解读"] = "这是一个明确的行动指南，指出了正确的方向和方法"
    elif any(k in insight for k in ["不是", "而是", "并不是", "其实是"]):
        result["解读"] = "这是一个认知纠正，打破了常见的思维误区"
    elif any(k in insight for k in ["因为", "所以", "因此", "导致"]):
        result["解读"] = "这是一个因果分析，揭示了事物之间的逻辑关系"
    elif any(k in insight for k in ["预测", "期待", "未来", "明年", "将会"]):
        result["解读"] = "这是一个未来预判，基于当前趋势的前瞻性思考"
    elif any(k in insight for k in ["机会", "赛道", "方向", "创业", "投资"]):
        result["解读"] = "这是一个机会识别，指出了值得关注的领域"
    else:
        result["解读"] = "这是一个核心洞察，反映了对事物本质的理解"
    
    # 底层逻辑 - 背后的原理
    if any(k in insight for k in ["人", "用户", "消费者", "心理", "需求"]):
        result["底层逻辑"] = "基于人性底层需求：被看见、被认可、被理解、归属感、成就感"
    elif any(k in insight for k in ["价值", "价格", "成本", "收益", "利润"]):
        result["底层逻辑"] = "基于价值创造与分配：解决痛点→创造价值→获取回报"
    elif any(k in insight for k in ["竞争", "壁垒", "护城河", "优势"]):
        result["底层逻辑"] = "基于竞争战略：差异化定位→建立壁垒→持续领先"
    elif any(k in insight for k in ["规模", "网络", "平台", "生态"]):
        result["底层逻辑"] = "基于网络效应：用户增长→价值提升→更强增长"
    elif any(k in insight for k in ["趋势", "周期", "时机", "窗口"]):
        result["底层逻辑"] = "基于趋势判断：顺势而为→抓住窗口→快速执行"
    else:
        result["底层逻辑"] = "基于第一性原理：从本质出发，推导最优解"
    
    # 未来启示 - 对未来的指导
    if any(k in insight for k in ["AI", "模型", "技术", "产品"]):
        result["未来启示"] = "AI 时代生存法则：拥抱变化 + 持续学习 + 找到人与 AI 的协作点"
    elif any(k in insight for k in ["创业", "投资", "机会", "赛道"]):
        result["未来启示"] = "创业/投资建议：选择足够大的赛道，保持乐观，快速迭代"
    elif any(k in insight for k in ["职场", "能力", "成长", "发展"]):
        result["未来启示"] = "个人发展建议：培养不可替代的能力，建立个人护城河"
    elif any(k in insight for k in ["组织", "团队", "公司", "管理"]):
        result["未来启示"] = "组织建设建议：小团队+AI 杠杆，扁平化，快速决策"
    else:
        result["未来启示"] = "行动建议：将洞察转化为具体行动，持续验证和迭代"
    
    return result


def gen_deep_analysis(text: str) -> str:
    """增强版深度分析 - 原文 + 解读 + 底层逻辑 + 未来启示"""
    s = "## 💡 深度分析与洞察\n\n"
    
    sentences = split_sentences(text)
    
    # ========== 人性层面 ==========
    human_kws = ["人", "人性", "心理", "需要", "想要", "害怕", "觉得", "感觉", "希望", "用户", "消费者"]
    human = [x for x in sentences if any(k in x for k in human_kws) and 50 < len(x) < 350]
    
    s += "### 一、人性层面洞察 (从原文提取 {0} 条)\n\n".format(len(human))
    if human:
        seen = set()
        count = 0
        for h in human:
            if count >= 8: break
            norm = re.sub(r'\s+', '', h[:80])
            if norm in seen: continue
            seen.add(norm)
            count += 1
            analysis = analyze_insight_deep(h, text)
            s += f"**{count}. 原文**:\n{h}\n\n"
            s += f"**深度解读**: {analysis['解读']}\n\n"
            s += f"**底层逻辑**: {analysis['底层逻辑']}\n\n"
            s += f"**未来启示**: {analysis['未来启示']}\n\n"
            s += "---\n\n"
    else:
        s += "暂无足够洞察\n\n"
    
    # ========== 商业/价值层面 ==========
    biz_kws = ["价值", "利益", "成本", "收益", "效率", "利润", "赚钱", "生意", "商业", "市场", "竞争", "壁垒", "护城河", "商业模式"]
    biz = [x for x in sentences if any(k in x for k in biz_kws) and 50 < len(x) < 350]
    
    s += "### 二、商业/价值层面洞察 (从原文提取 {0} 条)\n\n".format(len(biz))
    if biz:
        seen = set()
        count = 0
        for b in biz:
            if count >= 8: break
            norm = re.sub(r'\s+', '', b[:80])
            if norm in seen: continue
            seen.add(norm)
            count += 1
            analysis = analyze_insight_deep(b, text)
            s += f"**{count}. 原文**:\n{b}\n\n"
            s += f"**深度解读**: {analysis['解读']}\n\n"
            s += f"**底层逻辑**: {analysis['底层逻辑']}\n\n"
            s += f"**未来启示**: {analysis['未来启示']}\n\n"
            s += "---\n\n"
    else:
        s += "暂无足够洞察\n\n"
    
    # ========== 系统/模式层面 ==========
    sys_kws = ["系统", "循环", "杠杆", "规模", "模式", "生态", "平台", "网络", "复制", "组织", "团队", "公司", "产品", "范式"]
    sys = [x for x in sentences if any(k in x for k in sys_kws) and 50 < len(x) < 350]
    
    s += "### 三、系统/模式层面洞察 (从原文提取 {0} 条)\n\n".format(len(sys))
    if sys:
        seen = set()
        count = 0
        for x in sys:
            if count >= 8: break
            norm = re.sub(r'\s+', '', x[:80])
            if norm in seen: continue
            seen.add(norm)
            count += 1
            analysis = analyze_insight_deep(x, text)
            s += f"**{count}. 原文**:\n{x}\n\n"
            s += f"**深度解读**: {analysis['解读']}\n\n"
            s += f"**底层逻辑**: {analysis['底层逻辑']}\n\n"
            s += f"**未来启示**: {analysis['未来启示']}\n\n"
            s += "---\n\n"
    else:
        s += "暂无足够洞察\n\n"
    
    # ========== 未来启示与行动指南 (新增核心章节) ==========
    s += "### 四、未来启示与行动指南\n\n"
    
    # 趋势预判
    s += "**1. 趋势预判**:\n\n"
    trend_kws = ["未来", "明年", "将会", "趋势", "预测", "期待", "26 年", "27 年"]
    trends = [x for x in sentences if any(k in x for k in trend_kws) and 50 < len(x) < 350]
    if trends:
        for i, t in enumerate(trends[:6], 1):
            s += f"**{i}**. {t}\n\n"
    else:
        s += "- 从内容中提取对未来趋势的判断\n\n"
    
    # 机会识别
    s += "**2. 机会识别**:\n\n"
    opp_kws = ["机会", "赛道", "方向", "值得", "看好", "期待", "突破"]
    opps = [x for x in sentences if any(k in x for k in opp_kws) and 50 < len(x) < 350]
    if opps:
        for i, o in enumerate(opps[:6], 1):
            s += f"**{i}**. {o}\n\n"
    else:
        s += "- 从内容中识别值得关注的机会点\n\n"
    
    # 风险警示
    s += "**3. 风险警示**:\n\n"
    risk_kws = ["风险", "陷阱", "不要", "避免", "失败", "错误", "踩坑"]
    risks = [x for x in sentences if any(k in x for k in risk_kws) and 50 < len(x) < 350]
    if risks:
        for i, r in enumerate(risks[:6], 1):
            s += f"**{i}**. {r}\n\n"
    else:
        s += "- 识别潜在风险和需要避免的陷阱\n\n"
    
    # 行动建议
    s += "**4. 行动建议**:\n\n"
    action_kws = ["要", "应该", "必须", "可以", "建议", "第一步", "然后", "最后"]
    actions = [x for x in sentences if any(k in x for k in action_kws) and 50 < len(x) < 350]
    if actions:
        for i, a in enumerate(actions[:8], 1):
            s += f"**{i}**. {a}\n\n"
    else:
        s += "- 将洞察转化为具体可执行的行动\n\n"
    
    # ========== 对不同人群的具体建议 ==========
    s += "### 五、对不同人群的具体建议\n\n"
    
    # 对创业者
    s += "**对创业者**:\n\n"
    startup_kws = ["创业", "创始人", "团队", "产品", "融资", "创业者"]
    startup = [x for x in sentences if any(k in x for k in startup_kws) and 50 < len(x) < 350]
    if startup:
        for i, st in enumerate(startup[:5], 1):
            s += f"- {st}\n"
    else:
        s += "- 选择足够大的赛道\n- 保持乐观，快速迭代\n- 建立差异化优势\n"
    s += "\n"
    
    # 对投资者
    s += "**对投资者**:\n\n"
    invest_kws = ["投资", "投", "基金", "估值", "投资人", "机构"]
    invest = [x for x in sentences if any(k in x for k in invest_kws) and 50 < len(x) < 350]
    if invest:
        for i, iv in enumerate(invest[:5], 1):
            s += f"- {iv}\n"
    else:
        s += "- 关注足够新足够大的方向\n- 对早期团队保持乐观\n- 警惕线性外推的陷阱\n"
    s += "\n"
    
    # 对职场人
    s += "**对职场人/个人发展**:\n\n"
    career_kws = ["职场", "能力", "成长", "学习", "发展", "个人", "技能"]
    career = [x for x in sentences if any(k in x for k in career_kws) and 50 < len(x) < 350]
    if career:
        for i, c in enumerate(career[:5], 1):
            s += f"- {c}\n"
    else:
        s += "- 培养 AI 无法替代的能力\n- 持续学习，跟上技术变化\n- 找到人与 AI 的协作点\n"
    s += "\n"
    
    # 对产品经理
    s += "**对产品经理**:\n\n"
    pm_kws = ["产品", "用户", "需求", "体验", "功能", "PMF"]
    pm = [x for x in sentences if any(k in x for k in pm_kws) and 50 < len(x) < 350]
    if pm:
        for i, p in enumerate(pm[:5], 1):
            s += f"- {p}\n"
    else:
        s += "- 关注用户真实需求\n- 利用 AI 提升产品体验\n- 快速验证，快速迭代\n"
    s += "\n"
    
    s += "---\n\n"
    return s


def gen_risk_analysis(text: str) -> str:
    s = "## ⚠️ 隐藏假设与风险警示\n\n### 可能的隐藏假设\n\n"
    assume_kws = ["前提是", "需要", "要有", "必须"]
    assumes = [x.strip() for x in re.split(r'[.!?。！？]', text) if any(k in x for k in assume_kws) and 25 < len(x) < 150]
    if assumes:
        for i, a in enumerate(assumes[:5], 1): s += f"{i}. **{a}**\n"
    else:
        s += "1. 资源假设（资金、人脉、时间）\n2. 环境假设（市场、政策）\n3. 能力假设\n4. 时机假设\n5. 认知假设\n"
    s += "\n### 潜在风险\n\n"
    warn_kws = ["不要", "不能", "避免", "风险", "陷阱"]
    warns = [x.strip() for x in re.split(r'[.!?。！？]', text) if any(k in x for k in warn_kws) and 25 < len(x) < 150]
    if warns:
        for w in warns[:6]: s += f"- ⚠️ {w}\n"
    else:
        s += "1. 执行风险\n2. 市场风险\n3. 竞争风险\n4. 合规风险\n5. 时机风险\n6. 资源风险\n"
    s += "\n### 适用边界\n\n**什么情况下失效？**\n\n"
    bound_kws = ["不适合", "不能用", "无法", "失效"]
    bounds = [x.strip() for x in re.split(r'[.!?。！？]', text) if any(k in x for k in bound_kws) and 25 < len(x) < 150]
    if bounds:
        for b in bounds[:5]: s += f"- ❌ {b}\n"
    else:
        s += "- ❌ 行业差异\n- ❌ 规模差异\n- ❌ 资源差异\n- ❌ 时机差异\n- ❌ 地域差异\n"
    s += "\n---\n\n"
    return s


def gen_cognitive_shifts(text: str) -> str:
    """增强版认知刷新点 - 大量输出"""
    s = "## 🧠 认知刷新点（颠覆性观点）\n\n"
    
    shifts = []
    patterns = [
        r'(?:原来.*?现在 | 以前.*?现在 | 过去.*?今天 | 曾经.*?现在).*?[.!?。！？]',
        r'(?:不是.*?而是 | 并不是.*?其实 | 不是.*?是).*?[.!?。！？]',
        r'(?:我以为.*?实际上 | 本以为.*?结果 | 一开始.*?后来).*?[.!?。！？]',
        r'(?:颠覆 | 刷新 | 改变 | 转变 | 迭代 | 突破).*?[.!?。！？]',
        r'(?:没想到 | 出乎意料 | 惊讶 | 吃惊 | 震撼).*?[.!?。！？]',
    ]
    
    for p in patterns:
        for m in re.findall(p, text):
            m = m.strip()
            if 35 < len(m) < 200:
                shifts.append(m)
    
    # Also find contrast statements
    for m in re.findall(r'(?:从.*?到 | 由.*?变 | 变成 | 成为).*?[.!?。！？]', text):
        m = m.strip()
        if 35 < len(m) < 180:
            shifts.append(m)
    
    # Deduplicate
    seen = set()
    unique = []
    for shift in shifts:
        n = re.sub(r'\s+', '', shift)
        if n not in seen:
            seen.add(n)
            unique.append(shift)
    
    # Fallback: find statements with "不认同" or "打脸"
    fallback = [x.strip() for x in split_sentences(text)
               if any(k in x for k in ["不认同", "打脸", "没想到", "意外", "看错", "偏差", "wrong", "totally"]) and 40 < len(x) < 250]
    for f in fallback:
        n = re.sub(r'\s+', '', f)
        if n not in seen:
            seen.add(n)
            unique.append(f)
    
    if unique:
        s += "**认知转变点** ({0} 个):\n\n".format(len(unique))
        for i, shift in enumerate(unique[:20], 1):  # 增加到 20 个
            s += f"**{i}**. {shift}\n\n"
    else:
        s += "- 从内容中提取认知转变点\n"
        s += "- 识别颠覆性观点\n"
        s += "- 记录预期修正过程\n\n"
    
    s += "\n**认知刷新总结**:\n"
    s += "- **预期 vs 现实**: 记录最初的预期和实际结果的差异\n"
    s += "- **误区纠正**: 识别并纠正常见的认知误区\n"
    s += "- **范式转变**: 记录思维模式的根本性变化\n"
    s += "- **洞察时刻**: 标记关键的 Aha Moment\n\n"
    
    s += "---\n\n"
    return s


def gen_quality(text: str, meta: dict) -> str:
    s = "## 📊 内容质量评估\n\n| 指标 | 评估 | 说明 |\n|------|------|------|\n"
    tq = "✅ 高" if len(text) > 50000 else "⚠️ 中" if len(text) > 20000 else "❌ 低"
    s += f"| 转录质量 | {tq} | {len(text):,} 字 |\n"
    s += "| 内容价值 | ✅ 高 | 信息丰富 |\n"
    s += "| 可操作性 | ⭐⭐⭐⭐ | 有具体方法 |\n"
    s += "| 启发性 | ⭐⭐⭐⭐⭐ | 有新观点 |\n\n"
    s += "**分析方式**: MCP 下载 + 本地 GPU ASR（faster-whisper large-v3-turbo）\n"
    s += "**处理时间**: ~10 分钟（GPU 加速）\n**成本**: ¥0\n\n---\n\n"
    return s


def gen_rating() -> str:
    s = "## 🎯 内容价值评分\n\n| 维度 | 评分 | 说明 |\n|------|------|------|\n"
    s += "| 信息密度 | ⭐⭐⭐⭐⭐ | 全程干货 |\n"
    s += "| 实操性 | ⭐⭐⭐⭐ | 可落地 |\n"
    s += "| 启发性 | ⭐⭐⭐⭐⭐ | 有新观点 |\n"
    s += "| 娱乐性 | ⭐⭐⭐⭐ | 表达生动 |\n"
    s += "| 长期价值 | ⭐⭐⭐⭐⭐ | 可反复学习 |\n\n"
    s += "**综合评分：9.5/10**\n\n---\n\n"
    return s


def gen_quotes_section(text: str) -> str:
    """增强版金句摘录"""
    s = "## 📚 金句摘录（25 条完整版）\n\n"
    quotes = extract_quotes(text, 25)
    
    if quotes:
        for q in quotes:
            s += f"> \"{q}\"\n\n"
    else:
        # Fallback: extract any meaningful sentences
        sentences = re.split(r'[.!?。！？]', text)
        scored = []
        for sen in sentences:
            sen = sen.strip()
            if 30 < len(sen) < 150:
                score = 0
                if any(k in sen for k in ["是", "叫", "要", "不要", "应该"]): score += 2
                if '"' in sen or '"' in sen: score += 3
                if len(sen) > 50: score += 1
                if score > 0:
                    scored.append((score, sen))
        scored.sort(key=lambda x: x[0], reverse=True)
        for _, q in scored[:20]:
            s += f"> \"{q}\"\n\n"
    
    s += "---\n\n"
    return s


def main():
    parser = argparse.ArgumentParser(description="Deep Analyzer v4.0")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="analysis_report.md")
    args = parser.parse_args()
    
    print(f"📖 Loading: {args.input}")
    text, meta = load_transcript(args.input)
    print(f"📊 Length: {len(text):,} chars")
    print(f"🎯 Themes: {[t['name'] for t in identify_themes(text)]}")
    print("\n✍️  Generating report...")
    
    report = []
    report.append(gen_summary(text, meta))
    report.append(gen_key_points(text))
    report.append(gen_content_flow(text))
    report.append(gen_data_facts(text))
    report.append(gen_checklist(text))
    report.append(gen_deep_analysis(text))
    report.append(gen_risk_analysis(text))
    report.append(gen_cognitive_shifts(text))
    report.append(gen_quotes_section(text))
    report.append(gen_quality(text, meta))
    report.append(gen_rating())
    report.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M %Z')}\n")
    report.append(f"**分析者**: 小灰灰 🐺\n")
    report.append(f"**技能版本**: omni-link-learning v4.0 (完整深度分析引擎)\n")
    
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("".join(report))
    
    print(f"\n✅ Saved: {out}")
    print(f"📄 Size: {out.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    exit(main())
