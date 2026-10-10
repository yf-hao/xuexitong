import unittest

from core.utils.exam_ip_analysis import (
    HIGH_RISK,
    MEDIUM_RISK,
    REVIEW_RISK,
    analyze_exam_ip_risks,
)


class ExamIpRiskAnalysisTests(unittest.TestCase):
    def _record(self, student_id, submit_time, duration, ip="192.0.2.1/河南"):
        return {
            "id": student_id,
            "createUserName": f"学生{student_id}",
            "loginName": str(student_id),
            "submitTime": submit_time,
            "examConsumeTime": duration,
            "receiveIp": ip,
        }

    def test_flags_close_estimated_start_as_high_risk(self):
        groups = analyze_exam_ip_risks([
            self._record(1, "2026-09-24 14:00", "20分钟"),
            self._record(2, "2026-09-24 14:35", "30分钟"),
        ])

        self.assertEqual(groups[0]["risk_level"], HIGH_RISK)
        self.assertIn("14:05", groups[0]["evidence"])
        self.assertIn("5 分钟", groups[0]["evidence"])

    def test_flags_two_hour_submission_gap_as_medium_risk(self):
        groups = analyze_exam_ip_risks([
            self._record(1, "09-24 14:00", "30分钟"),
            self._record(2, "09-24 16:30", "30分钟"),
        ])

        self.assertEqual(groups[0]["risk_level"], MEDIUM_RISK)
        self.assertIn("2 小时阈值", groups[0]["evidence"])

    def test_keeps_shared_ip_without_matching_time_rule_as_review_only(self):
        groups = analyze_exam_ip_risks([
            self._record(1, "2026-09-24 14:00", "30分钟"),
            self._record(2, "2026-09-24 15:00", "30分钟"),
        ])

        self.assertEqual(groups[0]["risk_level"], REVIEW_RISK)

    def test_ignores_unique_ips(self):
        groups = analyze_exam_ip_risks([
            self._record(1, "2026-09-24 14:00", "30分钟"),
            self._record(2, "2026-09-24 15:00", "30分钟", "192.0.2.2/河南"),
        ])

        self.assertEqual(groups, [])


if __name__ == "__main__":
    unittest.main()