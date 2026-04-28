"""
LaTeX 公式工具模块
处理 LaTeX 到 Unicode 的转换
"""
import re


# 下标 Unicode 映射表
SUBSCRIPT_MAP = {
    '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
    '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
    'a': 'ₐ', 'e': 'ₑ', 'h': 'ₕ', 'i': 'ᵢ', 'j': 'ⱼ',
    'k': 'ₖ', 'l': 'ₗ', 'm': 'ₘ', 'n': 'ₙ', 'o': 'ₒ',
    'p': 'ₚ', 'r': 'ᵣ', 's': 'ₛ', 't': 'ₜ', 'u': 'ᵤ',
    'v': 'ᵥ', 'x': 'ₓ',
    'A': 'ᴀ', 'B': 'ʙ', 'C': 'ᴄ', 'D': 'ᴅ', 'E': 'ᴇ',
    'F': 'ꜰ', 'G': 'ɢ', 'H': 'ʜ', 'I': 'ɪ', 'J': 'ᴊ',
    'K': 'ᴋ', 'L': 'ʟ', 'M': 'ᴍ', 'N': 'ɴ', 'O': 'ᴏ',
    'P': 'ᴘ', 'R': 'ʀ', 'T': 'ᴛ', 'U': 'ᴜ', 'V': 'ᴠ',
    'W': 'ᴡ', 'Y': 'ʏ', 'Z': 'ᴢ',
    '+': '₊', '-': '₋', '=': '₌', '(': '₍', ')': '₎'
}

# 上标 Unicode 映射表
SUPERSCRIPT_MAP = {
    '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
    '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
    'a': 'ᵃ', 'b': 'ᵇ', 'c': 'ᶜ', 'd': 'ᵈ', 'e': 'ᵉ',
    'f': 'ᶠ', 'g': 'ᵍ', 'h': 'ʰ', 'i': 'ⁱ', 'j': 'ʲ',
    'k': 'ᵏ', 'l': 'ˡ', 'm': 'ᵐ', 'n': 'ⁿ', 'o': 'ᵒ',
    'p': 'ᵖ', 'r': 'ʳ', 's': 'ˢ', 't': 'ᵗ', 'u': 'ᵘ',
    'v': 'ᵛ', 'w': 'ʷ', 'x': 'ˣ', 'y': 'ʸ', 'z': 'ᶻ',
    '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾'
}

# LaTeX 命令到 Unicode 的映射表
# 注意：按长度从长到短排序，确保长命令先被替换
LATEX_TO_UNICODE_MAP = [
    # 逻辑符号（长命令优先）
    (r'\leftrightarrow', '↔'),    # 双向箭头
    (r'\rightarrow', '→'),       # 箭头
    (r'\implies', '⇒'),          # 蕴含
    (r'\not\subseteq', '⊈'),    # 不是子集或等于
    (r'\not\supseteq', '⊉'),    # 不是超集或等于
    (r'\not\subset', '⊄'),      # 不是真子集
    (r'\not\supset', '⊅'),      # 不是真超集
    (r'\not\in', '∉'),          # 不属于
    (r'\not=', '≠'),            # 不等于
    (r'\nsubseteq', '⊈'),       # 不是子集或等于
    (r'\nsupseteq', '⊉'),       # 不是超集或等于
    (r'\nsubset', '⊄'),         # 不是真子集
    (r'\nsupset', '⊅'),         # 不是真超集
    (r'\notin', '∉'),           # 不属于
    
    # 集合符号
    (r'\subseteq', '⊆'),         # 子集或等于
    (r'\supseteq', '⊇'),         # 超集或等于
    (r'\emptyset', '∅'),         # 空集
    (r'\varnothing', '∅'),       # 空集（变体）
    
    # 基本符号
    (r'\subset', '⊂'),           # 真子集
    (r'\supset', '⊃'),           # 真超集
    (r'\iff', '⟺'),             # 当且仅当
    (r'\land', '∧'),             # 逻辑与
    (r'\lor', '∨'),              # 逻辑或
    (r'\lnot', '¬'),             # 逻辑非
    (r'\forall', '∀'),           # 全称量词
    (r'\exists', '∃'),           # 存在量词
    (r'\to', '→'),               # 箭头
    (r'\preceq', '≼'),          # 偏序小于等于
    (r'\succeq', '≽'),          # 偏序大于等于
    (r'\preccurlyeq', '≼'),      # 偏序小于等于（变体）
    (r'\succcurlyeq', '≽'),      # 偏序大于等于（变体）
    (r'\prec', '≺'),             # 偏序小于
    (r'\succ', '≻'),             # 偏序大于
    (r'\leq', '≤'),              # 小于等于
    (r'\geq', '≥'),              # 大于等于
    (r'\neq', '≠'),              # 不等于
    (r'\in', '∈'),               # 属于
    (r'\bigcup', '⋃'),          # 大并集
    (r'\bigcap', '⋂'),          # 大交集
    (r'\cup', '∪'),              # 并集
    (r'\cap', '∩'),              # 交集
    (r'\circ', '∘'),             # 函数复合
    (r'\cdot', '·'),             # 点乘
    (r'\bullet', '•'),           # 实心圆点
    (r'\ast', '∗'),              # 星号运算符
    (r'\star', '⋆'),             # 星号
    (r'\oplus', '⊕'),            # 直和
    (r'\otimes', '⊗'),           # 张量积
    (r'\odot', '⊙'),             # 圆圈点号
    (r'\times', '×'),            # 乘号/叉乘
    (r'\div', '÷'),              # 除号
    (r'\pm', '±'),               # 正负号
    (r'\neg', '¬'),              # 逻辑非
    (r'\empty', '∅'),            # 空集
    (r'\wedge', '∧'),            # 逻辑与
    (r'\vee', '∨'),              # 逻辑或
    (r'\sim', '∼'),              # 相似/等价关系
    (r'\ldots', '…'),            # 省略号
    (r'\lrarr', '↔'),            # 双向箭头
]

# 简单 Unicode 符号的正则模式
# 包含：基本字符 + 数学符号 + Unicode 下标 + Unicode 上标
SIMPLE_UNICODE_PATTERN = (
    r'^[a-zA-Z0-9\s\(\)\[\]\{\}|+\-=,.\'\';:\!'
    r'¬∀∃∧∨→↔⇒⟺∈⊂⊃⊆⊇∪∩∅≤≥≠≈≡±×÷∞…⊈⊉⊄⊅⟨⟩∘·•∗⋆⊕⊗⊙≼≽≺≻∼'
    r'₀₁₂₃₄₅₆₇₈₉ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘʀᴛᴜᴠᴡʏᴢ₊₋₌₍₎'
    r'⁰¹²³⁴⁵⁶⁷⁸⁹ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ⁺⁻⁼⁽⁾'
    r']+$'
)


def convert_subscript(text):
    """
    将文本转换为下标 Unicode 字符
    
    Args:
        text: 要转换的文本（如 "1", "12", "n"）
    
    Returns:
        Unicode 下标文本（如 "₁", "₁₂", "ₙ"）
    
    Examples:
        >>> convert_subscript("1")
        '₁'
        >>> convert_subscript("12")
        '₁₂'
        >>> convert_subscript("n")
        'ₙ'
    """
    return ''.join(SUBSCRIPT_MAP.get(c, c) for c in text)


def convert_superscript(text):
    """
    将文本转换为上标 Unicode 字符
    
    Args:
        text: 要转换的文本（如 "2", "10", "n"）
    
    Returns:
        Unicode 上标文本（如 "²", "¹⁰", "ⁿ"）
    
    Examples:
        >>> convert_superscript("2")
        '²'
        >>> convert_superscript("10")
        '¹⁰'
        >>> convert_superscript("n")
        'ⁿ'
    """
    return ''.join(SUPERSCRIPT_MAP.get(c, c) for c in text)


def latex_to_unicode(latex_expr):
    """
    将简单 LaTeX 公式转换为 Unicode 文本
    
    支持：
    - 下标：R_1 → R₁, R_{12} → R₁₂, 10_2 → 10₂
    - 上标：x^2 → x², x^{10} → x¹⁰, 10^{-3} → 10⁻³
    - 尖括号：<a,b> → ⟨a,b⟩
    - 花括号转义：\\{ → {, \\} → }
    
    注意：
    - 仅支持简单的数字和字母下标/上标
    - 复杂表达式（如 x_{n+1}）应渲染成图片
    
    Args:
        latex_expr: LaTeX 表达式（如 "R_1 = \\\\{<2,4>, <2,9>\\\\}"）
    
    Returns:
        Unicode 文本（如 "R₁ = {⟨2,4⟩, ⟨2,9⟩}"）
    
    Examples:
        >>> latex_to_unicode("R_1")
        'R₁'
        >>> latex_to_unicode("x^2")
        'x²'
        >>> latex_to_unicode("10^{-3}")
        '10⁻³'
        >>> latex_to_unicode(r"R_1 = \\{<2,4>, <2,9>\\}")
        'R₁ = {⟨2,4⟩, ⟨2,9⟩}'
    """
    result = latex_expr
    
    # 1. 处理下标: R_1 → R₁, R_{12} → R₁₂
    def replace_subscript(m):
        var = m.group(1)  # 变量名（如 R, x）
        sub = m.group(2)  # 下标内容（如 1, {12}）
        # 移除花括号（如果有）
        sub = sub.replace('{', '').replace('}', '')
        # 仅当下标所有字符都在映射表中时才转换，否则保留原样以便渲染为图片
        if all(c in SUBSCRIPT_MAP for c in sub):
            return var + convert_subscript(sub)
        return m.group(0)
    
    # 匹配 R_1、[x]_R 或 R_{12} 格式（支持 [] 包裹的变量，支持负号）
    # 使用 (?<![a-zA-Z0-9\[\]\\]) 确保前面不是同类字符或反斜杠，避免匹配 LaTeX 命令中的下标（如 \bigcup_{x}）
    result = re.sub(r'(?<![a-zA-Z0-9\[\]\\])([a-zA-Z0-9\[\]]+)_\{?([a-zA-Z0-9\-]+)\}?', replace_subscript, result)
    
    # 2. 处理上标: x^2 → x², x^{10} → x¹⁰, R^{-1} → R⁻¹
    def replace_superscript(m):
        var = m.group(1)  # 变量名
        sup = m.group(2)  # 上标内容
        # 移除花括号
        sup = sup.replace('{', '').replace('}', '')
        # 仅当上标所有字符都在映射表中时才转换，否则保留原样以便渲染为图片
        if all(c in SUPERSCRIPT_MAP for c in sup):
            return var + convert_superscript(sup)
        return m.group(0)
    
    # 匹配 x^2、[x]^2 或 x^{10} 格式（支持 [] 包裹的变量，支持负号和加号）
    # 使用 (?<![a-zA-Z0-9\[\]\\]) 避免匹配 LaTeX 命令中的上标
    result = re.sub(r'(?<![a-zA-Z0-9\[\]\\])([a-zA-Z0-9\[\]]+)\^\{?([a-zA-Z0-9\-\+]+)\}?', replace_superscript, result)
    
    # 3. 尖括号转换: < → ⟨, > → ⟩
    # 注意：先处理 LaTeX 命令 \langle 和 \rangle
    result = result.replace(r'\langle', '⟨')
    result = result.replace(r'\rangle', '⟩')
    # 再处理普通尖括号
    result = result.replace('<', '⟨')
    result = result.replace('>', '⟩')
    
    # 4. 花括号转义: \{ → {, \} → }
    result = result.replace(r'\{', '{')
    result = result.replace(r'\}', '}')
    
    return result


def is_simple_latex(latex_expr):
    """
    判断 LaTeX 表达式是否足够简单，可以转换为 Unicode
    
    简单表达式：
    - 只包含下标、上标
    - 不包含矩阵、积分、分数等复杂结构
    
    Args:
        latex_expr: LaTeX 表达式
    
    Returns:
        bool: True 表示可以转换为 Unicode，False 表示需要渲染成图片
    
    Examples:
        >>> is_simple_latex("R_1")
        True
        >>> is_simple_latex(r"\\int_0^1 x dx")
        False
        >>> is_simple_latex(r"\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}")
        False
    """
    # 复杂 LaTeX 命令列表
    complex_commands = [
        r'\begin{',      # 矩阵环境
        r'\int',         # 积分
        r'\sum',         # 求和
        r'\prod',        # 连乘
        r'\frac',        # 分数
        r'\sqrt',        # 根号
        r'\Big',         # 大括号
        r'\bigg',
        r'\Bigg',
        r'\big',
        r'\lim',         # 极限
        r'\oint',        # 围道积分
        r'\iint',        # 二重积分
        r'\iiint',       # 三重积分
    ]
    
    # 检查是否包含复杂命令
    for cmd in complex_commands:
        if cmd in latex_expr:
            return False
    
    return True


def apply_latex_unicode_map(text):
    """
    应用 LaTeX 到 Unicode 的映射表进行批量转换
    
    Args:
        text: LaTeX 文本
    
    Returns:
        转换后的 Unicode 文本
    
    Examples:
        >>> apply_latex_unicode_map(r"R_1 \\circ R_2")
        'R₁ ∘ R₂'
        >>> apply_latex_unicode_map(r"a \\land b")
        'a ∧ b'
    """
    result = text
    for latex_cmd, unicode_char in LATEX_TO_UNICODE_MAP:
        result = result.replace(latex_cmd, unicode_char)
    return result


def is_simple_unicode(text):
    """
    判断文本是否只包含简单的 Unicode 符号
    
    Args:
        text: Unicode 文本
    
    Returns:
        bool: True 表示只包含简单符号，False 表示需要渲染成图片
    
    Examples:
        >>> is_simple_unicode("R₁ ∘ R₂")
        True
        >>> is_simple_unicode("a ∧ b")
        True
        >>> is_simple_unicode("∉")  # 组合字符
        False
    """
    # 检查是否包含 ∉（组合字符）
    if '∉' in text:
        return False
    
    # 检查是否匹配简单符号模式
    return bool(re.match(SIMPLE_UNICODE_PATTERN, text))
