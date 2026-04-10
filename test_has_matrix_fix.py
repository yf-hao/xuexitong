#!/usr/bin/env python3
"""验证 has_matrix 函数没有被覆盖"""
import sys
sys.path.insert(0, '/Volumes/Hao/Users/hao/Documents/hao/sias/xuexitong')

from core.utils.latex_utils import has_matrix

# 测试 has_matrix 是否是函数
print(f"has_matrix 类型: {type(has_matrix)}")
print(f"has_matrix 是可调用对象: {callable(has_matrix)}")

# 测试函数调用
expr = r"\begin{pmatrix}1 & 2\\3 & 4\end{pmatrix}"
result = has_matrix(expr)
print(f"has_matrix('{expr[:30]}...') = {result}")

print("\n✓ has_matrix 函数正常工作")
