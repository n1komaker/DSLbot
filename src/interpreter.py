import sys
import re
from lark import Transformer


class Context:
    def __init__(self, initial_state='Start'):
        self.state = initial_state
        self.variables = {}
        self.history = []

    def set_var(self, name, value):
        self.variables[name] = value

    def get_var(self, name):
        return self.variables.get(name, "")

    def format_string(self, text):
        for key, val in self.variables.items():
            text = text.replace(key, str(val))
        return text


class BotInterpreter(Transformer):
    def __init__(self):
        super().__init__()
        self.flows = {}

    def bot_def(self, items):
        self.flows[str(items[0])] = {k: v for k, v in items[1:]}
        return str(items[0])

    def state_def(self, items):
        return (str(items[0]), list(items[1:]))

    def instruction(self, items):
        return items[0]

    def say_cmd(self, items):
        raw_text = items[0].value[1:-1] if hasattr(items[0], 'value') else str(items[0]).strip('"')
        return {'type': 'say', 'content': raw_text}

    def listen_cmd(self, items):
        var_name = str(items[0]) if items else None
        return {'type': 'listen', 'var': var_name}

    def goto_cmd(self, items):
        return {'type': 'goto', 'target': str(items[0])}

    def exit_cmd(self, items):
        return {'type': 'exit'}

    def set_cmd(self, items):
        return {'type': 'set', 'var': str(items[0]), 'value': items[1]}

    def call_cmd(self, items):
        func_name = str(items[0])
        result_var = str(items[-1])
        args = items[1:-1]
        return {'type': 'call', 'func': func_name, 'args': args, 'result': result_var}

    def if_cmd(self, items):
        return {
            'type': 'if',
            'left': items[0],
            'op': str(items[1]),
            'right': items[2],
            'target': str(items[3])
        }

    def sql_cmd(self, items):
        query = items[0].value[1:-1]
        result_var = str(items[1]) if len(items) > 1 else None
        return {'type': 'sql', 'query': query, 'result': result_var}

    def process_cmd(self, items):
        cases = {}
        default_action = None
        for item in items:
            if item['type'] == 'case':
                cases[item['intent']] = item['action']
            elif item['type'] == 'default':
                default_action = item['action']
        return {'type': 'process', 'cases': cases, 'default': default_action}

    def case_rule(self, items):
        return {'type': 'case', 'intent': str(items[0]).strip('"'), 'action': items[1]}

    def default_rule(self, items):
        return {'type': 'default', 'action': items[0]}

    def action(self, items):
        return items[0]

    def value(self, items):
        token = items[0]
        if token.type == 'STRING':
            return token.value[1:-1]
        elif token.type == 'INT':
            return int(token.value)
        elif token.type == 'VAR_NAME':
            return {'type': 'var_ref', 'name': token.value}
        return token.value


class RuntimeEngine:
    def __init__(self, flows, db_manager=None):
        self.flows = flows
        self.llm_service = None
        self.external_functions = {}
        self.db = db_manager

    def set_llm_service(self, service):
        self.llm_service = service

    def register_function(self, name, func):
        self.external_functions[name] = func

    def _resolve_value(self, val, context):
        if isinstance(val, dict) and val.get('type') == 'var_ref':
            return context.get_var(val['name'])
        return val

    def _execute_sql(self, query, context):
        if not self.db:
            return 0

        pattern = r"(\$[a-zA-Z0-9_]+)"
        matches = re.findall(pattern, query)

        params = []
        for var_name in matches:
            val = context.get_var(var_name)
            params.append(val)

        safe_query = re.sub(pattern, "?", query)

        try:
            if safe_query.strip().upper().startswith("SELECT"):
                res = self.db.fetch_one(safe_query, tuple(params))
                return res if res is not None else 0
            else:
                return self.db.execute(safe_query, tuple(params))
        except Exception:
            return 0

    def _execute_instruction(self, cmd, context, mock_inputs=None):
        if not isinstance(cmd, dict): return False, None

        cmd_type = cmd['type']

        if cmd_type == 'say':
            text = context.format_string(cmd['content'])
            print(f"[Bot]: {text}")
            return False, None

        elif cmd_type == 'listen':
            if mock_inputs is not None and len(mock_inputs) > 0:
                val = mock_inputs.pop(0)
                print(f"[User] (Mock): {val}")
            else:
                val = input("[User]: ")

            context.history.append(val)
            if cmd.get('var'):
                context.set_var(cmd['var'], val)
            return False, None

        elif cmd_type == 'set':
            val = self._resolve_value(cmd['value'], context)
            context.set_var(cmd['var'], val)
            return False, None

        elif cmd_type == 'sql':
            result = self._execute_sql(cmd['query'], context)
            if cmd['result']:
                context.set_var(cmd['result'], result)
            return False, None

        elif cmd_type == 'call':
            func_name = cmd['func']
            if func_name in self.external_functions:
                resolved_args = [self._resolve_value(arg, context) for arg in cmd['args']]
                try:
                    result = self.external_functions[func_name](*resolved_args)
                    context.set_var(cmd['result'], result)
                except Exception:
                    context.set_var(cmd['result'], "error")
            return False, None

        elif cmd_type == 'if':
            left = self._resolve_value(cmd['left'], context)
            right = self._resolve_value(cmd['right'], context)
            op = cmd['op']
            target = cmd['target']

            condition_met = False
            s_left, s_right = str(left), str(right)
            if op == '==':
                condition_met = (s_left == s_right)
            elif op == '!=':
                condition_met = (s_left != s_right)
            try:
                f_left, f_right = float(left), float(right)
                if op == '>':
                    condition_met = (f_left > f_right)
                elif op == '<':
                    condition_met = (f_left < f_right)
            except:
                pass

            if condition_met:
                return True, target
            return False, None

        elif cmd_type == 'goto':
            return True, cmd['target']
        elif cmd_type == 'exit':
            return True, 'Exit'

        elif cmd_type == 'process':
            if not self.llm_service: return True, 'Exit'
            last_input = context.history[-1] if context.history else ""
            candidates = list(cmd['cases'].keys())
            intent = self.llm_service.detect_intent(last_input, candidates)

            matched = cmd['cases'].get(intent, cmd['default'])
            if matched:
                return self._execute_instruction(matched, context, mock_inputs)
            return False, None

        return False, None

    def run(self, bot_name, mock_inputs=None):
        if bot_name not in self.flows: return
        flow = self.flows[bot_name]
        context = Context()
        print(f"--- Bot {bot_name} Started ---")

        while context.state != 'Exit':
            if context.state not in flow: break
            cmds = flow[context.state]
            idx = 0
            while idx < len(cmds):
                should_break, next_state = self._execute_instruction(cmds[idx], context, mock_inputs)
                if should_break:
                    if next_state: context.state = next_state
                    break
                idx += 1
        print("--- Session Ended ---")