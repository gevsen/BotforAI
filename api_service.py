import aiohttp
import json
# Assuming config is available or values are passed directly
# import config

class APIService:
    def __init__(self, api_key: str, chat_api_url: str, image_api_url: str, session: aiohttp.ClientSession):
        self.api_key = api_key
        self.chat_api_url = chat_api_url
        self.image_api_url = image_api_url
        self.session = session

    async def chat_completion(self, model: str, messages: list, temperature: float, max_tokens: int = None) -> tuple[str | None, str | None]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with self.session.post(f'{self.chat_api_url}/chat/completions', json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content")
                    return content, None
                else:
                    error_message = await response.text()
                    return None, f"Error: {response.status} - {error_message}"
        except Exception as e:
            return None, f"Exception: {str(e)}"

    async def generate_image(self, model: str, prompt: str, size: str = "1024x1024", response_format: str = "url") -> tuple[str | None, str | None]:
        payload = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "response_format": response_format,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with self.session.post(f'{self.image_api_url}/images/generations', json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    image_url = data.get("data", [{}])[0].get(response_format) # DALL-E 3 returns 'url' or 'b64_json'
                    return image_url, None
                else:
                    error_message = await response.text()
                    return None, f"Error: {response.status} - {error_message}"
        except Exception as e:
            return None, f"Exception: {str(e)}"
