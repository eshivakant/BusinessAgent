from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx


class LLMClient:
    """OpenRouter-compatible LLM client for metadata extraction and OCR."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        request_timeout: int = 60,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.request_timeout = request_timeout
        self.client = httpx.Client(timeout=request_timeout)

    def extract_metadata(
        self,
        document_text: str,
        source_uri: str,
    ) -> DocumentMetadata:
        """
        Extract document metadata using LLM.
        Returns: document_type, vendor, department, keywords.
        """
        prompt = f"""Analyze this document and extract metadata in JSON format.
Document source: {source_uri}
Document content:
{document_text[:2000]}

Return JSON with these exact fields:
{{
  "document_type": "invoice|report|contract|receipt|statement|other",
  "vendor": "vendor name or null",
  "department": "department name or null",
  "keywords": ["keyword1", "keyword2"]
}}

Only return valid JSON, no other text."""

        response_text = self._call_llm(
            model="meta-llama/llama-2-7b-chat",
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            data = json.loads(response_text)
            return DocumentMetadata(
                document_type=data.get("document_type", "other"),
                vendor=data.get("vendor"),
                department=data.get("department"),
                keywords=data.get("keywords", []),
            )
        except (json.JSONDecodeError, KeyError):
            return DocumentMetadata(
                document_type="other",
                vendor=None,
                department=None,
                keywords=[],
            )

    def ocr_image(self, image_path: str | Path) -> str:
        """
        Extract text from image using multimodal LLM (OCR).
        Supports: png, jpg, jpeg, gif, webp
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise ValueError(f"Image not found: {image_path}")

        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # Determine media type
        suffix = image_path.suffix.lower()
        media_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        media_type = media_type_map.get(suffix, "image/png")

        response_text = self._call_llm(
            model="gpt-4-vision",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Extract all text from this image. Return only the extracted text, nothing else.",
                        },
                    ],
                }
            ],
        )

        return response_text.strip()

    def _call_llm(self, model: str, messages: list[dict[str, Any]]) -> str:
        """Make a request to OpenRouter API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1000,
        }

        try:
            response = self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            raise ValueError("No response from LLM")
        except httpx.HTTPError as e:
            raise RuntimeError(f"LLM API error: {e}")


class DocumentMetadata:
    """Extracted document metadata."""

    def __init__(
        self,
        document_type: str,
        vendor: str | None = None,
        department: str | None = None,
        keywords: list[str] | None = None,
    ) -> None:
        self.document_type = document_type
        self.vendor = vendor
        self.department = department
        self.keywords = keywords or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_type": self.document_type,
            "vendor": self.vendor,
            "department": self.department,
            "keywords": self.keywords,
        }
