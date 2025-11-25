class MockLLMService:
    def __init__(self):
        self.mock_rules = {
            "办理流量包": "办理流量包",
            "办理流量": "办理流量包",
            "买流量": "办理流量包",
            "查流量": "查询流量",
            "查询流量": "查询流量",
            "流量": "查询流量",
            "查话费": "查询话费",
            "话费": "查询话费",
            "充值": "充值缴费",
            "宽带": "宽带故障",
            "修": "宽带故障",
            "人工": "人工服务",
            "确认": "确认",
            "是": "确认",
            "拒绝": "拒绝",
            "否": "拒绝",
            "没有": "没有了",
            "结束": "结束",
            "还有": "还有",
            "修改姓名": "修改姓名",
            "修改邮箱": "修改邮箱",
            "修改住址": "修改住址",
            "退出": "退出"
        }

    def detect_intent(self, user_input, candidates):
        for key, intent in self.mock_rules.items():
            if key in user_input:
                if intent in candidates:
                    return intent
        return "UNKNOWN"


class TestAdapter:
    def __init__(self, user_inputs):
        self.user_inputs = user_inputs
        self.bot_outputs = []

    def send(self, text):
        self.bot_outputs.append(text)

    def receive(self):
        if self.user_inputs:
            return self.user_inputs.pop(0)
        return "EXIT"

    def get_last_output(self):
        return self.bot_outputs[-1] if self.bot_outputs else ""

    def get_all_output(self):
        return "\n".join(self.bot_outputs)