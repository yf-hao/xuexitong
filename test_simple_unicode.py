#!/usr/bin/env python3
"""测试 is_simple_unicode 检查"""
import sys
sys.path.insert(0, '/Volumes/Hao/Users/hao/Documents/hao/sias/xuexitong')

from core.utils.latex_utils import latex_to_unicode, apply_latex_unicode_map, is_simple_unicode

# 测试表达式
expr = r"A=\begin{pmatrix}1 & 2\\3 & 4\end{pmatrix},\quad B=\begin{pmatrix}2 & 0\\1 & 5\end{pmatrix}"

print("=" * 60)
print("测试 is_simple_unicode 检查")
print("=" * 60)
print(f"原始表达式: {expr}")
print()

# 模拟 render_math_expr 中的转换
expr_text = latex_to_unicode(expr)
print(f"latex_to_unicode 后: {expr_text[:100]}...")

expr_text = apply_latex_unicode_map(expr_text)
print(f"apply_latex_unicode_map 后: {expr_text[:100]}...")

# 检查 is_simple_unicode
is_simple = is_simple_unicode(expr_text)
print(f"\nis_simple_unicode(expr_text) = {is_simple}")

if is_simple:
    print("⚠️ 这会导致提前返回，跳过 HTML 表格转换!")
else:
    print("✓ is_simple_unicode 返回 False，继续执行 HTML 表格转换")
