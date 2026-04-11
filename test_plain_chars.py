#!/usr/bin/env python3
"""测试 plain_chars_pattern 检查"""
import re

# 测试表达式
expr = r"A=\begin{pmatrix}1 & 2\\3 & 4\end{pmatrix},\quad B=\begin{pmatrix}2 & 0\\1 & 5\end{pmatrix}"

print("=" * 60)
print("测试 plain_chars_pattern 检查")
print("=" * 60)
print(f"表达式: {expr}")
print()

plain_chars_pattern = r'^[a-zA-Z0-9\s\(\)\[\]\{\}+\-=,.\'\';:\!]+$'
match = re.match(plain_chars_pattern, expr)

print(f"re.match(plain_chars_pattern, expr) = {match}")

if match:
    print("⚠️ 这会导致提前返回!")
else:
    print("✓ 不匹配，继续执行")
