import os
import unittest
import base64
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QTimer, QUrl
from PyQt6.QtGui import QImage, QTextDocument
from PyQt6.QtWidgets import QApplication, QDialog

from core.apis.exam_api import EXAM_SUBMIT_MARK_URL
from core.utils.exam_mark_paper_parser import (
    parse_exam_mark_paper, parse_exam_question_mark_paper,
)
from ui.dialogs.exam_answer_dialog import (
    ExamAnswerDialog, _ExamAnswerTextBrowser, _ExamAIScoringWorker,
    _student_answer_image_data_uris,
)


_APP = QApplication.instance() or QApplication(["exam-answer-submission-tests"])


class FakeSubmitResponse:
    status_code = 200
    url = EXAM_SUBMIT_MARK_URL

    def raise_for_status(self):
        pass

    def json(self):
        return {"status": "success", "msg": "批阅成功"}


class FakeSubmitSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeSubmitResponse()


class ExamAnswerSubmissionTests(unittest.TestCase):
    def setUp(self):
        html = """
        <form id="submitMarking" method="post"
          action="/mooc2-ans/exam/test/submitmark?testUserRelationId=answer-1&amp;classId=class-1">
          <input name="perq1" value="10"><input name="typeq1" value="4">
          <input name="groupidq1" value="0"><input name="relationidq1" value="rel-1">
          <input name="recordidq1" value="rec-1"><input name="scoreq1" value="6">
          <input name="subq1" value="1"><textarea name="teacherContentq1">原评语</textarea>
          <input name="labelq1" value=""><input name="typicalq1" value="0">
          <input name="perq2" value="10"><input name="typeq2" value="4">
          <input name="groupidq2" value="0"><input name="relationidq2" value="rel-2">
          <input name="recordidq2" value="rec-2"><input name="scoreq2" value="7">
          <input name="subq2" value="1"><textarea name="teacherContentq2">原有评语</textarea>
          <input name="labelq2" value=""><input name="typicalq2" value="0">
          <input name="testUserRelationId" value="answer-1">
          <input name="testPaperId" value="paper-1">
          <input name="courseId" value="course-1">
          <input name="classId" value="class-1">
          <input name="questionId" value="q1,q2,">
          <input name="sumScore" value="13">
          <input name="markStyle" value="0">
          <input name="submitType" value="0">
        </form>
        <div class="questionWrap" index="1" name="简答题">
          <input id="fullScoreq1" value="10"><input name="scoreq1" value="6">
          <h3 class="mark_name" id="questionStem_q1">题目一</h3>
        </div>
        <div class="questionWrap" index="2" name="简答题">
          <input id="fullScoreq2" value="10"><input name="scoreq2" value="7">
          <h3 class="mark_name" id="questionStem_q2">题目二</h3>
        </div>
        """
        self.content = parse_exam_mark_paper(html)
        self.dialog = ExamAnswerDialog(
            "考试", "学生", "1", self.content,
            exam_id="exam-1", answer_id="answer-1", session=object(),
        )

    def tearDown(self):
        self.dialog.deleteLater()
        _APP.processEvents()

    def test_ai_reason_is_submitted_as_teacher_content_and_scores_are_summed(self):
        first_question, second_question = self.content.questions
        self.dialog._draft_scores[
            self.dialog._score_draft_key(first_question)
        ] = 8
        self.dialog._ai_breakdowns[
            self.dialog._score_draft_key(first_question)
        ] = {
            "score": 8,
            "earned_points": [{
                "item": "关键步骤 <正确>",
                "points": 8,
                "evidence": "推导 <完整>",
            }],
            "lost_points": [{
                "item": "缺少结论",
                "points": 2,
                "evidence": "未写结论",
            }],
            "summary": "整体正确 & 合理",
        }

        _action, query_params, form_fields, referer = (
            self.dialog._build_submission_payload()
        )
        values = dict(form_fields)

        self.assertEqual(values["scoreq1"], "8")
        self.assertEqual(values["scoreq2"], "7")
        self.assertEqual(values["sumScore"], "15")
        self.assertNotIn("AI 评分理由", values["teacherContentq1"])
        self.assertIn("整体正确 &amp; 合理", values["teacherContentq1"])
        self.assertIn("&lt;正确&gt;", values["teacherContentq1"])
        self.assertIn("依据：推导 &lt;完整&gt;", values["teacherContentq1"])
        self.assertEqual(values["teacherContentq2"], "原有评语")
        self.assertEqual(dict(query_params)["sumScore"], "15")
        self.assertEqual(referer, "")

    def test_submit_button_posts_in_worker_and_closes_only_on_success(self):
        first_question = self.content.questions[0]
        self.dialog._draft_scores[
            self.dialog._score_draft_key(first_question)
        ] = 8
        self.dialog._ai_breakdowns[
            self.dialog._score_draft_key(first_question)
        ] = {
            "score": 8,
            "earned_points": [{
                "item": "关键步骤",
                "points": 8,
                "evidence": "推导正确",
            }],
            "lost_points": [],
            "summary": "总体正确",
        }
        session = FakeSubmitSession()
        self.dialog._session = session
        self.dialog.show()
        event_loop = QEventLoop()
        self.dialog.finished.connect(event_loop.quit)

        self.dialog._submit_grades()
        QTimer.singleShot(5000, event_loop.quit)
        event_loop.exec()

        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(len(session.calls), 1)
        _url, options = session.calls[0]
        form_fields = dict(options["data"])
        self.assertEqual(form_fields["scoreq1"], "8")
        self.assertIn("teacherContentq1", form_fields)
        self.assertEqual(form_fields["sumScore"], "15")

    def test_embedded_answer_image_loads_in_answer_browser(self):
        image_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/"
            "iZk9HQAAAABJRU5ErkJggg=="
        )
        image_data = base64.b64encode(image_bytes).decode("ascii")
        data_uri = f"data:image/png;base64,{image_data}"
        html = f"""
        <div class="questionWrap" name="简答题">
          <h3 class="mark_name">题干</h3>
          <div class="topicStudentAnswer">
            <p><img class="ans-ued-img" src="{data_uri}"></p>
          </div>
        </div>
        """
        question = parse_exam_mark_paper(html).questions[0]
        browser = _ExamAnswerTextBrowser()
        browser.setHtml(question.student_answer_html)

        image = browser.document().resource(
            QTextDocument.ResourceType.ImageResource, QUrl(data_uri)
        )

        self.assertIsInstance(image, QImage)
        self.assertFalse(image.isNull())
        browser.deleteLater()
        _APP.processEvents()

    def test_image_only_student_answer_is_not_replaced_with_empty_text(self):
        data_uri = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/"
            "iZk9HQAAAABJRU5ErkJggg=="
        )
        content = parse_exam_mark_paper(
            f'<div class="questionWrap" name="简答题">'
            f'<h3 class="mark_name" id="questionStem_q1">题干</h3>'
            f'<div class="topicStudentAnswer"><img src="{data_uri}"></div>'
            '</div>'
        )
        dialog = ExamAnswerDialog(
            "考试", "学生", "1", content,
            exam_id="image-only", answer_id="answer-1",
        )
        answer_html = dialog._paper_html(content)
        self.assertIn(data_uri, answer_html)
        self.assertNotIn("暂无作答", answer_html)
        dialog.deleteLater()
        _APP.processEvents()

    def test_scoring_image_extraction_keeps_all_embedded_images_in_order(self):
        first_image = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/"
            "iZk9HQAAAABJRU5ErkJggg=="
        )
        second_image = "data:image/jpeg;base64,/9j/ZmFrZQ=="
        answer_html = (
            f'<img src="{first_image}"><span>答案文字</span>'
            f'<img src="{second_image}">'
            '<img src="https://example.test/image.png">'
        )

        self.assertEqual(
            _student_answer_image_data_uris(answer_html),
            [first_image, second_image],
        )

    def test_scoring_worker_passes_docx_images_with_body_marker_to_ai(self):
        image_data_uri = "data:image/png;base64,aW1hZ2UtMQ=="
        attachment = SimpleNamespace(
            object_id="docx-1", filename="answer.docx"
        )
        worker = _ExamAIScoringWorker(
            "question-1",
            {
                "question": "题目",
                "maximum_score": 10,
                "student_answer": "直接作答",
                "student_answer_images": [],
            },
            (attachment,),
            session=object(),
        )
        outcomes = []
        worker.completed.connect(lambda *result: outcomes.append(result))
        with (
            patch(
                "ui.dialogs.exam_answer_dialog.exam_attachment_cache_path",
                return_value="cached-answer.docx",
            ),
            patch(
                "ui.dialogs.exam_answer_dialog.os.path.isfile",
                return_value=True,
            ),
            patch(
                "ui.dialogs.exam_answer_dialog.os.path.getsize",
                return_value=10,
            ),
            patch(
                "ui.dialogs.exam_answer_dialog.extract_attachment_scoring_content",
                return_value=("正文前 [图片 1] 正文后", (image_data_uri,)),
            ),
            patch(
                "ui.dialogs.exam_answer_dialog.DiscreteMathAIService"
            ) as ai_service_class,
        ):
            worker.run()

        self.assertTrue(outcomes[0][1], outcomes[0][2])
        scoring_data = (
            ai_service_class.return_value.generate_exam_score.call_args.args[0]
        )
        self.assertEqual(
            scoring_data["student_attachments"],
            [{"filename": "answer.docx", "text": "正文前 [图片 1] 正文后"}],
        )
        self.assertEqual(
            scoring_data["student_answer_images"],
            [{
                "data_uri": image_data_uri,
                "context": "附件 answer.docx 中的图片 1，对应正文标记 [图片 1]",
            }],
        )
    def test_question_mark_dialog_builds_question_specific_submit_payload(self):
        html = """
        <form id="submitMarking"
          action="/mooc2-ans/exam/test/submit-markquestion?clazzid=class-1&amp;id=exam-1&amp;answerid=answer-1&amp;qid=q1">
          <input name="answerid" value="answer-1">
          <input name="qid" id="qid" value="q1">
          <input id="fullScoreq1" value="33.0">
          <input name="scoreq1" value="">
          <textarea name="teacherContentq1"></textarea>
        </form>
        <div class="changeTimu"><span class="timuNum">第1题</span></div>
        <div class="stem">1.<span>(简答题，33.0分)</span>
          <div class="hiddenTitle"><p>题目内容</p></div>
        </div>
        <div id="stuAnswer_q1"><div class="answerCon stuAnswerWords">
          <p>学生答案</p>
        </div></div>
        """
        page = parse_exam_question_mark_paper(html)
        dialog = ExamAnswerDialog(
            "考试", page.student_name, page.student_id, page.content,
            exam_id="exam-1", answer_id=page.answer_id, session=object(),
        )
        question = page.content.questions[0]
        draft_key = dialog._score_draft_key(question)
        dialog._draft_scores[draft_key] = 28
        dialog._ai_breakdowns[draft_key] = {
            "score": 28,
            "earned_points": [{
                "item": "关键步骤", "points": 28, "evidence": "推导完整",
            }],
            "lost_points": [{
                "item": "遗漏说明", "points": 5, "evidence": "缺少说明",
            }],
            "summary": "基本正确",
        }

        action, query_params, form_fields, referer = (
            dialog._build_submission_payload()
        )
        values = dict(form_fields)

        self.assertIn("/submit-markquestion?", action)
        self.assertEqual(dict(query_params)["qid"], "q1")
        self.assertEqual(values["scoreq1"], "28")
        self.assertIn("基本正确", values["teacherContentq1"])
        self.assertNotIn("sumScore", values)
        self.assertEqual(referer, "")
        dialog.deleteLater()
        _APP.processEvents()


if __name__ == "__main__":
    unittest.main()