import os
import json
import requests
from requests.exceptions import ReadTimeout
from core.config import AI_CONFIG_FILE, DEFAULT_AI_SYSTEM_PROMPT
from core.logger import get_logger

logger = get_logger()

class DiscreteMathAIService:
    """离散数学大模型 API 客户端接口 (使用 requests 库以实现免依赖安装)"""
    
    def __init__(self):
        self.config_path = AI_CONFIG_FILE
        self.api_key = ""
        self.base_url = "https://api.deepseek.com/v1"
        self.model = "deepseek-chat"
        self.endpoint_type = "chat_completions"
        self.system_prompt = DEFAULT_AI_SYSTEM_PROMPT
        self.load_config()

    def load_config(self):
        """从 JSON 配置文件加载 AI 参数"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.api_key = data.get("api_key", "")
                    self.base_url = data.get("base_url", "https://api.deepseek.com/v1")
                    self.model = data.get("model", "deepseek-chat")
                    self.endpoint_type = data.get("endpoint_type", "chat_completions")
                    self.system_prompt = data.get("system_prompt", DEFAULT_AI_SYSTEM_PROMPT)
            except Exception:
                # 若读取解析失败，保持默认值
                pass
        else:
            self.save_config()

    def save_config(self):
        """保存 AI 参数到配置文件"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            data = {
                "api_key": self.api_key,
                "base_url": self.base_url,
                "model": self.model,
                "endpoint_type": self.endpoint_type,
                "system_prompt": self.system_prompt
            }
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return True
        except Exception:
            return False

    def generate_reply_suggestion(self, student_question: str) -> str:
        """调用大模型为学生的提问生成答疑草稿"""
        if not self.api_key:
            return "错误：未配置 AI API Key，请点击顶部『AI设置』进行配置。"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            stream_url, stream_data = self._build_chat_completions_payload(student_question, for_test=False)
            stream_content = self._send_streaming_chat_request(stream_url, stream_data, headers)
            if stream_content is not None:
                return stream_content

            url, data = self._build_request_payload(student_question, for_test=False)
            content = self._send_generation_request(url, data, headers)
            if content is not None:
                return content

            # /responses 已完成但没有正文时，再回退到更兼容的非流式 chat/completions
            if self.endpoint_type == "responses":
                fallback_url, fallback_data = self._build_chat_completions_payload(student_question, for_test=False)
                logger.warning("AI API /responses 返回空正文，自动回退到非流式 /chat/completions")
                fallback_content = self._send_generation_request(fallback_url, fallback_data, headers)
                if fallback_content is not None:
                    return fallback_content

            return "错误：API 返回了空内容或非兼容响应格式，未解析到有效回复。"
        except Exception as e:
            logger.error(f"AI API 请求异常: {str(e)}")
            return f"错误：调用 AI 服务发生异常：{str(e)}"

    def _extract_reply_content(self, res_json) -> str | None:
        """从兼容 OpenAI 的响应中提取有效文本，空串视为失败。"""
        if self.endpoint_type == "responses":
            content = self._extract_responses_content(res_json)
            if content is not None:
                return content

        choices = res_json.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()

            text = choices[0].get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()

        # 兼容部分聚合接口直接返回 output / response 字段
        for key in ("output", "response", "content", "answer"):
            value = res_json.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        return None

    def _build_request_payload(self, student_question: str, for_test: bool = False):
        """根据接口类型构造 URL 和请求体。"""
        user_prompt = "ping" if for_test else f"学生提问：'{student_question}'。请给出详细的启发式解答。"
        base_url = self.base_url.rstrip("/")

        if self.endpoint_type == "responses":
            url = self._build_endpoint_url(base_url, "responses")
            if for_test:
                data = {
                    "model": self.model,
                    "input": user_prompt
                }
            else:
                data = {
                    "model": self.model,
                    "input": [
                        {"role": "system", "content": [{"type": "input_text", "text": self.system_prompt}]},
                        {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]}
                    ],
                    "temperature": 0.3
                }
            return url, data

        return self._build_chat_completions_payload(student_question, for_test=for_test)

    def _build_chat_completions_payload(self, student_question: str, for_test: bool = False):
        user_prompt = "ping" if for_test else f"学生提问：'{student_question}'。请给出详细的启发式解答。"
        base_url = self.base_url.rstrip("/")
        url = self._build_endpoint_url(base_url, "chat/completions")
        data = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": user_prompt}
            ]
        }
        if not for_test:
            data["messages"].insert(0, {"role": "system", "content": self.system_prompt})
            data["temperature"] = 0.3
        return url, data

    def _build_endpoint_url(self, base_url: str, suffix: str) -> str:
        """兼容 base_url 为 host、/v1 或 /beta 三种形式。"""
        trimmed = base_url.rstrip("/")
        if trimmed.endswith("/v1") or trimmed.endswith("/beta"):
            return f"{trimmed}/{suffix}"
        return f"{trimmed}/v1/{suffix}"

    def _send_generation_request(self, url: str, data: dict, headers: dict) -> str | None:
        logger.info("========== AI API 发起请求 ==========")
        logger.info(f"URL: {url}")
        logger.info(f"Payload: {json.dumps(data, ensure_ascii=False, indent=2)}")
        logger.info("=====================================")

        response = requests.post(url, headers=headers, json=data, timeout=120)
        response.encoding = "utf-8"
        if response.status_code != 200:
            logger.error(f"AI API 返回失败: {response.status_code} - {response.text}")
            raise RuntimeError(f"API 返回代码 {response.status_code}\n{response.text}")

        logger.info(f"AI API 原始返回内容: {response.text}")
        res_json = response.json()
        return self._extract_reply_content(res_json)

    def _send_streaming_chat_request(self, url: str, data: dict, headers: dict) -> str | None:
        stream_data = dict(data)
        stream_data["stream"] = True

        logger.info("========== AI API 流式回退请求 ==========")
        logger.info(f"URL: {url}")
        logger.info(f"Payload: {json.dumps(stream_data, ensure_ascii=False, indent=2)}")
        logger.info("=======================================")

        response = requests.post(url, headers=headers, json=stream_data, timeout=120, stream=True)
        response.encoding = "utf-8"
        if response.status_code != 200:
            logger.error(f"AI API 流式返回失败: {response.status_code}")
            return None

        chunks = []
        for raw_line in response.iter_lines(decode_unicode=True):
            line = (raw_line or "").strip()
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk_json = json.loads(payload)
            except Exception:
                continue
            delta = ((chunk_json.get("choices") or [{}])[0].get("delta") or {})
            content = delta.get("content")
            if isinstance(content, str) and content:
                chunks.append(content)

        content = "".join(chunks).strip()
        if content:
            logger.info(f"AI API 流式回退成功，字符数: {len(content)}")
            return content
        return None

    def _extract_responses_content(self, res_json) -> str | None:
        """从 /v1/responses 返回中提取文本。"""
        output = res_json.get("output")
        if isinstance(output, list):
            text_parts = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content_list = item.get("content")
                if not isinstance(content_list, list):
                    continue
                for content_item in content_list:
                    if not isinstance(content_item, dict):
                        continue
                    text = content_item.get("text")
                    if isinstance(text, str) and text.strip():
                        text_parts.append(text.strip())
            if text_parts:
                return "\n".join(text_parts)

        output_text = res_json.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        return None

    def test_connection(self) -> tuple:
        """测试连接大模型接口"""
        if not self.api_key:
            return False, "API Key 不能为空"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        url, data = self._build_request_payload("ping", for_test=True)

        try:
            response = requests.post(url, headers=headers, json=data, timeout=(10, 30))
            if response.status_code == 200:
                return True, "连接测试成功！API 能正常通信。"
            else:
                return False, f"测试失败 (HTTP {response.status_code}): {response.text[:200]}"
        except ReadTimeout:
            return False, "网络请求超时：服务在 30 秒内未返回。该接口可能可用，但当前响应过慢。"
        except Exception as e:
            return False, f"网络请求异常: {str(e)}"
