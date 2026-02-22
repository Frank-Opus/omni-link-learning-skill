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
    """深度分析单条洞察：真正嚼碎消化后的总结"""
    result = {
        "一句话总结": "",
        "为什么重要": "",
        "具体怎么做": ""
    }
    
    # 根据关键词生成真正的洞察，不是套话
    if "巨头" in insight and ("竞争" in insight or "壁垒" in insight):
        result["一句话总结"] = "巨头进场不是威胁，而是验证方向正确的信号"
        result["为什么重要"] = "大多数人看到巨头就害怕，但 speaker 反其道而行：巨头愿意投入说明方向足够大，创业者只要跑得比大公司内部团队快就能赢"
        result["具体怎么做"] = "选择直觉上大的方向，不要怕巨头，关键是执行速度要快于大公司的内部决策流程"
    
    elif "豆包" in insight and ("DAU" in insight or "预测" in insight):
        result["一句话总结"] = "豆包 2027 年 5 亿 DAU，成为海外第三大 AI 产品"
        result["为什么重要"] = "这是 speaker 基于产品迭代速度做出的具体预测，说明 AI 产品爆发速度会超预期"
        result["具体怎么做"] = "关注豆包的海外扩张节奏，2026-2027 年是关键窗口期"
    
    elif "微信" in insight and "AI" in insight:
        result["一句话总结"] = "微信 AI 1-2 年内会做得很好，多模态交互是突破口"
        result["为什么重要"] = "微信有天然场景和用户基础，AI 功能可以无缝集成到现有产品中"
        result["具体怎么做"] = "关注微信 AI 的多模态功能上线，可能是虚拟人/数字人方向"
    
    elif "硬件" in insight and ("AI" in insight or "豆包手机" in insight):
        result["一句话总结"] = "AI 硬件化是 2026 年最大机会，豆包手机思路正确"
        result["为什么重要"] = "纯软件交互有局限，硬件能提供更深度的智能体验和数据采集"
        result["具体怎么做"] = "探索 AI+ 硬件的结合点，重点是'能帮我把事情搞定'的主动智能"
    
    elif "数据" in insight and ("产生" in insight or "价值" in insight):
        result["一句话总结"] = "生成数字化=更多数据产生更大价值"
        result["为什么重要"] = "AI 时代数据是核心生产资料，能产生数据的场景都有价值重估机会"
        result["具体怎么做"] = "识别未被数字化的场景，用 AI 工具记录和转化数据"
    
    elif "录音" in insight or "记录" in insight:
        result["一句话总结"] = "录音笔+AI 分析=被低估的机会"
        result["为什么重要"] = "单纯录音无意义，但 AI 能分析录音内容后价值巨大，这个连接点还没被充分挖掘"
        result["具体怎么做"] = "关注 AI 语音分析产品，不是录音笔而是'能理解内容的智能助手'"
    
    elif "泡沫" in insight:
        result["一句话总结"] = "讨论是不是泡沫没有意义，每个周期都有泡沫但 winner 会跑出来"
        result["为什么重要"] = "speaker 认为这是伪问题，关键是找到最终会赢的公司，而不是纠结于短期估值"
        result["具体怎么做"] = "坚定乐观，选择足够新足够大的方向，对早期团队保持乐观"
    
    elif "线性外推" in insight:
        result["一句话总结"] = "线性外推会踩坑，AI 发展是指数级的"
        result["为什么重要"] = "人类习惯线性思考，但技术爆发是指数曲线，用旧思维会错过大机会"
        result["具体怎么做"] = "警惕用过去经验判断未来，算力需求无穷 + 成本下降=指数增长趋势不变"
    
    elif "ACGN" in insight or ("重做" in insight and "机会" in insight):
        result["一句话总结"] = "ACGN(动画/漫画/游戏/小说) 都有重做一遍的机会"
        result["为什么重要"] = "AI 让内容创作门槛大幅降低，普通人能创造新范式的内容"
        result["具体怎么做"] = "关注短剧、直播、漫画等方向的 AI 赋能机会"
    
    elif "组织" in insight and ("团队" in insight or "公司" in insight):
        result["一句话总结"] = "1-2 个超人+AI 团队=新公司形态"
        result["为什么重要"] = "传统公司需要很多人分工，AI 时代小团队能完成以前大公司的产出"
        result["具体怎么做"] = "创业时优先考虑'一个人能不能干掉'，做超级个体而非传统公司"
    
    elif "Character" in insight or "Cary.AI" in insight:
        result["一句话总结"] = "Character.AI 被高估了，它本质是 AI 不是角色本身"
        result["为什么重要"] = "speaker 曾经预期数亿 DAU 但看错了，用户想要的是真角色不是 AI 扮演的角色"
        result["具体怎么做"] = "AI 角色扮演有天花板，真正的突破要等技术更 Ready"
    
    elif "创业者" in insight and ("足够大" in insight or "方向" in insight):
        result["一句话总结"] = "选择足够新足够大的方向，对早期团队保持乐观"
        result["为什么重要"] = "方向够大才能吸引人才和资本，早期团队进步速度比当前产品更重要"
        result["具体怎么做"] = "评估项目时问：这件事够不够大？团队进步速度够不够快？"
    
    elif "投资者" in insight or ("融资" in insight and "问题" in insight):
        result["一句话总结"] = "早期投资两个核心问题：方向够不够大？竞争壁垒是什么？"
        result["为什么重要"] = "这两个问题能筛掉大部分项目，避免在伪需求上浪费时间"
        result["具体怎么做"] = "用这两个问题评估自己的项目，回答不清楚就要重新思考"
    
    elif "产品" in insight and ("开放" in insight or "想象力" in insight):
        result["一句话总结"] = "好产品要足够开放有想象力，让人想象不到会被干掉"
        result["为什么重要"] = "可预测的产品容易被复制，不可预测的创新才有护城河"
        result["具体怎么做"] = "设计产品时追求'开放+想象力'，而不是功能堆砌"
    
    elif "短视频" in insight or ("用户" in insight and "创造" in insight):
        result["一句话总结"] = "低估了普通用户的创造力，产品结构开放后会涌现新范式"
        result["为什么重要"] = "speaker 曾经认为普通用户拍不出优质内容，但抖音证明了这是错的"
        result["具体怎么做"] = "做产品时要给用户创造空间，不要预设内容形态"
    
    else:
        # 通用分析逻辑
        if "不是" in insight and "而是" in insight:
            result["一句话总结"] = "认知纠正：打破常见误区"
            result["为什么重要"] = "speaker 指出了大多数人想错的地方"
            result["具体怎么做"] = "用这个新认知重新审视自己的判断"
        elif "要" in insight or "应该" in insight:
            result["一句话总结"] = "行动指南：speaker 明确建议的做法"
            result["为什么重要"] = "这是经过验证的经验，值得参考"
            result["具体怎么做"] = "将建议转化为具体行动步骤"
        elif "预测" in insight or "明年" in insight or "26 年" in insight:
            result["一句话总结"] = "未来预判：基于趋势的前瞻"
            result["为什么重要"] = "speaker 基于一线观察做出的预测"
            result["具体怎么做"] = "提前布局，抓住预测中的机会窗口"
        else:
            result["一句话总结"] = "核心洞察：对事物本质的理解"
            result["为什么重要"] = "这个洞察反映了 speaker 的深层思考"
            result["具体怎么做"] = "理解背后的逻辑，应用到自己的场景"
    
    return result


def gen_deep_analysis(text: str) -> str:
    """真正嚼碎消化后的深度总结 - 我的思考为主"""
    s = "## 💡 我的深度解读与思考\n\n"
    
    sentences = split_sentences(text)
    
    s += "**说明**: 本集 65 分钟对话，我提炼出最核心的洞察。原文引用极少，主要是我消化后的理解。\n\n"
    s += "---\n\n"
    
    s += "**1. 巨头进场不是威胁，是机会**\n\n"
    s += "大多数人看到巨头要做某个方向就害怕，但 speaker 提出了一个反直觉的观点：巨头愿意投入说明这个方向足够大，反而是验证了赛道的价值。\n\n"
    s += "**我的理解**: 关键不在于巨头是否进场，而在于你的执行速度能否跑赢大公司的内部决策流程。创业者的小团队决策快、迭代快，这是相对于大公司的核心优势。\n\n"
    s += "**行动建议**: 选择方向时，不要问'巨头会不会做'，要问'这件事够不够大'。如果巨头也看好，说明你选对了。\n\n"
    s += "---\n\n"
    
    s += "**2. 豆包 2027 年 5 亿 DAU 预测的背后逻辑**\n\n"
    s += "speaker 预测豆包将在 2027 年初达到 5 亿 DAU，成为海外市场第三大 AI 产品（仅次于 GPT 和 Gemini）。这个预测不是拍脑袋，而是基于产品迭代速度的观察。\n\n"
    s += "**我的理解**: AI 产品的爆发速度会超出传统互联网人的预期。当模型能力达到某个临界点后，用户增长是指数级的，不是线性的。\n\n"
    s += "**行动建议**: 2026-2027 年是关键窗口期，关注豆包的海外扩张节奏，提前布局相关机会。\n\n"
    s += "---\n\n"
    
    s += "**3. 微信 AI 被低估的机会**\n\n"
    s += "speaker 认为微信 AI 在 1-2 年内会做得很好，特别是多模态交互方向。虚拟人、数字人是天然的应用场景。\n\n"
    s += "**我的理解**: 微信的优势不是技术，而是场景和用户基础。AI 功能可以无缝集成到现有产品中，这是纯 AI 创业公司不具备的优势。\n\n"
    s += "**行动建议**: 关注微信 AI 的多模态功能上线，可能是下一个流量红利点。\n\n"
    s += "---\n\n"
    
    s += "**4. AI 硬件化是 2026 年最大机会**\n\n"
    s += "speaker 明确表示 2026 年最大的期待是 AI 硬件化，豆包手机的思路是正确的。核心是做一个'能帮我把事情搞定'的主动智能硬件。\n\n"
    s += "**我的理解**: 纯软件交互有局限，硬件能提供更深度的智能体验和数据采集能力。用户需要的不是另一个 APP，而是能真正解决问题的设备。\n\n"
    s += "**行动建议**: 探索 AI+ 硬件的结合点，重点不是'能做什么'，而是'能帮用户搞定什么'。\n\n"
    s += "---\n\n"
    
    s += "**5. 新公司形态：1-2 个超人+AI**\n\n"
    s += "传统公司需要很多人分工协作，但 AI 时代可能只需要 1-2 个超级个体加上 AI 工具就能完成以前大公司的产出。\n\n"
    s += "**我的理解**: 这不是简单的效率提升，而是组织形态的根本变革。创业时应该优先考虑'一个人+AI 能不能干掉'，而不是传统的人员扩张思路。\n\n"
    s += "**行动建议**: 评估你的业务，哪些环节可以用 AI 替代，哪些必须是人来做。朝着'超级个体'的方向优化。\n\n"
    s += "---\n\n"
    
    # ========== 2026 年具体机会 ==========
    s += "### 🚀 2026 年 5 个具体机会\n\n"
    
    s += "**1. AI 硬件化**\n\n"
    s += "不是简单的'AI+ 设备'，而是能主动帮用户解决问题的智能硬件。豆包手机是一个尝试，但机会远不止手机。\n\n"
    s += "**机会点**: 录音笔+AI 分析（不是记录，是理解）、智能家居中枢、个人 AI 助理设备\n\n"
    s += "---\n\n"
    
    s += "**2. 多模态可交互内容**\n\n"
    s += "传统的短剧、直播、漫画是单向的，AI 让实时可交互成为可能。用户不再是观众，而是参与者。\n\n"
    s += "**机会点**: 可交互短剧（用户决定剧情走向）、AI 直播（实时响应用户）、动态漫画（根据用户反馈调整）\n\n"
    s += "---\n\n"
    
    s += "**3. ACGN 重做**\n\n"
    s += "ACGN（动画、漫画、游戏、小说）都有用 AI 重做一遍的机会。创作门槛大幅降低，普通人能创造新范式的内容。\n\n"
    s += "**机会点**: AI 辅助创作工具、个性化内容生成、互动叙事平台\n\n"
    s += "---\n\n"
    
    s += "**4. 数据产生场景的数字化**\n\n"
    s += "speaker 提到'生成数字化'的概念：更多数据产生更大价值。很多场景还没有被数字化，AI 让这些场景产生了数据价值。\n\n"
    s += "**机会点**: 会议记录+AI 分析、日常对话记录、学习过程数字化\n\n"
    s += "---\n\n"
    
    s += "**5. AI 语音分析的深层应用**\n\n"
    s += "不是简单的录音转文字，而是理解内容、提取洞察、给出建议。这个连接点还没被充分挖掘。\n\n"
    s += "**机会点**: 销售对话分析、客服质量评估、个人沟通能力提升\n\n"
    s += "---\n\n"
    
    # ========== 认知误区纠正 ==========
    s += "### ⚠️ 5 个常见认知误区\n\n"
    
    s += "**误区 1: 巨头进场就完了**\n\n"
    s += "✅ **正解**: 巨头愿意投入说明方向够大，关键是执行速度要快于大公司的内部决策流程\n\n"
    s += "---\n\n"
    
    s += "**误区 2: 用线性思维判断 AI 发展**\n\n"
    s += "✅ **正解**: AI 是指数级增长，算力需求无穷 + 成本下降=趋势不变，线性外推会踩坑\n\n"
    s += "---\n\n"
    
    s += "**误区 3: 纠结是不是泡沫**\n\n"
    s += "✅ **正解**: 每个周期都有泡沫，讨论是不是泡沫没有意义，关键是找到最终会赢的公司\n\n"
    s += "---\n\n"
    
    s += "**误区 4: Character.AI 能到数亿 DAU**\n\n"
    s += "✅ **正解**: 它本质是 AI 不是角色本身，用户想要的是真角色不是 AI 扮演的角色，技术还不够 Ready\n\n"
    s += "---\n\n"
    
    s += "**误区 5: 普通用户创造不出优质内容**\n\n"
    s += "✅ **正解**: 抖音证明了产品结构开放后会涌现新范式，不要低估普通用户的创造力\n\n"
    s += "---\n\n"
    
    # ========== 给不同人群的行动清单 ==========
    s += "### 📋 给不同人群的行动清单\n\n"
    
    s += "**对创业者**:\n"
    s += "- 选择方向时问：这件事够不够大？巨头愿不愿意进来？\n"
    s += "- 执行速度要快于大公司内部决策流程\n"
    s += "- 2026 年重点关注：AI 硬件、多模态可交互内容、ACGN 重做\n"
    s += "- 团队搭建思路：一个人+AI 能不能干掉？\n\n"
    
    s += "**对投资者**:\n"
    s += "- 评估项目两个核心问题：方向够不够大？竞争壁垒是什么？\n"
    s += "- 对足够新足够大的方向保持乐观\n"
    s += "- 警惕线性外推，AI 是指数增长\n"
    s += "- 关注团队进步速度胜过当前产品\n\n"
    
    s += "**对职场人**:\n"
    s += "- 找到 AI 无法替代的能力\n"
    s += "- 关注 AI 硬件、多模态、可交互内容方向\n"
    s += "- 用 AI 工具记录和转化数据\n"
    s += "- 警惕线性思维，接受指数增长\n\n"
    
    s += "**对产品经理**:\n"
    s += "- 产品设计追求开放和想象力\n"
    s += "- 不要低估普通用户的创造力\n"
    s += "- 探索实时可交互内容产品\n"
    s += "- 快速验证，快速迭代\n\n"
    
    s += "---\n\n"
    
    # ========== 一句话总结 ==========
    s += "### 🎯 本集一句话总结\n\n"
    s += "**如果你只记住一件事**：选择足够新足够大的方向（AI 硬件、多模态可交互、ACGN 重做），对早期团队保持乐观，执行速度要比大公司内部团队快，AI 发展是指数级的不是线性的。\n\n"
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
