"""作业发布设置弹窗。"""

from PyQt6.QtCore import QDateTime, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDateTimeEdit,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)


class HomeworkPublishDialog(QDialog):
    """设置作业发布时间与常用发布选项。"""

    def __init__(
        self,
        work_title: str = "",
        course_id: str = "",
        class_id: str = "",
        work_library_id: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.work_title = str(work_title or "").strip()
        self.course_id = str(course_id or "").strip()
        self.class_id = str(class_id or "").strip()
        self.work_library_id = str(work_library_id or "").strip()
        self.start_time_input = None
        self.end_time_input = None
        self.passing_standard_input = None
        self.redo_times_input = None
        self.end_notice_time_input = None
        self.allow_answer_cb = None
        self.allow_score_cb = None
        self.answer_after_end_cb = None
        self.allow_paste_cb = None
        self.random_sort_cb = None
        self.random_options_cb = None
        self.redo_highest_score_cb = None
        self.not_show_last_answer_cb = None
        self.allow_download_attachment_cb = None
        self.multi_half_score_cb = None
        self.completion_ignore_case_cb = None
        self.blank_ignore_comma_cb = None
        self.prohibit_view_work_cb = None
        self.not_show_teacher_comment_cb = None
        self.ai_review_cb = None
        self.self_mark_cb = None
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("发布作业设置")
        self.resize(620, 560)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel, QGroupBox {
                color: #e6e6e6;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #3d3d3d;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 14px;
            }
            QDateTimeEdit, QSpinBox {
                background-color: #252526;
                color: #e6e6e6;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                padding: 6px 8px;
                min-height: 20px;
            }
            QCheckBox {
                color: #e6e6e6;
                spacing: 8px;
            }
            QPushButton {
                background-color: #007acc;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 8px 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #005c99;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title_label = QLabel(f"作业：{self.work_title or '未命名作业'}")
        title_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title_label)

        tip_label = QLabel("请先确认发布时间和作业规则，点击“发送”后再正式发布。")
        tip_label.setStyleSheet("color: #9cdcfe; font-size: 12px;")
        tip_label.setWordWrap(True)
        layout.addWidget(tip_label)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)
        left_layout = QVBoxLayout()
        left_layout.setSpacing(12)
        right_layout = QVBoxLayout()
        right_layout.setSpacing(12)

        time_group = QGroupBox("1. 时间与生命周期")
        time_form = QFormLayout(time_group)
        time_form.setContentsMargins(14, 18, 14, 12)
        time_form.setSpacing(10)
        time_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        time_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        now = QDateTime.currentDateTime()
        end = now

        self.start_time_input = QDateTimeEdit(now)
        self.start_time_input.setCalendarPopup(True)
        self.start_time_input.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        time_form.addRow("开始时间", self.start_time_input)

        self.end_time_input = QDateTimeEdit(end)
        self.end_time_input.setCalendarPopup(True)
        self.end_time_input.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        time_form.addRow("截止时间", self.end_time_input)

        self.end_notice_time_input = QSpinBox()
        self.end_notice_time_input.setRange(0, 999)
        self.end_notice_time_input.setValue(24)
        self.end_notice_time_input.setSuffix(" 小时")
        time_form.addRow("截止前提醒", self.end_notice_time_input)
        left_layout.addWidget(time_group)

        score_group = QGroupBox("2. 重做与评分规则")
        score_form = QFormLayout(score_group)
        score_form.setContentsMargins(14, 18, 14, 12)
        score_form.setSpacing(10)
        score_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        score_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self.passing_standard_input = QSpinBox()
        self.passing_standard_input.setRange(0, 100)
        self.passing_standard_input.setValue(60)
        self.passing_standard_input.setSuffix(" 分")
        score_form.addRow("及格线", self.passing_standard_input)

        self.redo_times_input = QSpinBox()
        self.redo_times_input.setRange(0, 99)
        self.redo_times_input.setValue(2)
        score_form.addRow("允许重做次数", self.redo_times_input)

        self.redo_highest_score_cb = QCheckBox("重做后取最高分")
        self.redo_highest_score_cb.setChecked(True)
        score_form.addRow("", self.redo_highest_score_cb)

        self.multi_half_score_cb = QCheckBox("多选题漏选给一半分")
        self.multi_half_score_cb.setChecked(True)
        score_form.addRow("", self.multi_half_score_cb)

        self.completion_ignore_case_cb = QCheckBox("填空题忽略大小写")
        self.completion_ignore_case_cb.setChecked(True)
        score_form.addRow("", self.completion_ignore_case_cb)

        self.blank_ignore_comma_cb = QCheckBox("填空题忽略逗号差异")
        self.blank_ignore_comma_cb.setChecked(True)
        score_form.addRow("", self.blank_ignore_comma_cb)

        self.not_show_last_answer_cb = QCheckBox("不展示上次答案")
        self.not_show_last_answer_cb.setChecked(True)
        score_form.addRow("", self.not_show_last_answer_cb)

        left_layout.addWidget(score_group)
        left_layout.addStretch()

        option_group = QGroupBox("3. 防作弊与随机化")
        option_layout = QVBoxLayout(option_group)
        option_layout.setContentsMargins(14, 18, 14, 12)
        option_layout.setSpacing(10)
        option_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self.allow_paste_cb = QCheckBox("允许粘贴")
        self.allow_paste_cb.setChecked(True)
        option_layout.addWidget(self.allow_paste_cb)

        self.random_sort_cb = QCheckBox("题目随机排序")
        self.random_sort_cb.setChecked(True)
        option_layout.addWidget(self.random_sort_cb)

        self.random_options_cb = QCheckBox("选项随机排序")
        self.random_options_cb.setChecked(True)
        option_layout.addWidget(self.random_options_cb)

        right_layout.addWidget(option_group)

        visibility_group = QGroupBox("4. 结果显示控制")
        visibility_layout = QVBoxLayout(visibility_group)
        visibility_layout.setContentsMargins(14, 18, 14, 12)
        visibility_layout.setSpacing(10)
        visibility_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self.allow_answer_cb = QCheckBox("允许学生查看答案")
        self.allow_answer_cb.setChecked(True)
        visibility_layout.addWidget(self.allow_answer_cb)

        self.allow_score_cb = QCheckBox("允许学生查看分数")
        self.allow_score_cb.setChecked(True)
        visibility_layout.addWidget(self.allow_score_cb)

        self.answer_after_end_cb = QCheckBox("截止后才允许查看答案")
        visibility_layout.addWidget(self.answer_after_end_cb)

        self.prohibit_view_work_cb = QCheckBox("禁止查看作业详情")
        visibility_layout.addWidget(self.prohibit_view_work_cb)

        self.not_show_teacher_comment_cb = QCheckBox("不显示教师评语")
        visibility_layout.addWidget(self.not_show_teacher_comment_cb)

        self.allow_download_attachment_cb = QCheckBox("允许下载附件")
        self.allow_download_attachment_cb.setChecked(True)
        visibility_layout.addWidget(self.allow_download_attachment_cb)
        right_layout.addWidget(visibility_group)

        advanced_group = QGroupBox("5. 重点参数补充")
        advanced_layout = QVBoxLayout(advanced_group)
        advanced_layout.setContentsMargins(14, 18, 14, 12)
        advanced_layout.setSpacing(10)
        advanced_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self.self_mark_cb = QCheckBox("开启学生自评")
        advanced_layout.addWidget(self.self_mark_cb)

        self.ai_review_cb = QCheckBox("开启 AI 评阅")
        advanced_layout.addWidget(self.ai_review_cb)
        right_layout.addWidget(advanced_group)
        right_layout.addStretch()

        content_layout.addLayout(left_layout, 1)
        content_layout.addLayout(right_layout, 1)
        layout.addLayout(content_layout, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        send_btn = QPushButton("发送")
        send_btn.clicked.connect(self._on_send_clicked)
        btn_layout.addWidget(send_btn)
        layout.addLayout(btn_layout)

    def _on_send_clicked(self):
        if self.end_time_input.dateTime() < self.start_time_input.dateTime():
            self.end_time_input.setFocus()
            return
        self.accept()

    @property
    def publish_settings(self) -> dict:
        return {
            "startTime": self.start_time_input.dateTime().toString("yyyy-MM-dd HH:mm:ss"),
            "endTime": self.end_time_input.dateTime().toString("yyyy-MM-dd HH:mm:ss"),
            "endNoticeTime": int(self.end_notice_time_input.value()),
            "passingStandard": int(self.passing_standard_input.value()),
            "redoTimes": int(self.redo_times_input.value()),
            "redoHighestScore": 1 if self.redo_highest_score_cb.isChecked() else 0,
            "multiHalfScore": 1 if self.multi_half_score_cb.isChecked() else 0,
            "completionIngoreCase": 1 if self.completion_ignore_case_cb.isChecked() else 0,
            "blankIgnoreComma": 1 if self.blank_ignore_comma_cb.isChecked() else 0,
            "allowAnswer": 1 if self.allow_answer_cb.isChecked() else 0,
            "allowScore": 1 if self.allow_score_cb.isChecked() else 0,
            "answerAfterEnd": 1 if self.answer_after_end_cb.isChecked() else 0,
            "allowPaste": 1 if self.allow_paste_cb.isChecked() else 0,
            "randomSort": 1 if self.random_sort_cb.isChecked() else 0,
            "randomOptions": 1 if self.random_options_cb.isChecked() else 0,
            "notShowLastAnswer": 1 if self.not_show_last_answer_cb.isChecked() else 0,
            "allowDownloadAttachment": 1 if self.allow_download_attachment_cb.isChecked() else 0,
            "prohibitViewWork": 1 if self.prohibit_view_work_cb.isChecked() else 0,
            "notShowTeacherComment": 1 if self.not_show_teacher_comment_cb.isChecked() else 0,
            "selfMark": 1 if self.self_mark_cb.isChecked() else 0,
            "aiReview": 1 if self.ai_review_cb.isChecked() else 0,
        }
