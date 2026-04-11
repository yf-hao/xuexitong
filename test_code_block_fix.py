#!/usr/bin/env python3
"""测试代码块解析修复"""
import sys
sys.path.insert(0, '/Volumes/Hao/Users/hao/Documents/hao/sias/xuexitong')

import re

def parse_question_text(text: str):
    """模拟题目解析逻辑"""
    def strip_md_emphasis(value: str) -> str:
        if not value:
            return ""
        return re.sub(r"`([^`]*)`", r"\1", value)

    lines = text.splitlines()

    # 去掉首行题号前缀
    if lines:
        num_prefix = re.compile(r'^\s*\d+\s*[、.．]\s*')
        lines[0] = num_prefix.sub('', lines[0], count=1)

    content_lines = []
    current_section = "content"
    in_code_block = False  # 跟踪是否在代码块内

    for line in lines:
        raw_line = line.rstrip('\r')

        # 检测代码块开始/结束
        if re.match(r"^\s*```", raw_line):
            in_code_block = not in_code_block
            # 保留代码块围栏标记
            raw_line_clean = raw_line
        elif in_code_block:
            # 代码块内部：保留原始内容
            raw_line_clean = raw_line
        else:
            # 普通文本：处理 Markdown 标记
            raw_line_clean = strip_md_emphasis(raw_line)

        # 跳过分隔线
        if not in_code_block and raw_line_clean.strip() == "---":
            continue

        stripped = raw_line_clean.strip()

        # 跳过空行
        if not stripped:
            continue

        # 添加到内容
        if current_section == "content":
            content_lines.append(raw_line_clean)

    return "\n".join(content_lines)

# 测试题目
test_question = """2、执行下面 Java 代码后，变量 $sum$ 的值为：

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

答案：C"""

print("=" * 80)
print("原始题目")
print("=" * 80)
print(test_question)
print()

print("=" * 80)
print("解析后的内容（应该保留代码块标记）")
print("=" * 80)
parsed = parse_question_text(test_question)
print(parsed)
print()

# 检查代码块是否保留
print("=" * 80)
print("验证结果")
print("=" * 80)
print(f"✓ 包含 ```java: {'```java' in parsed}")
print(f"✓ 包含代码内容: {'int sum = 0;' in parsed}")
print(f"✓ 包含结束 ```: {parsed.count('```') >= 2}")

# 统计 ``` 出现次数
count = parsed.count('```')
print(f"✓ ``` 出现次数: {count} (应该是 2)")
