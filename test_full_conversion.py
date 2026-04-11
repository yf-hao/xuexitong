#!/usr/bin/env python3
"""测试完整题目转换"""
import sys
sys.path.insert(0, '/Volumes/Hao/Users/hao/Documents/hao/sias/xuexitong')

import html
import re

# 模拟 to_html 函数
def to_html(text, replacements=None):
    """转换为 HTML，支持代码块"""
    if text is None:
        return ""

    # 预处理：检测并转换 Markdown 代码块
    code_block_pattern = re.compile(r'```(\w*)\n(.*?)\n```', re.DOTALL)

    # 使用占位符保护代码块
    code_blocks = {}
    placeholder_counter = [0]

    def replace_code_block(match):
        lang = match.group(1) or ""
        code = match.group(2)

        # 转义 HTML 特殊字符
        code_escaped = html.escape(code)

        # 处理缩进和换行
        code_escaped = code_escaped.replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
        code_escaped = code_escaped.replace(" ", "&nbsp;")
        code_escaped = code_escaped.replace("\n", "<br/>")

        # 生成 HTML 代码块
        if lang:
            code_html = f'<pre class="hover"><code lang="{lang}" class="language-{lang}">{code_escaped}<br/></code></pre>'
        else:
            code_html = f'<pre class="hover"><code>{code_escaped}<br/></code></pre>'

        placeholder = f"__CODE_BLOCK_{placeholder_counter[0]}__"
        placeholder_counter[0] += 1
        code_blocks[placeholder] = code_html
        return placeholder

    # 替换代码块为占位符
    text_with_placeholders = code_block_pattern.sub(replace_code_block, str(text))

    # 处理普通文本行
    lines = text_with_placeholders.splitlines() or [""]
    html_lines = []
    for line in lines:
        escaped = html.escape(line)
        escaped = escaped.replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
        escaped = escaped.replace(" ", "&nbsp;")
        if escaped == "":
            escaped = "&nbsp;"
        html_lines.append(f"<p>{escaped}</p>")
    html_str = "".join(html_lines)

    # 恢复代码块
    for placeholder, code_html in code_blocks.items():
        html_str = html_str.replace(f"<p>{placeholder}</p>", code_html)

    if replacements:
        for k, v in replacements.items():
            html_str = html_str.replace(k, v)
    return html_str

# 模拟数学公式处理
def replace_math(text):
    """模拟数学公式处理（简化版）"""
    # 匹配 $...$ 和 $$...$$
    pattern = re.compile(r'\$\$\s*(.+?)\s*\$\$|\$\s*(.+?)\s*\$', re.DOTALL)
    replacements = {}
    new_text = text
    counter = [0]

    for match in pattern.finditer(text):
        expr = match.group(1) or match.group(2) or ""
        expr = expr.strip()

        # 简单转换：将 LaTeX 命令转为 Unicode
        expr_text = expr
        expr_text = expr_text.replace(r"\leq", "≤")
        expr_text = expr_text.replace(r"\geq", "≥")
        expr_text = expr_text.replace(r"\neq", "≠")
        expr_text = expr_text.replace(r"\sum", "∑")
        expr_text = expr_text.replace(r"\int", "∫")
        expr_text = expr_text.replace(r"\infty", "∞")

        # 占位符
        placeholder = f"__MATH_TEXT_{counter[0]}__"
        counter[0] += 1
        replacements[placeholder] = expr_text
        new_text = new_text.replace(match.group(0), placeholder, 1)

    return new_text, replacements

# 测试题目
question_content = """2、执行下面 Java 代码后，变量 $sum$ 的值为：

```java
int sum = 0;
for (int i = 1; i <= 4; i++) {
    sum += i;
}
```

A. $4$
B. $6$
C. $10$
D. $11$

答案：C
难易程度：中
答案解析：`for` 循环中，变量 `i` 从 1 开始，每次加 1，直到 `i <= 4` 为止，因此循环执行时：

$$
sum = 0 + 1 + 2 + 3 + 4
$$

即：

$$
sum = 10
$$

所以正确答案为 C。"""

print("=" * 80)
print("原始题目（Markdown 格式）")
print("=" * 80)
print(question_content)
print()

print("=" * 80)
print("处理步骤")
print("=" * 80)

# 步骤 1: 数学公式处理
print("\n步骤 1: 数学公式处理")
content_with_math, math_replacements = replace_math(question_content)
print(f"  找到 {len(math_replacements)} 个数学公式")
for k, v in math_replacements.items():
    print(f"    {k} → {v}")

# 步骤 2: HTML 转换（包括代码块）
print("\n步骤 2: HTML 转换（包括代码块）")
html_result = to_html(content_with_math, math_replacements)

print("\n" + "=" * 80)
print("最终 HTML 输出")
print("=" * 80)
print(html_result)
print()

# 分析结果
print("=" * 80)
print("结果分析")
print("=" * 80)
print(f"✓ 包含 <pre class=\"hover\">: {('<pre class=\"hover\">' in html_result)}")
print(f"✓ 包含 <code lang=\"java\">: {('<code lang=\"java\"' in html_result)}")
print(f"✓ 包含数学公式: {len(math_replacements) > 0}")
print(f"✓ 包含 &lt;=: {('&lt;=' in html_result)}")
print(f"✓ 包含 &nbsp;: {('&nbsp;' in html_result)}")
print(f"✓ 包含 <br/>: {('<br/>' in html_result)}")

# 格式化显示（带缩进）
print("\n" + "=" * 80)
print("格式化 HTML（便于阅读）")
print("=" * 80)
import xml.dom.minidom
try:
    dom = xml.dom.minidom.parseString(f"<root>{html_result}</root>")
    pretty = dom.toprettyxml(indent="  ")
    # 移除 <?xml?> 和 <root> 标签
    lines = pretty.split('\n')
    formatted = '\n'.join([line for line in lines[2:-2] if line.strip()])
    print(formatted)
except:
    print(html_result)
