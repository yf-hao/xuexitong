#!/usr/bin/env python3
"""测试代码块转换功能"""
import sys
sys.path.insert(0, '/Volumes/Hao/Users/hao/Documents/hao/sias/xuexitong')

# 测试 to_html 函数
import html
import re

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

# 测试用例
test_cases = [
    # 测试 1: Java 代码块
    """请分析以下代码：
```java
int sum = 0;
for (int i = 1; i <= 4; i++) {
    sum += i;
}
```
以上代码实现了求和功能。""",

    # 测试 2: Python 代码块
    """Python 示例：
```python
def hello():
    print("Hello, World!")
```
这是一个简单的函数。""",

    # 测试 3: 无语言标识的代码块
    """普通代码：
```
some code here
```
结束。""",

    # 测试 4: 混合内容
    """# 标题

段落内容

```javascript
const x = 10;
console.log(x);
```

继续段落。""",
]

print("=" * 60)
print("代码块转换测试")
print("=" * 60)

for i, test_case in enumerate(test_cases, 1):
    print(f"\n测试 {i}:")
    print("-" * 60)
    result = to_html(test_case)
    print(result)
    
    # 检查是否包含代码块标签
    if '<pre class="hover">' in result:
        print(f"\n✓ 成功转换为代码块")
        # 提取代码块
        import re
        match = re.search(r'<pre class="hover">.*?</pre>', result, re.DOTALL)
        if match:
            print(f"代码块内容: {match.group(0)[:100]}...")
    else:
        print(f"\n✗ 未检测到代码块")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
