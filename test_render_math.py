#!/usr/bin/env python3
"""测试 render_math_expr 的逻辑"""
import re
import sys
sys.path.insert(0, '/Volumes/Hao/Users/hao/Documents/hao/sias/xuexitong')

from core.utils.latex_utils import (
    has_matrix, parse_matrix, is_simple_matrix, matrix_to_html,
    latex_to_unicode, apply_latex_unicode_map, is_simple_unicode
)

# 测试表达式
expr = r"A=\begin{pmatrix}1 & 2\\3 & 4\end{pmatrix},\quad B=\begin{pmatrix}2 & 0\\1 & 5\end{pmatrix}"

print("=" * 60)
print("模拟 render_math_expr 的执行流程")
print("=" * 60)
print(f"输入表达式: {expr}")
print()

# 步骤 1: 检查是否有矩阵
print("步骤 1: 检查矩阵")
has_matrix_result = has_matrix(expr)
print(f"  has_matrix = {has_matrix_result}")

if has_matrix_result:
    # 步骤 2: 检查是否所有矩阵都是简单矩阵
    print("\n步骤 2: 检查所有矩阵是否简单")
    all_matrices_simple = True
    temp_expr = expr
    while has_matrix(temp_expr):
        matrix_data = parse_matrix(temp_expr)
        if matrix_data:
            if not is_simple_matrix(matrix_data):
                all_matrices_simple = False
                print(f"  发现复杂矩阵: {matrix_data['type']}")
                break
            print(f"  发现简单矩阵: {matrix_data['type']}")
            temp_expr = temp_expr.replace(matrix_data['full_match'], '', 1)
        else:
            break
    
    print(f"  all_matrices_simple = {all_matrices_simple}")
    
    if all_matrices_simple:
        print("\n步骤 3: 跳过 CodeCogs API，执行 HTML 表格转换")
        
        # 模拟 HTML 表格转换逻辑
        result_expr = expr
        has_complex_matrix = False
        placeholders = {}
        
        while has_matrix(result_expr):
            matrix_data = parse_matrix(result_expr)
            if matrix_data:
                if is_simple_matrix(matrix_data):
                    html_table = matrix_to_html(matrix_data)
                    placeholder = f'MATRIXHTMLPLACEHOLDER{len(result_expr)}ENDPLACEHOLDER'
                    result_expr = result_expr.replace(matrix_data['full_match'], placeholder, 1)
                    placeholders[placeholder] = html_table
                    print(f"  转换矩阵为 HTML，使用占位符: {placeholder}")
                else:
                    has_complex_matrix = True
                    break
            else:
                break
        
        if not has_complex_matrix:
            print("\n步骤 4: 处理剩余的 LaTeX 命令")
            result_expr = latex_to_unicode(result_expr)
            result_expr = apply_latex_unicode_map(result_expr)
            print(f"  转换后: {result_expr[:100]}...")
            
            print("\n步骤 5: 恢复 HTML 表格")
            for placeholder, html_table in placeholders.items():
                result_expr = result_expr.replace(placeholder, html_table)
            
            print("\n最终结果:")
            print(f"  返回: (None, 0, 0, text)")
            print(f"  text 长度: {len(result_expr)}")
            print(f"  text 前200字符: {result_expr[:200]}...")
            print(f"  包含 <table: {'<table' in result_expr}")
            print(f"  包含 editor-table: {'editor-table' in result_expr}")
