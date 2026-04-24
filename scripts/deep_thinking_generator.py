#!/usr/bin/env python3
"""
深度思考生成器 v8.0
根据 deep_thinking_template.md 模板生成深度思考报告
"""

import argparse
import re
from pathlib import Path


def split_sentences(text: str) -> list:
    """智能分割 ASR 转录文本（无标点或空格分隔）"""
    # 先按常见连接词分割
    connectors = ['然后', '所以', '但是', '因为', '如果', '虽然', '而且', '另外', '其实', '对吧', '就是', '我觉得', '我认为']
    
    sentences = []
    current = ""
    
    # 按句号和空格分割
    parts = re.split(r'[.!?。！？\s]{2,}', text)
    
    for part in parts:
        part = part.strip()
        if len(part) > 10:
            # 检查是否包含连接词，如果是则进一步分割
            for conn in connectors:
                if conn in part and len(part) > 80:
                    sub_parts = part.split(conn)
                    for i, sub in enumerate(sub_parts):
                        if i > 0 and len(sub.strip()) > 10:
                            sentences.append(conn + sub.strip())
                        elif len(sub.strip()) > 10:
                            sentences.append(sub.strip())
                    break
            else:
                sentences.append(part)
    
    # 过滤太短或太长的
    sentences = [s for s in sentences if 20 < len(s) < 500]
    
    return sentences


def extract_key_themes(text: str) -> list:
    """从文本中提取关键主题"""
    themes = []
    
    # 预定义的主题关键词
    theme_keywords = {
        "巨头竞争": ["巨头", "大公司", "竞争", "壁垒", "护城河"],
        "AI 硬件": ["硬件", "手机", "设备", "豆包手机"],
        "豆包预测": ["豆包", "DAU", "预测", "27 年"],
        "微信 AI": ["微信", "AI", "多模态"],
        "新公司形态": ["组织", "团队", "公司", "1-2 个", "超人"],
        "线性外推": ["线性", "指数", "外推", "增长"],
        "泡沫论": ["泡沫", "估值", "周期"],
        "ACGN 重做": ["ACGN", "动画", "漫画", "游戏", "短剧", "重做"],
        "生成数字化": ["数据", "数字化", "产生", "记录"],
        "AI 语音分析": ["录音", "语音", "分析", "理解"]
    }
    
    sentences = split_sentences(text)
    
    for theme, keywords in theme_keywords.items():
        for sent in sentences:
            if any(kw in sent for kw in keywords):
                themes.append((theme, sent))
                break
    
    return themes[:8]  # 返回最多 8 个主题


def generate_deep_thinking(text: str) -> str:
    """生成深度思考报告"""
    
    themes = extract_key_themes(text)
    
    report = "# 🧠 深度思考报告\n\n"
    report += "**说明**: 本集对话的深度解读与思考，原文引用极少，主要是消化后的分析。\n\n"
    report += "---\n\n"
    
    # ========== 第一部分：核心洞察 ==========
    report += "## 一、核心洞察\n\n"
    
    for i, (theme, quote) in enumerate(themes[:5], 1):
        report += f"### {i}. 关于「{theme}」的深层思考\n\n"
        report += f"**speaker 观点**: {quote[:100]}...\n\n"
        
        report += "**我的深度分析**:\n\n"
        report += f"[这里需要深入分析 {theme} 这个主题]\n\n"
        
        report += "这个观点背后有几个隐含前提：\n"
        report += "1. [前提 1 - 需要分析]\n"
        report += "2. [前提 2 - 需要分析]\n"
        report += "3. [前提 3 - 需要分析]\n\n"
        
        report += "**我想到的案例/问题/机会**:\n"
        report += f"- [案例 1 - 与 {theme} 相关]\n"
        report += f"- [案例 2 - 与 {theme} 相关]\n"
        report += f"- [案例 3 - 与 {theme} 相关]\n\n"
        
        report += "**我的判断**:\n"
        report += f"[对 {theme} 的独立判断]\n\n"
        
        report += "**行动建议**:\n"
        report += f"- [具体建议 1]\n"
        report += f"- [具体建议 2]\n"
        report += f"- [具体建议 3]\n\n"
        
        report += "---\n\n"
    
    # ========== 第二部分：最受启发的点 ==========
    report += "## 二、本集我最受启发的 5 个点\n\n"
    
    for i in range(1, 6):
        report += f"{i}. **[洞察{i}]** —— [为什么受启发]\n\n"
    
    report += "---\n\n"
    
    # ========== 第三部分：我的疑问 ==========
    report += "## 三、我的 5 个疑问\n\n"
    
    for i in range(1, 6):
        report += f"{i}. **[疑问{i}]** —— [为什么有疑问]\n\n"
    
    report += "---\n\n"
    
    # ========== 第四部分：要做的事 ==========
    report += "## 四、我接下来要做的 5 件事\n\n"
    
    for i in range(1, 6):
        report += f"{i}. **[事项{i}]** —— [具体怎么做]\n\n"
    
    report += "---\n\n"
    
    # ========== 第五部分：批判性思考 ==========
    report += "## 五、批判性思考\n\n"
    
    report += "**我同意的观点**:\n"
    report += "1. [观点] —— [为什么同意]\n"
    report += "2. [观点] —— [为什么同意]\n\n"
    
    report += "**我存疑的观点**:\n"
    report += "1. [观点] —— [为什么存疑]\n"
    report += "2. [观点] —— [为什么存疑]\n\n"
    
    report += "**我不同意的观点**:\n"
    report += "1. [观点] —— [为什么不同意]\n\n"
    
    return report


def main():
    parser = argparse.ArgumentParser(description='深度思考生成器 v8.0')
    parser.add_argument('--input', required=True, help='输入转录文本文件')
    parser.add_argument('--output', required=True, help='输出报告文件')
    
    args = parser.parse_args()
    
    # 读取输入
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 文件不存在：{input_path}")
        return 1
    
    with open(input_path, 'r', encoding='utf-8') as f:
        text = f.read()
    
    print(f"📖 加载：{input_path}")
    print(f"📊 长度：{len(text):,} 字")
    
    # 生成报告
    print("\n✍️  生成深度思考报告...")
    report = generate_deep_thinking(text)
    
    # 保存
    output_path = Path(args.output)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n✅ 已保存：{output_path}")
    print(f"📄 大小：{output_path.stat().st_size:,} 字节")
    
    return 0


if __name__ == '__main__':
    exit(main())
