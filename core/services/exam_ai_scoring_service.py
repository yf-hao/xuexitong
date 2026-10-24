import hashlib
import json
import os

from bs4 import BeautifulSoup

from core.apis.ai_service import DiscreteMathAIService
from core.apis.exam_api import (
    download_exam_attachment, exam_attachment_cache_path,
)
from core.utils.attachment_preview import extract_attachment_scoring_content
from core.utils.image_utils import validated_image_data_uri

OBJECTIVE_QUESTION_TYPES = {"单选题", "多选题", "判断题"}


def student_answer_image_data_uris(answer_html):
    answer_soup = BeautifulSoup(answer_html or "", "html.parser")
    return [
        image_data_uri
        for image in answer_soup.find_all("img")
        if (image_data_uri := validated_image_data_uri(image.get("src", "")))
    ]


class ExamAIScoringService:
    MAX_ATTACHMENT_TEXT_CHARS = 100_000

    def __init__(self, ai_service_factory=None):
        self.ai_service_factory = ai_service_factory or DiscreteMathAIService

    @staticmethod
    def question_key(exam_id, question):
        question_identity = question.question_id or json.dumps(
            [question.question_type, question.number],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        identity = json.dumps(
            [str(exam_id), question_identity],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

    @classmethod
    def rubric_settings_key(cls, exam_id, question):
        return f"exam_ai_rubrics/{cls.question_key(exam_id, question)}"

    @staticmethod
    def rubric_fingerprint(rubric):
        normalized = str(rubric or "").strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def is_subjective_question(question):
        return question.question_type not in OBJECTIVE_QUESTION_TYPES

    @staticmethod
    def build_scoring_data(question, rubric=""):
        return {
            "question": BeautifulSoup(
                question.stem_html or "", "html.parser"
            ).get_text("\n", strip=True),
            "maximum_score": question.score,
            "reference_answer": BeautifulSoup(
                question.correct_answer_html or "", "html.parser"
            ).get_text("\n", strip=True),
            "reference_explanation": BeautifulSoup(
                question.explanation_html or "", "html.parser"
            ).get_text("\n", strip=True),
            "student_answer": BeautifulSoup(
                question.student_answer_html or "", "html.parser"
            ).get_text("\n", strip=True),
            "student_answer_images": student_answer_image_data_uris(
                question.student_answer_html
            ),
            "additional_scoring_requirements": str(rubric or "").strip(),
        }

    def score(self, scoring_data, attachments, session):
        attachment_texts = []
        answer_images = [
            {
                "data_uri": image_data_uri,
                "context": f"答卷中的图片 {image_index}",
            }
            for image_index, image_data_uri in enumerate(
                scoring_data.get("student_answer_images") or [], 1
            )
        ]
        total_chars = 0
        for attachment in attachments:
            if session is None:
                raise RuntimeError("当前没有可用的学习通登录会话")
            cache_path = exam_attachment_cache_path(
                attachment.object_id, attachment.filename
            )
            if not os.path.isfile(cache_path) or os.path.getsize(cache_path) == 0:
                download_exam_attachment(
                    session, attachment.object_id, cache_path
                )
            text, image_data_uris = extract_attachment_scoring_content(
                cache_path
            )
            total_chars += len(text)
            if total_chars > self.MAX_ATTACHMENT_TEXT_CHARS:
                raise ValueError(
                    "附件文本总量超过 100,000 字符，无法进行 AI 评分"
                )
            for image_index, image_data_uri in enumerate(image_data_uris, 1):
                answer_images.append({
                    "data_uri": image_data_uri,
                    "context": (
                        f"附件 {attachment.filename} 中的图片 {image_index}，"
                        f"对应正文标记 [图片 {image_index}]"
                    ),
                })
            attachment_texts.append({
                "filename": attachment.filename,
                "text": text,
            })

        prepared_data = dict(scoring_data)
        prepared_data["student_attachments"] = attachment_texts
        prepared_data["student_answer_images"] = answer_images
        return self.ai_service_factory().generate_exam_score(prepared_data)