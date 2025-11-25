import sys
import re
from lark import Transformer


class ConsoleAdapter:
    def send(self, text): print(f"[Bot]: {text}")

    def receive(self): return input("[User]: ")


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
        raw = items[0].value[1:-1] if hasattr(items[0], 'value') else str(items[0]).strip('"')
        return {'type': 'say', 'content': raw}

    def listen_cmd(self, items):
        var = str(items[0]) if items else None
        return {'type': 'listen', 'var': var}

    def goto_cmd(self, items):
        return {'type': 'goto', 'target': str(items[0])}

    def exit_cmd(self, items):
        return {'type': 'exit'}

    def set_cmd(self, items):
        return {'type': 'set', 'var': str(items[0]), 'value': items[1]}

    def call_cmd(self, items):
        func = str(items[0])
        res = str(items[-1])
        args = items[1:-1]
        return {'type': 'call', 'func': func, 'args': args, 'result': res}

    def if_cmd(self, items):
        return {'type': 'if', 'left': items[0], 'op': str(items[1]), 'right': items[2], 'target': str(items[3])}

    def sql_cmd(self, items):
        q = items[0].value[1:-1]
        res = str(items[1]) if len(items) > 1 else None
        return {'type': 'sql', 'query': q, 'result': res}

    def process_cmd(self, items):
        cases = {}
        default = None
        for item in items:
            if item['type'] == 'case':
                cases[item['intent']] = item['action']
            elif item['type'] == 'default':
                default = item['action']
        return {'type': 'process', 'cases': cases, 'default': default}

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
    def __init__(self, flows, db_manager=None, io_adapter=None):
        self.flows = flows
        self.llm_service = None
        self.external_functions = {}
        self.db = db_manager
        self.io = io_adapter if io_adapter else ConsoleAdapter()

    def set_llm_service(self, service):
        self.llm_service = service

    def register_function(self, name, func):
        self.external_functions[name] = func

    def _resolve_value(self, val, context):
        if isinstance(val, dict) and val.get('type') == 'var_ref':
            return context.get_var(val['name'])
        return val

    def _execute_sql(self, query, context):
        if not self.db: return 0
        pattern = r"(\$[a-zA-Z0-9_]+)"
        matches = re.findall(pattern, query)
        params = [context.get_var(var) for var in matches]
        safe_query = re.sub(pattern, "?", query)
        try:
            if safe_query.strip().upper().startswith("SELECT"):
                res = self.db.fetch_one(safe_query, tuple(params))
                return res if res is not None else 0
            else:
                return self.db.execute(safe_query, tuple(params))
        except:
            return 0

    def _execute_instruction(self, cmd, context, mock_inputs=None):
        if not isinstance(cmd, dict): return False, None
        ctype = cmd['type']

        if ctype == 'say':
            text = context.format_string(cmd['content'])
            self.io.send(text)
            return False, None

        elif ctype == 'listen':
            val = mock_inputs.pop(0) if mock_inputs else self.io.receive()
            if val == "EXIT":
                return True, 'Exit'
            context.history.append(val)
            if cmd.get('var'): context.set_var(cmd['var'], val)
            return False, None

        elif ctype == 'sql':
            res = self._execute_sql(cmd['query'], context)
            if cmd['result']: context.set_var(cmd['result'], res)
            return False, None

        elif ctype == 'set':
            val = self._resolve_value(cmd['value'], context)
            context.set_var(cmd['var'], val)
            return False, None

        elif ctype == 'call':
            if cmd['func'] in self.external_functions:
                args = [self._resolve_value(a, context) for a in cmd['args']]
                try:
                    res = self.external_functions[cmd['func']](*args)
                    context.set_var(cmd['result'], res)
                except:
                    context.set_var(cmd['result'], "error")
            return False, None

        elif ctype == 'if':
            l, r = self._resolve_value(cmd['left'], context), self._resolve_value(cmd['right'], context)
            op = cmd['op']
            met = False
            sl, sr = str(l), str(r)
            if op == '==':
                met = (sl == sr)
            elif op == '!=':
                met = (sl != sr)
            try:
                if op == '>':
                    met = (float(l) > float(r))
                elif op == '<':
                    met = (float(l) < float(r))
            except:
                pass
            if met: return True, cmd['target']
            return False, None

        elif ctype == 'process':
            if not self.llm_service: return True, 'Exit'
            last = context.history[-1] if context.history else ""
            cands = list(cmd['cases'].keys())
            intent = self.llm_service.detect_intent(last, cands)
            match = cmd['cases'].get(intent, cmd['default'])
            if match: return self._execute_instruction(match, context, mock_inputs)
            return False, None

        elif ctype == 'goto':
            return True, cmd['target']
        elif ctype == 'exit':
            return True, 'Exit'
        return False, None

    def run(self, bot_name, mock_inputs=None):
        if bot_name not in self.flows: return
        flow = self.flows[bot_name]
        ctx = Context()
        print(f"--- Bot {bot_name} Started ---")

        max_steps = 1000
        steps = 0

        while ctx.state != 'Exit':
            if steps > max_steps:
                print("Error: Max execution steps reached (Infinite Loop detected).")
                break

            if ctx.state not in flow: break
            cmds = flow[ctx.state]
            idx = 0
            while idx < len(cmds):
                brk, nxt = self._execute_instruction(cmds[idx], ctx, mock_inputs)
                if brk:
                    if nxt: ctx.state = nxt
                    break
                idx += 1
            steps += 1

        self.io.send("Session Ended")
        print("--- Session Ended ---")