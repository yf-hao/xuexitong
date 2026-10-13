import base64
import json
import unittest
from urllib.parse import quote

from core.utils.exam_mark_paper_parser import (
    parse_exam_mark_paper, parse_exam_question_mark_paper,
)


class ExamMarkPaperParserTests(unittest.TestCase):
    def test_grading_status_distinguishes_objective_and_subjective_scores(self):
        html = """
        <div>
          <div class="questionWrap" name="单选题">
            <input id="fullScore1" value="2">
            <input name="score1" value="2" readonly>
          </div>
          <div class="questionWrap" name="单选题">
            <input id="fullScore2" value="2">
            <input name="score2" value="0" readonly>
          </div>
          <div class="questionWrap" name="多选题">
            <input id="fullScore3" value="2">
            <input name="score3" value="1" readonly>
          </div>
          <div class="questionWrap" name="简答题">
            <input id="fullScore4" value="2">
            <input name="score4" value="1" readonly>
          </div>
          <div class="questionWrap" name="单选题">
            <input id="fullScore5" value="2">
            <input name="score5" value="0">
          </div>
        </div>
        """

        questions = parse_exam_mark_paper(html).questions

        statuses_by_number = {
          question.number: question.grading_status for question in questions
        }
        self.assertEqual(statuses_by_number, {
          "1": "correct",
          "2": "incorrect",
          "3": "partial",
          "4": "graded",
          "5": "pending",
        })
    def test_objective_student_answer_excludes_source_labels_and_score_controls(self):
        html = """
        <div class="questionWrap" name="单选题">
          <h3 class="mark_name">题干</h3>
          <div class="topicStudentAnswer">
            <div class="mark_key clearfix">
              <span class="studenticon"><img src="/avatar.png"></span>
              <span class="colorDeep">学生答案：C</span>
            </div>
            <div class="mark_score">
              <div class="totalScore">得分：2.5分</div>
              <a onclick="editScore()">点击修改</a>
            </div>
          </div>
        </div>
        """

        question = parse_exam_mark_paper(html).questions[0]

        self.assertIn("C", question.student_answer_html)
        for redundant_text in (
            "学生答案", "得分", "2.5", "点击修改", "avatar.png",
            "附件或媒体内容", "editScore",
        ):
            self.assertNotIn(redundant_text, question.student_answer_html)

    def test_extracts_objective_choices_correct_answer_and_explanation(self):
        html = """
        <div class="ans-cc">
          <div class="left-typt-tit">一.单选题（共1题，2.5分）</div>
          <div class="questionWrap" index="1" name="单选题">
            <input id="fullScore1" value="2.5">
            <div class="topicArea">
              <h3 class="mark_name">
                <span class="colorShallow">1. (单选题, 2.5分)</span>
                <div class="hiddenTitle textWrap">1. 题目正文</div>
              </h3>
              <ul class="mark_letter"><li>选项甲</li><li>选项乙</li></ul>
              <div class="mark_answer topicStudentAnswer"><div>学生选择</div></div>
              <div class="mark_answer topicRightAnswer">
                <div class="mark_key">
                  <span class="studenticon"><img src="/avatar.png"></span>
                  <span class="colorGreen"><i class="fontWeight">正确答案：</i>C</span>
                </div>
                <div class="answerAnalysis">
                  <span class="analysisTit"><b>答案解析</b></span>
                  <div class="AnalysisCon">选项 C 符合题意。</div>
                </div>
              </div>
            </div>
          </div>
        </div>
        """

        question = parse_exam_mark_paper(html).questions[0]

        self.assertIn("题目正文", question.stem_html)
        self.assertIn("选项甲", question.stem_html)
        self.assertIn("选项乙", question.stem_html)
        self.assertIn('<div class="choices">', question.stem_html)
        self.assertIn("<div>选项甲</div>", question.stem_html)
        self.assertNotIn("<li>", question.stem_html)
        self.assertNotIn("1. (单选题, 2.5分)", question.stem_html)
        self.assertTrue(question.stem_html.startswith("题目正文"))
        self.assertIn("学生选择", question.student_answer_html)
        self.assertIn("C", question.correct_answer_html)
        self.assertNotIn("正确答案", question.correct_answer_html)
        self.assertNotIn("avatar.png", question.correct_answer_html)
        self.assertIn("选项 C 符合题意", question.explanation_html)

    def test_groups_questions_by_type_and_sums_maximum_scores(self):
        html = """
        <div class="ans-cc">
          <div class="left-typt-tit">一.单选题（共2题，5.0分）</div>
          <div class="questionWrap" index="1" name="单选题">
            <input id="fullScore1" value="2.5">
            <input id="score1" name="score1" value="1.5" data-score="2.5" readonly>
            <h3 class="mark_name">
              <span class="colorShallow">1. (单选题, 2.5分)</span>
              <div>第一题</div>
            </h3>
          </div>
          <div class="questionWrap" index="2" name="单选题">
            <input id="fullScore2" value="2.5">
            <input id="score2" name="score2" value="1.0" data-score="2.5">
            <h3 class="mark_name">
              <span class="colorShallow">2. (单选题, 2.5分)</span>
              <div>第二题</div>
            </h3>
          </div>
        </div>
        """

        content = parse_exam_mark_paper(html)

        self.assertEqual(len(content.groups), 1)
        group = content.groups[0]
        self.assertEqual(
          group.title, "一.单选题（共2题，每题2.5分，共5.0分）"
        )
        self.assertEqual(group.question_type, "单选题")
        self.assertEqual(len(group.questions), 2)
        self.assertEqual(group.total_score, 5.0)
        self.assertEqual([question.score for question in group.questions], [2.5, 2.5])
        self.assertEqual(group.questions[0].earned_score, 1.5)
        self.assertTrue(group.questions[0].score_confirmed)
        self.assertEqual(group.questions[1].earned_score, 1.0)
        self.assertFalse(group.questions[1].score_confirmed)
        self.assertEqual(len(content.questions), 2)
        self.assertNotIn("1. (单选题, 2.5分)", group.questions[0].stem_html)
        self.assertIn("第一题", group.questions[0].stem_html)

    def test_group_title_omits_per_question_score_when_scores_differ(self):
        html = """
        <div class="ans-cc">
          <div class="left-typt-tit">一.单选题（共2题，5.0分）</div>
          <div class="questionWrap" index="1" name="单选题">
            <input id="fullScore1" value="2">
            <h3 class="mark_name"><div>第一题</div></h3>
          </div>
          <div class="questionWrap" index="2" name="单选题">
            <input id="fullScore2" value="3">
            <h3 class="mark_name"><div>第二题</div></h3>
          </div>
        </div>
        """

        group = parse_exam_mark_paper(html).groups[0]

        self.assertEqual(group.title, "一.单选题（共2题，5.0分）")

    def test_extracts_question_and_answer_sections(self):
        html = """
        <div class="questionWrap" index="4" name="简答题">
          <h3 class="mark_name" id="questionStem_52"><b>题干</b></h3>
          <div class="stuAnswerWords">
            <div class="SubjectStuAnswer"><p>学生答案</p></div>
          </div>
          <div class="answerAnalysis"><p>解析内容</p></div>
        </div>
        """

        content = parse_exam_mark_paper(html)

        self.assertEqual(len(content.questions), 1)
        question = content.questions[0]
        self.assertEqual(question.number, "4")
        self.assertEqual(question.question_type, "简答题")
        self.assertEqual(question.question_id, "52")
        self.assertIn("题干", question.stem_html)
        self.assertIn("学生答案", question.student_answer_html)
        self.assertEqual(question.correct_answer_html, "")
        self.assertIn("解析内容", question.explanation_html)

    def test_preserves_submit_form_template_and_page_options(self):
        html = """
        <form id="submitMarking" method="post"
          action="/mooc2-ans/exam/test/submitmark?testUserRelationId=answer-1&amp;classId=class-1">
          <input type="hidden" name="per42" value="10">
          <input type="hidden" name="relationid42" value="relation-42">
          <input type="hidden" name="recordid42" value="record-42">
          <input type="text" name="score42" value="6">
          <textarea name="teacherContent42"><p>原评语</p></textarea>
          <input type="hidden" name="questionId" value="42,">
          <input type="text" name="sumScore" value="6">
          <input type="hidden" id="checkHiddenObjectQuestion" value="1">
        </form>
        <div class="questionWrap" index="1" name="简答题">
          <input id="fullScore42" value="10">
          <input name="score42" value="6">
          <h3 class="mark_name" id="questionStem_42">题目</h3>
        </div>
        """

        content = parse_exam_mark_paper(html)
        submission = content.submission
        fields = dict(submission.fields)
        query_params = dict(submission.query_params)

        self.assertEqual(
            submission.action.split("?", 1)[0],
            "/mooc2-ans/exam/test/submitmark",
        )
        self.assertEqual(fields["teacherContent42"], "<p>原评语</p>")
        self.assertEqual(fields["recordid42"], "record-42")
        self.assertEqual(query_params["testUserRelationId"], "answer-1")
        self.assertEqual(query_params["classId"], "class-1")
        self.assertEqual(query_params["checkHiddenObjectQuestion"], "1")
        self.assertEqual(query_params["sorttype"], "0")
        self.assertEqual(content.questions[0].question_id, "42")

    def test_extracts_student_answer_attachments_from_cloud_iframes(self):
        metadata = quote(
            json.dumps({
                "objectid": "cloud-object-1",
                "name": "任务一提示词.md",
                "type": "md",
                "size": "1.75K",
            }, ensure_ascii=False),
            safe="",
        )
        encoded_metadata = base64.b64encode(
            metadata.encode("utf-8")
        ).decode("ascii")
        html = f"""
        <div class="questionWrap" index="1" name="简答题">
          <h3 class="mark_name" id="questionStem_q1"><div>题目</div></h3>
          <div class="stuAnswerWords">
            <div class="SubjectStuAnswer">
              <div class="editor-iframe">
                <iframe class="attach-iframe" module="insertAttach"
                  objectid="cloud-object-1" filename="任务一提示词.md"
                  filetype="md" filesize="1.75K"
                  name="{encoded_metadata}"></iframe>
              </div>
            </div>
          </div>
        </div>
        """

        question = parse_exam_mark_paper(html).questions[0]

        self.assertEqual(len(question.attachments), 1)
        attachment = question.attachments[0]
        self.assertEqual(attachment.object_id, "cloud-object-1")
        self.assertEqual(attachment.filename, "任务一提示词.md")
        self.assertEqual(attachment.file_type, "md")
        self.assertEqual(attachment.file_size, "1.75K")
        self.assertNotIn("iframe", question.student_answer_html)

    def test_removes_active_content_controls_and_external_urls(self):
        html = """
        <div class="questionWrap">
          <h3 class="mark_name">题干</h3>
          <div class="stuAnswerWords">
            <div class="SubjectStuAnswer" onclick="run()">
              <p>保留文本</p>
              <script><b>不应保留</b></script>
              <img src="https://outside.invalid/image.png">
              <a href="https://outside.invalid">链接文本</a>
              <input name="score1" value="100">
              <textarea>可编辑文本</textarea>
            </div>
          </div>
          <button>提交成绩</button>
        </div>
        """

        question = parse_exam_mark_paper(html).questions[0]
        answer = question.student_answer_html

        self.assertIn("保留文本", answer)
        self.assertIn("链接文本", answer)
        self.assertIn("[附件或媒体内容]", answer)
        for forbidden in (
            "run()", "不应保留", "outside.invalid", "score1", "100",
            "可编辑文本", "提交成绩", "onclick", "href", "src",
        ):
            self.assertNotIn(forbidden, answer)

    def test_keeps_valid_inline_raster_image_and_rejects_mismatched_data_uri(self):
        image_payload = base64.b64encode(
            b"\x89PNG\r\n\x1a\nimage-data"
        ).decode("ascii")
        html = f"""
        <div class="questionWrap" name="简答题">
          <h3 class="mark_name">题干</h3>
          <div class="topicStudentAnswer">
            <p><img src="data:image/png;base64,{image_payload}" width="120"></p>
            <img src="data:image/png;base64,SGVsbG8=">
          </div>
        </div>
        """

        answer = parse_exam_mark_paper(html).questions[0].student_answer_html

        self.assertIn(f'data:image/png;base64,{image_payload}', answer)
        self.assertIn('width="120"', answer)
        self.assertEqual(answer.count("[附件或媒体内容]"), 1)

    def test_rejects_page_without_question_sections(self):
        with self.assertRaisesRegex(ValueError, "没有找到题目内容"):
            parse_exam_mark_paper("<html><body>empty</body></html>")


    def test_parses_question_mark_page_into_reusable_answer_content(self):
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
          <div class="hiddenTitle"><p>实现学生信息录入与查询。</p></div>
        </div>
        <div class="infoHead"><h2>张同学 <span class="markStatus">待批阅</span></h2>
          <span class="xuehao">s001</span></div>
        <div id="stuAnswer_q1"><div class="answerCon stuAnswerWords">
          <p>学生答案内容</p>
        </div></div>
        <div id="correctanswer_q1"></div>
        """

        page = parse_exam_question_mark_paper(
            html, referer="https://example.test/markquestionnew"
        )

        self.assertEqual(page.student_name, "张同学")
        self.assertEqual(page.student_id, "s001")
        self.assertEqual(page.answer_id, "answer-1")
        question = page.content.questions[0]
        self.assertEqual(question.question_id, "q1")
        self.assertEqual(question.number, "1")
        self.assertEqual(question.question_type, "简答题")
        self.assertEqual(question.score, 33.0)
        self.assertIn("实现学生信息录入与查询", question.stem_html)
        self.assertIn("学生答案内容", question.student_answer_html)
        self.assertEqual(
            page.content.submission.action.split("?", 1)[0],
            "/mooc2-ans/exam/test/submit-markquestion",
        )
        self.assertIn(("scoreq1", ""), page.content.submission.fields)

if __name__ == "__main__":
    unittest.main()
