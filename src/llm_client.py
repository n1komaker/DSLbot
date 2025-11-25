import os
from dotenv import load_dotenv
from zai import ZhipuAiClient

load_dotenv()


class LLMService:
    def __init__(self):
        self.api_key = os.getenv("ZHIPU_API_KEY")
        self.model_name = os.getenv("ZHIPU_MODEL_NAME", "glm-4-flash")

        if not self.api_key:
            raise ValueError("CRITICAL ERROR: ZHIPU_API_KEY not found in .env file!")

        self.client = ZhipuAiClient(api_key=self.api_key)

    def detect_intent(self, user_input, candidates):
        candidates_str = ", ".join([f'"{c}"' for c in candidates])
        system_content = (
            f"Select the best intent from: [{candidates_str}]\n"
            f"User Input: \"{user_input}\"\n"
            f"Output only the exact intent string. Return 'UNKNOWN' if no match."
        )

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "user", "content": system_content}
            ],
            temperature=0.01,
        )

        content = response.choices[0].message.content.strip()
        clean_intent = content.replace('"', '').replace("'", "")

        if clean_intent in candidates:
            return clean_intent

        for c in candidates:
            if c in clean_intent:
                return c

        return "UNKNOWN"