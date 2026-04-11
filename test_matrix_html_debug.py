#!/usr/bin/env python3
"""测试矩阵HTML转换"""
import re
from core.utils.latex_utils import has_matrix, parse_matrix, is_simple_matrix, matrix_to_html

# 测试表达式
expr = r"A=\begin{pmatrix}1 & 2\\3 & 4\end{pmatrix},\quad B=\begin{pmatrix}2 & 0\\1 & 5\end{pmatrix}"

print("=" * 60)
print("测试表达式:", expr)
print("=" * 60)

# 1. 测试 has_matrix
print(f"\n1. has_matrix(expr) = {has_matrix(expr)}")

# 2. 测试 parse_matrix
print(f"\n2. 解析第一个矩阵:")
matrix_data = parse_matrix(expr)
if matrix_data:
    print(f"   type: {matrix_data['type']}")
    print(f"   rows: {matrix_data['rows']}")
    print(f"   full_match: {matrix_data['full_match'][:50]}...")
    
    # 3. 测试 is_simple_matrix
    print(f"\n3. is_simple_matrix(matrix_data) = {is_simple_matrix(matrix_data)}")
    
    # 4. 测试 matrix_to_html
    print(f"\n4. matrix_to_html(matrix_data):")
    html = matrix_to_html(matrix_data)
    print(f"   {html[:200]}...")
else:
    print("   解析失败!")

# 5. 测试多个矩阵
print(f"\n5. 测试检测所有矩阵:")
temp_expr = expr
count = 0
while has_matrix(temp_expr):
    matrix_data = parse_matrix(temp_expr)
    if matrix_data:
        count += 1
        print(f"   矩阵 {count}: {matrix_data['type']}, 简单={is_simple_matrix(matrix_data)}")
        temp_expr = temp_expr.replace(matrix_data['full_match'], '', 1)
    else:
        break

print(f"\n总共找到 {count} 个矩阵")
