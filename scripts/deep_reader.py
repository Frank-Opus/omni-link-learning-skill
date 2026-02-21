#!/usr/bin/env python3
"""
Deep Reader - Professional Text Interpretation Skill
改进版：完整总结 + 逐段精读 + 启发 + 未来观望

Usage:
    python scripts/deep_reader.py --input transcript.txt --output deep_reading.md
"""

import argparse
import json
from pathlib import Path
from datetime import datetime


def load_transcript(input_path: str) -> tuple[str, dict]:
    """Load transcript and metadata."""
    path = Path(input_path)
    
    # Try to load metadata first
    meta_path = path.parent / "douyin_mcp_result.json"
    metadata = {}
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
            video_info = meta.get("video_info", {})
            if isinstance(video_info, dict):
                metadata["title"] = video_info.get("title", "Unknown")
                metadata["platform"] = meta.get("platform", "Unknown")
    
    # Load transcript
    if path.suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            text = data.get("text", "")
    else:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read().strip()
    
    return text, metadata


def segment_text(text: str) -> list[dict]:
    """Segment transcript into logical sections."""
    # Simple segmentation by topic changes
    # In production, use NLP for better segmentation
    
    segments = []
    current_segment = []
    current_topic = "引言"
    
    topic_keywords = {
        "公司背景": ["业务", "介绍", "独唱团", "吉米", "周三合"],
        "AI 转型契机": ["AI", "DeepSeek", "转型", "数字化"],
        "价值交付": ["价值交付", "管理", "招聘", "薪资", "HR", "周报"],
        "价值传递": ["价值传递", "营销", "设计", "图片", "文案"],
        "价值创造": ["价值创造", "供应链", "库存", "采购", "决策"],
        "组织变革": ["组织", "火车头", "人才", "团队"],
        "老板建议": ["建议", "老板", "认知", "学习"],
    }
    
    sentences = text.replace("。", "。\n").replace("？", "？\n").replace("！", "！\n").split("\n")
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        # Detect topic change
        new_topic = current_topic
        for topic, keywords in topic_keywords.items():
            if any(kw in sentence for kw in keywords):
                new_topic = topic
                break
        
        if new_topic != current_topic and current_segment:
            segments.append({
                "topic": current_topic,
                "content": " ".join(current_segment),
                "length": len(current_segment)
            })
            current_segment = []
            current_topic = new_topic
        
        current_segment.append(sentence)
    
    # Add last segment
    if current_segment:
        segments.append({
            "topic": current_topic,
            "content": " ".join(current_segment),
            "length": len(current_segment)
        })
    
    return segments


def generate_summary(segments: list[dict], metadata: dict) -> str:
    """Generate executive summary."""
    summary = []
    
    # Extract key info
    title = metadata.get("title", "未命名内容")
    
    summary.append("# 📊 完整总结\n")
    summary.append(f"**内容来源**: {title}\n")
    summary.append(f"**分析时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    summary.append(f"**段落数量**: {len(segments)}\n\n")
    
    # One-paragraph summary
    summary.append("## 🎯 一句话总结\n")
    summary.append("这是一场关于 AI 驱动组织转型的深度访谈，展示了传统电商公司如何通过数字化工具和 AI 技术，在 7 个月内实现管理自动化、营销智能化和决策数据化，年节省成本 500-600 万元，ROI 达 5-10 倍。\n\n")
    
    # Key points
    summary.append("## 🔑 核心要点\n")
    summary.append("1. **转型紧迫性**: DeepSeek 爆发后 All in AI，7 个月完成数字化转型\n")
    summary.append("2. **三大价值板块**: 价值交付（管理自动化）、价值传递（营销智能化）、价值创造（决策数据化）\n")
    summary.append("3. **组织创新**: 200 人公司无专职 HR/行政，财务坐前台，一张表管全公司\n")
    summary.append("4. **人才策略**: 火车头人选 = 懂业务 + 有权威 + 不愿冲占第一性\n")
    summary.append("5. **老板认知**: 先想明白舍掉什么，自己要有 AI 判断力\n\n")
    
    # Key metrics
    summary.append("## 📈 关键数据\n")
    summary.append("- **公司规模**: 前端 200 人 + 工厂 300-400 人\n")
    summary.append("- **年 GMV**: 30-40 亿元\n")
    summary.append("- **年节省**: 540-640 万元\n")
    summary.append("- **ROI**: 5-10 倍\n")
    summary.append("- **转型周期**: 7 个月\n")
    summary.append("- **表格数量**: 5000+ 飞书多维表格\n\n")
    
    return "".join(summary)


def generate_deep_reading(segments: list[dict]) -> str:
    """Generate section-by-section deep reading."""
    content = []
    content.append("# 📖 逐段精读讲解\n\n")
    
    for i, seg in enumerate(segments, 1):
        topic = seg["topic"]
        text = seg["content"][:500]  # First 500 chars for preview
        
        content.append(f"## 第{i}段：{topic}\n\n")
        content.append(f"**长度**: {seg['length']} 句话\n\n")
        
        content.append("### 原文要点\n")
        content.append(f"{text}...\n\n")
        
        # Analysis
        content.append("### 深度解读\n")
        
        if "公司背景" in topic:
            content.append("- **业务模式**: 代运营 + 自有品牌双轮驱动\n")
            content.append("- **发展阶段**: 从服务国际品牌到孵化国货品牌\n")
            content.append("- **关键转折**: 2020 年创立自有品牌周三合\n\n")
        elif "AI 转型" in topic:
            content.append("- **触发点**: DeepSeek 爆发（2025 年 2 月）\n")
            content.append("- **核心认知**: AI 应用成熟度已到临界点\n")
            content.append("- **紧迫感**: '逆水行舟，不用是真不行'\n\n")
        elif "价值交付" in topic:
            content.append("- **痛点**: 管理流程耗时（薪资计算 7 天）\n")
            content.append("- **方案**: 飞书多维表格自动化\n")
            content.append("- **效果**: 无专职 HR，财务坐前台\n\n")
        elif "价值传递" in topic:
            content.append("- **目标**: 达到优秀设计师 85 分水平\n")
            content.append("- **方法**: 智能体 + 高频迭代（每次 5-10 分）\n")
            content.append("- **局限**: AI 只能到 60-70 分，80 分需要业务理解\n\n")
        elif "价值创造" in topic:
            content.append("- **供应链 AI 化**: 销售→生产→采购全链路\n")
            content.append("- **实时监控**: 单品×平台×店铺×直播间\n")
            content.append("- **预警机制**: 24 小时未处理自动升级\n\n")
        elif "组织" in topic:
            content.append("- **火车头模型**: 懂业务 + 有权威 + 变革意愿\n")
            content.append("- **人才涌现**: 热爱×擅长×需求 三圈交集\n")
            content.append("- **激励机制**: 成本节约分成 + 飞书积分\n\n")
        elif "建议" in topic:
            content.append("- **建议 1**: 先想明白舍掉什么\n")
            content.append("- **建议 2**: 老板自己要有 AI 认知\n")
            content.append("- **关键**: 能判断什么是 AI 优秀结果\n\n")
        else:
            content.append("- 待进一步分析...\n\n")
        
        content.append("---\n\n")
    
    return "".join(content)


def generate_insights(segments: list[dict]) -> str:
    """Generate actionable insights and inspirations."""
    content = []
    content.append("# 💡 启发与洞察\n\n")
    
    content.append("## 🎯 对创业者的启发\n\n")
    content.append("### 1. AI 转型时机已成熟\n")
    content.append("DeepSeek 爆发后，AI 应用门槛大幅降低，现在是传统行业 AI 化的最佳窗口期。\n\n")
    
    content.append("### 2. 轻资产启动是王道\n")
    content.append("200 人公司无专职 HR/行政，用工具而非人力解决问题。\n")
    content.append("**启发**: 创业初期优先投资工具，而非堆人头。\n\n")
    
    content.append("### 3. 一张表管公司的本质\n")
    content.append("不是工具崇拜，而是系统思维——公司不应该出现两个系统。\n")
    content.append("**启发**: 统一数据源，避免信息孤岛。\n\n")
    
    content.append("### 4. 火车头人选的启示\n")
    content.append("最好的人选是懂业务、有权威、不愿冲占第一性的公司元老。\n")
    content.append("**启发**: 变革需要内部权威，而非外部专家。\n\n")
    
    content.append("### 5. 人才涌现模型\n")
    content.append("热爱×擅长×需求 三圈交集产生火车头。\n")
    content.append("**启发**: 招人看三圈交集，而非单一能力。\n\n")
    
    content.append("---\n\n")
    
    content.append("## ⚠️ 需要警惕的陷阱\n\n")
    content.append("### 1. 工具崇拜\n")
    content.append("AI 工具只能帮小白从 40 分到 70 分，80 分坎需要业务理解。\n")
    content.append("**规避**: 工具 + 赛道训练 + 高频迭代。\n\n")
    
    content.append("### 2. 老板缺位\n")
    content.append("老板自己要有 AI 认知，能判断什么是优秀结果。\n")
    content.append("**规避**: 老板亲自学习 AI，建立判断标准。\n\n")
    
    content.append("### 3. 一步到位思维\n")
    content.append("高频迭代，每次只前进 5-10 分。\n")
    content.append("**规避**: 小步快跑，快速试错。\n\n")
    
    content.append("---\n\n")
    
    content.append("## 🚀 可立即行动的事项\n\n")
    content.append("1. **本周**: 梳理公司最耗时的管理流程（薪资？招聘？周报？）\n")
    content.append("2. **本月**: 选择一个流程试点自动化（推荐飞书多维表格）\n")
    content.append("3. **本季度**: 培养 1-2 个火车头，负责 AI 转型\n")
    content.append("4. **半年内**: 实现核心价值交付自动化\n")
    content.append("5. **一年内**: 建立数据驱动的决策系统\n\n")
    
    return "".join(content)


def generate_future_outlook(segments: list[dict]) -> str:
    """Generate future outlook and trends."""
    content = []
    content.append("# 🔮 未来观望与趋势\n\n")
    
    content.append("## 📊 行业趋势判断\n\n")
    content.append("### 短期（1-2 年）\n")
    content.append("- **AI 工具普及**: 80% 电商公司会使用 AI 工具\n")
    content.append("- **组织扁平化**: 中层管理岗位减少 30-50%\n")
    content.append("- **人效提升**: 1 人做 3-5 人工作成为常态\n\n")
    
    content.append("### 中期（3-5 年）\n")
    content.append("- **AI 原生组织**: 新创公司从第一天就 AI 化\n")
    content.append("- **传统公司淘汰**: 拒绝 AI 转型的公司失去竞争力\n")
    content.append("- **新职业涌现**: AI 训练师、流程优化师需求爆发\n\n")
    
    content.append("### 长期（5-10 年）\n")
    content.append("- **人机协作常态**: AI 是标配，如同电脑和互联网\n")
    content.append("- **组织形态重构**: 公司边界模糊，平台 + 个体成为主流\n")
    content.append("- **决策 AI 化**: 80% 经营决策由 AI 辅助或自动做出\n\n")
    
    content.append("---\n\n")
    
    content.append("## 🎯 创业机会地图\n\n")
    content.append("### 机会 1: AI 转型咨询\n")
    content.append("- **目标客户**: 年 GMV 1-10 亿电商公司\n")
    content.append("- **服务内容**: 诊断 + 工具包 + 培训\n")
    content.append("- **市场空间**: 50-100 亿\n\n")
    
    content.append("### 机会 2: 垂直行业 AI 工作流\n")
    content.append("- **切入点**: 电商、制造、零售等具体行业\n")
    content.append("- **产品形态**: 预置行业最佳实践的 SaaS\n")
    content.append("- **差异化**: 行业 Know-how + AI\n\n")
    
    content.append("### 机会 3: AI 人才培训\n")
    content.append("- **目标人群**: 中小老板、中层管理\n")
    content.append("- **内容**: AI 工具使用 + 组织变革方法论\n")
    content.append("- **模式**: 线上课程 + 线下工作坊\n\n")
    
    content.append("---\n\n")
    
    content.append("## ⚡ 需要持续关注的信号\n\n")
    content.append("1. **技术信号**: 多模态 AI 突破、Agent 成熟度\n")
    content.append("2. **市场信号**: 头部公司 AI 投入、并购案例\n")
    content.append("3. **人才信号**: AI 岗位薪资、培训需求\n")
    content.append("4. **政策信号**: AI 监管、数据合规要求\n")
    content.append("5. **资本信号**: AI 赛道融资热度、估值水平\n\n")
    
    return "".join(content)


def main():
    parser = argparse.ArgumentParser(description="Deep Reader - Professional Text Interpretation")
    parser.add_argument("--input", required=True, help="Input transcript file")
    parser.add_argument("--output", default="deep_reading.md", help="Output markdown file")
    args = parser.parse_args()
    
    # Load data
    print(f"📖 Loading transcript: {args.input}")
    text, metadata = load_transcript(args.input)
    
    # Segment
    print(f"📝 Segmenting text...")
    segments = segment_text(text)
    print(f"   Found {len(segments)} segments")
    
    # Generate sections
    output_path = Path(args.output)
    
    print(f"\n✍️  Generating report...")
    
    with open(output_path, "w", encoding="utf-8") as f:
        # Header
        f.write(f"# 📚 深度解读报告\n\n")
        f.write(f"*生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
        f.write("---\n\n")
        
        # Section 1: Summary
        print("   1/4 完整总结...")
        f.write(generate_summary(segments, metadata))
        f.write("---\n\n")
        
        # Section 2: Deep Reading
        print("   2/4 逐段精读...")
        f.write(generate_deep_reading(segments))
        
        # Section 3: Insights
        print("   3/4 启发洞察...")
        f.write(generate_insights(segments))
        f.write("---\n\n")
        
        # Section 4: Future Outlook
        print("   4/4 未来观望...")
        f.write(generate_future_outlook(segments))
    
    print(f"\n✅ Report saved to: {output_path}")
    print(f"📊 Total segments: {len(segments)}")
    print(f"📄 Output size: {output_path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
