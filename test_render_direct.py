#!/usr/bin/env python3
"""测试题目内容处理流程"""
import sys
sys.path.insert(0, '/Volumes/Hao/Users/hao/Documents/hao/sias/xuexitong')

from core.utils.latex_utils import (
    has_matrix, parse_matrix, is_simple_matrix, matrix_to_html,
    latex_to_unicode, apply_latex_unicode_map, is_simple_unicode
)
import re

# 模拟 render_math_expr 函数
class MockAPI:
    def __init__(self):
        self._matrix_placeholders = {}
    
    def render_math_expr(self, expr):
        print(f"\n{'='*60}")
        print(f"render_math_expr 被调用")
        print(f"表达式: {expr[:100]}...")
        print(f"{'='*60}")
        
        expr_render = expr
        
        # 检查矩阵
        if has_matrix(expr_render):
            print("检测到矩阵")
            # 检查是否所有矩阵都是简单矩阵
            all_matrices_simple = True
            temp_expr = expr_render
            while has_matrix(temp_expr):
                matrix_data = parse_matrix(temp_expr)
                if matrix_data:
                    if not is_simple_matrix(matrix_data):
                        all_matrices_simple = False
                        break
                    temp_expr = temp_expr.replace(matrix_data['full_match'], '', 1)
                else:
                    break
            
            if all_matrices_simple:
                print("所有矩阵都是简单矩阵，跳过渲染")
            else:
                print("包含复杂矩阵，需要渲染")
                # 模拟渲染
                return "http://example.com/image.png", 100, 50, "matrix text"
        
        # LaTeX 命令转换
        expr_text = latex_to_unicode(expr_render)
        expr_text = apply_latex_unicode_map(expr_text)
        
        # is_simple_unicode 检查
        if is_simple_unicode(expr_text):
            print("is_simple_unicode = True，返回文本")
            return None, 0, 0, expr_text
        
        # HTML 表格转换
        print(f"检查 HTML 表格转换, has_matrix={has_matrix(expr_render)}")
        if has_matrix(expr_render):
            print(f"开始 HTML 表格转换")
            result_expr = expr_render
            has_complex_matrix = False
            
            while has_matrix(result_expr):
                matrix_data = parse_matrix(result_expr)
                if matrix_data:
                    if is_simple_matrix(matrix_data):
                        html_table = matrix_to_html(matrix_data)
                        placeholder = f'MATRIXHTMLPLACEHOLDER{len(result_expr)}ENDPLACEHOLDER'
                        result_expr = result_expr.replace(matrix_data['full_match'], placeholder, 1)
                        self._matrix_placeholders[placeholder] = html_table
                    else:
                        has_complex_matrix = True
                        break
                else:
                    break
            
            if not has_complex_matrix:
                print(f"所有矩阵都是简单矩阵，准备返回 HTML 表格")
                result_expr = latex_to_unicode(result_expr)
                result_expr = apply_latex_unicode_map(result_expr)
                
                if hasattr(self, '_matrix_placeholders'):
                    for placeholder, html_table in self._matrix_placeholders.items():
                        result_expr = result_expr.replace(placeholder, html_table)
                    self._matrix_placeholders = {}
                
                print(f"返回 HTML 表格, 长度={len(result_expr)}, 包含<table={'<table' in result_expr}")
                return None, 0, 0, result_expr
        
        print("未处理，返回 None")
        return None, 0, 0, expr_text

# 测试
api = MockAPI()
expr = r"A=\begin{pmatrix}1 & 2\\3 & 4\end{pmatrix},\quad B=\begin{pmatrix}2 & 0\\1 & 5\end{pmatrix}"
result = api.render_math_expr(expr)

print(f"\n最终结果:")
print(f"  url: {result[0]}")
print(f"  w: {result[1]}, h: {result[2]}")
print(f"  text 长度: {len(result[3]) if result[3] else 0}")
if result[3]:
    print(f"  包含 <table: {'<table' in result[3]}")
    print(f"  前200字符: {result[3][:200]}")
