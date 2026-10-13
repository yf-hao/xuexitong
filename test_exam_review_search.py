import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QTableWidgetItem

from ui.views.exam_review_view import ExamReviewView


_APP = QApplication.instance() or QApplication(["exam-review-search-tests"])


class ExamReviewSearchTests(unittest.TestCase):
    def setUp(self):
        self.view = ExamReviewView(None)
        self.view.page_num = 2
        self.view.state = 1
        records = [
            ("张三", "2024001"),
            ("李四", "2025002"),
            ("王张", "2026003"),
        ]
        self.view.records_table.setRowCount(len(records))
        for row, record in enumerate(records):
            for column, value in enumerate(record):
                self.view.records_table.setItem(
                    row, column, QTableWidgetItem(value)
                )

    def tearDown(self):
        self.view.close()
        self.view.deleteLater()

    def test_matches_partial_name_and_student_id_on_current_page(self):
        self.view.student_search_input.setText("张")
        self.assertEqual(
            [
                row
                for row in range(self.view.records_table.rowCount())
                if not self.view.records_table.isRowHidden(row)
            ],
            [0, 2],
        )

        self.view.student_search_input.setText("500")
        self.assertEqual(
            [
                row
                for row in range(self.view.records_table.rowCount())
                if not self.view.records_table.isRowHidden(row)
            ],
            [1],
        )
        self.assertEqual(self.view.page_num, 2)
        self.assertEqual(self.view.state, 1)

    def test_empty_query_restores_all_current_page_rows(self):
        self.view.student_search_input.setText("not found")
        self.view.student_search_input.clear()

        self.assertEqual(
            [
                row
                for row in range(self.view.records_table.rowCount())
                if not self.view.records_table.isRowHidden(row)
            ],
            [0, 1, 2],
        )

    def test_no_match_shows_current_page_empty_message(self):
        self.view.student_search_input.setText("不存在")

        self.assertTrue(
            all(
                self.view.records_table.isRowHidden(row)
                for row in range(self.view.records_table.rowCount())
            )
        )
        self.assertEqual(
            self.view.status_label.text(), "当前页没有匹配的姓名或学号"
        )


if __name__ == "__main__":
    unittest.main()