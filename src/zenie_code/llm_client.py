import json
import re

import requests


def parse_json_object(text):
    if isinstance(text, dict):
        return text
    if text is None:
        raise ValueError("Empty model response")

    text = str(text).strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


class LLMClient:
    def __init__(
        self,
        base_url,
        api_key,
        model,
        temperature=0.2,
        max_tokens=4096,
        timeout=600,
        structured_output=True,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.structured_output = structured_output

    def chat(
        self,
        messages,
        response_format=None,
        temperature=None,
        max_tokens=None,
        seed=None,
    ):
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key != "none":
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        if seed is not None:
            payload["seed"] = seed
        if response_format and self.structured_output:
            payload["response_format"] = response_format

        response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)

        # Some OpenAI-compatible local servers do not support response_format.
        # Retry once without it rather than breaking the entire agent.
        if response.status_code >= 400 and "response_format" in payload:
            payload.pop("response_format", None)
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)

        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def chat_json(self, messages, schema, **kwargs):
        response_format = {
            "type": "json_schema",
            "json_schema": schema,
        }
        raw = self.chat(messages, response_format=response_format, **kwargs)
        return parse_json_object(raw)
