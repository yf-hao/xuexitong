"""
Excel解析工具模块
用于解析从树维教务系统下载的成绩登记册文件
"""
import xlrd
from typing import List, Dict


def parse_students_xls(path: str) -> List[Dict[str, str]]:
    """
    解析成绩登记册Excel文件，提取学生信息

    Args:
        path: Excel文件路径

    Returns:
        学生信息列表，每个元素包含 student_id 和 name

    Raises:
        Exception: 文件读取或解析失败时抛出异常
    """
    try:
        book = xlrd.open_workbook(path)
        sheet = book.sheet_by_index(0)

        students = []

        for i in range(sheet.nrows):
            row = sheet.row_values(i)

student_id = str(row[1]).strip()  # 第二列 - 学号/工号
            name = str(row[2]).strip()        # 第三列 - 姓名

            # 防止被当成数字读出来
            if student_id.endswith('.0'):
                student_id = student_id[:-2]

            # 验证学号格式：必须是13位数字
            if student_id.isdigit() and len(student_id) == 13:
                students.append({
                    "student_id": student_id,
                    "name": name
                })
            else:
                print(f"第{i+1}行学号不合法，跳过：{student_id}")

        return students
    except Exception as e:
        raise Exception(f"Excel文件解析失败: {e}")
