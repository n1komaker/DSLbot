import sys
from lark import Transformer, Tree

class Context:
    """运行时上下文：记录当前状态、变量和对话历史"""
    def __init__(self, initial_state='Start'):
        self.state = initial_state
        self.variables = {}
        self.history = []

class BotInterpreter(Transformer):
    """将Lark解析的AST转换为字典结构"""
    def __init__(self):
        super().__init__()
        self.flows = {}

    def bot_def(self, items):
        bot_name = str(items[0])
        state_dict = {k: v for k, v in items[1:]}
        self.flows[bot_name] = state_dict
        return bot_name

    def state_def(self, items):
        state_name = str(items[0])
        instructions = list(items[1:])
        return (state_name, instructions)

    def say_cmd(self, items):
        return {'type': 'say', 'content': items[0].strip('"')}

    def listen_cmd(self, items):
        return {'type': 'listen'}

    def goto_cmd(self, items):
        return {'type': 'goto', 'target': str(items[0])}

    def exit_cmd(self, items):
        return {'type': 'exit'}

    def process_cmd(self, items):
        """处理 process 块"""
        cases = {}
        default_action = None

        for item in items:
            if item['type'] == 'case':
                cases[item['intent']] = item['action']
            elif item['type'] == 'default':
                default_action = item['action']

        return {
            'type': 'process',
            'cases': cases,
            'default': default_action
        }

    def case_rule(self, items):
        intent = items[0].strip('"')
        action = items[1]
        return {'type': 'case', 'intent': intent, 'action': action}

    def default_rule(self, items):
        action = items[0]
        return {'type': 'default', 'action': action}

    def action(self, items):
        return items[0]


class RuntimeEngine:
    def __init__(self, flows):
        self.flows = flows
        self.llm_service = None

    def set_llm_service(self, service):
        self.llm_service = service

    def _execute_instruction(self, cmd, context, mock_inputs=None):
        """执行指令
        should_break: 是否中断当前指令列表的执行
        next_state: 如果发生了跳转，这里是新状态名；否则为 None
        """

        if cmd['type'] == 'say':
            print(f"[Bot]: {cmd['content']}")
            return False, None

        elif cmd['type'] == 'listen':
            if mock_inputs:
                if len(mock_inputs) > 0:
                    user_input = mock_inputs.pop(0)
                    print(f"[User] (Mock): {user_input}")
                else:
                    print("Error: Mock inputs exhausted!")
                    user_input = ""
            else:
                user_input = input("[User]: ")
            context.history.append(user_input)
            return False, None

        elif cmd['type'] == 'goto':
            return True, cmd['target']

        elif cmd['type'] == 'exit':
            return True, 'Exit'

        elif cmd['type'] == 'process':
            if not self.llm_service:
                print("Error: LLM Service not configured.")
                return True, 'Exit'

            last_input = context.history[-1] if context.history else ""
            candidates = list(cmd['cases'].keys())

            detected_intent = self.llm_service.detect_intent(last_input, candidates)

            matched_action = None
            if detected_intent in cmd['cases']:
                matched_action = cmd['cases'][detected_intent]
            elif cmd['default']:
                matched_action = cmd['default']

            if matched_action:
                return self._execute_instruction(matched_action, context, mock_inputs)

            return False, None

        return False, None

    def run(self, bot_name, mock_inputs=None):
        if bot_name not in self.flows:
            print(f"Error: Bot '{bot_name}' not found.")
            return

        flow = self.flows[bot_name]
        context = Context()

        print(f"--- Bot {bot_name} Started ---")

        while context.state != 'Exit':
            current_state_name = context.state
            if current_state_name not in flow:
                print(f"Error: State '{current_state_name}' not found.")
                break

            instructions = flow[current_state_name]

            i = 0
            while i < len(instructions):
                cmd = instructions[i]

                should_break, next_state = self._execute_instruction(cmd, context, mock_inputs)

                if should_break:
                    if next_state:
                        context.state = next_state
                    break

                i += 1

        print("--- Session Ended ---")