import unittest
import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(TEST_DIR, '..'))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from lark import Lark
from src.interpreter import BotInterpreter, RuntimeEngine
from src.db_manager import DBManager


class LocalMockLLMService:
    def __init__(self):
        self.mock_rules = [
            ("办理流量包", "办理流量包"),
            ("办理流量", "办理流量包"),
            ("买流量", "办理流量包"),
            ("查询流量", "查询流量"),
            ("查流量", "查询流量"),
            ("流量", "查询流量"),
            ("查话费", "查询话费"),
            ("话费", "查询话费"),
            ("充值", "充值缴费"),
            ("宽带", "宽带故障"),
            ("修", "宽带故障"),
            ("人工", "人工服务"),
            ("修改姓名", "修改姓名"),
            ("修改邮箱", "修改邮箱"),
            ("修改住址", "修改住址"),
            ("确认", "确认"),
            ("是", "确认"),
            ("拒绝", "拒绝"),
            ("否", "拒绝"),
            ("没有", "没有了"),
            ("结束", "结束"),
            ("还有", "还有"),
            ("退出", "退出")
        ]

    def detect_intent(self, user_input, candidates):
        for key, intent in self.mock_rules:
            if key in user_input:
                if intent in candidates:
                    return intent
        return "UNKNOWN"


class LocalTestAdapter:
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


TEST_DB_PATH = os.path.join(PROJECT_ROOT, 'test_bot_data.db')
REPORT_FILE = os.path.join(PROJECT_ROOT, 'test_report.txt')


class TestEnterpriseScenario(unittest.TestCase):

    def setUp(self):
        self.db = DBManager(TEST_DB_PATH)
        self.db.execute("DROP TABLE IF EXISTS users")
        self.db.execute("""
            CREATE TABLE users (
                phone TEXT PRIMARY KEY, 
                name TEXT, 
                balance REAL, 
                data_left REAL, 
                package_name TEXT, 
                broadband_status INT, 
                id_card TEXT,
                email TEXT,
                address TEXT,
                city TEXT
            )
        """)

        self.db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?)",
                        ("13800138000", "测试1", 1200.50, 50.0, "5G畅享套餐", 0, "4512", "test1@example.com",
                         "北京市海淀区科技园", "北京"))
        self.db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?)",
                        ("13900139000", "测试2", 5.00, 0.0, "4G基础套餐", 0, "8821", "test2@test.com", "上海市浦东新区",
                         "上海"))
        self.db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?)",
                        ("18900189000", "测试3", 150.00, 10.0, "家庭融合套餐", 1, "9090", "test3@isp.net",
                         "广州市天河区", "广州"))
        self.db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                        "13600136000", "测试4", 10.00, 2.0, "学生校园卡", 0, "6666", "test4@campus.edu", "武汉市洪山区",
                        "武汉"))

    def tearDown(self):
        self.db.close()
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except PermissionError:
                pass

    def load_flow(self, script_name, bot_name):
        grammar_file = os.path.join(PROJECT_ROOT, 'src', 'dsl_parser', 'grammar.lark')
        script_file = os.path.join(PROJECT_ROOT, 'examples', script_name)

        if not os.path.exists(grammar_file):
            raise FileNotFoundError(f"Fatal: Grammar not found: {grammar_file}")
        if not os.path.exists(script_file):
            raise FileNotFoundError(f"Fatal: Script not found: {script_file}")

        with open(grammar_file, 'r', encoding='utf-8') as f:
            grammar = f.read()
        with open(script_file, 'r', encoding='utf-8') as f:
            script = f.read()

        parser = Lark(grammar, parser='lalr')
        interpreter = BotInterpreter()
        ast = parser.parse(script)
        interpreter.transform(ast)

        if bot_name not in interpreter.flows:
            raise ValueError(
                f"Bot '{bot_name}' not found in {script_name}. Available: {list(interpreter.flows.keys())}")
        return interpreter.flows

    def run_engine(self, script_name, bot_name, inputs):
        flows = self.load_flow(script_name, bot_name)
        adapter = LocalTestAdapter(inputs)
        engine = RuntimeEngine(flows, db_manager=self.db, io_adapter=adapter)
        engine.set_llm_service(LocalMockLLMService())
        engine.run(bot_name)
        return adapter

    def test_1(self):
        print("\n=== Test 1: Lifecycle Topup Consumption ===")
        inputs = ["13900139000", "充值", "100", "还有", "办理流量包", "没有了"]
        adapter = self.run_engine('customer_server.bot', 'custBot', inputs)

        output = adapter.get_all_output()
        self.assertIn("充值成功", output)
        self.assertIn("办理成功", output)

        final_bal = self.db.fetch_one("SELECT balance FROM users WHERE phone='13900139000'")
        self.assertAlmostEqual(final_bal, 95.0, places=2)

    def test_2(self):
        print("\n=== Test 2: Boundary Exact Balance ===")
        inputs = ["13600136000", "办理流量包", "没有了"]
        adapter = self.run_engine('customer_server.bot', 'custBot', inputs)

        output = adapter.get_all_output()
        self.assertIn("办理成功", output)

        final_bal = self.db.fetch_one("SELECT balance FROM users WHERE phone='13600136000'")
        self.assertAlmostEqual(final_bal, 0.0, places=2)

    def test_3(self):
        print("\n=== Test 3: Security SQL Injection ===")
        malicious_input = "' OR '1'='1"
        inputs = ["13800138000", malicious_input]

        adapter = self.run_engine('profile_manager.bot', 'profBot', inputs)

        output = adapter.get_all_output()
        self.assertIn("身份验证失败", output)
        self.assertNotIn("档案信息", output)

    def test_4(self):
        print("\n=== Test 4: Parametrized Scenarios ===")
        test_cases = [
            ("User Test1", "13800138000", "办理成功", 1190.50),
            ("User Test2", "13900139000", "余额不足", 5.00)
        ]
        for desc, phone, expected_msg, expected_bal in test_cases:
            with self.subTest(scenario=desc):
                if "余额不足" in expected_msg:
                    inputs = [phone, "办理流量包", "拒绝", "没有了"]
                else:
                    inputs = [phone, "办理流量包", "没有了"]

                adapter = self.run_engine('customer_server.bot', 'custBot', inputs)
                output = adapter.get_all_output()

                self.assertIn(expected_msg, output)
                actual_bal = self.db.fetch_one(f"SELECT balance FROM users WHERE phone='{phone}'")
                self.assertAlmostEqual(actual_bal, expected_bal, places=2)

    def test_5(self):
        print("\n=== Test 5: Profile Update Persistence ===")
        inputs = ["13800138000", "4512", "修改邮箱", "new_email@test.com", "退出"]
        self.run_engine('profile_manager.bot', 'profBot', inputs)

        new_email = self.db.fetch_one("SELECT email FROM users WHERE phone='13800138000'")
        self.assertEqual(new_email, "new_email@test.com")

        inputs_verify = ["13800138000", "4512", "退出"]
        adapter_verify = self.run_engine('profile_manager.bot', 'profBot', inputs_verify)
        self.assertIn("new_email@test.com", adapter_verify.get_all_output())

    def test_6(self):
        print("\n=== Test 6: Broadband Fault Detection ===")
        inputs = ["18900189000", "宽带故障", "没有了"]
        adapter = self.run_engine('customer_server.bot', 'custBot', inputs)

        output = adapter.get_all_output()
        self.assertIn("线路信号异常", output)
        self.assertIn("错误代码: 1", output)

    def test_7(self):
        print("\n=== Test 7: Loop & Retry Mechanism ===")
        inputs = ["110", "13800138000", "没有了"]
        adapter = self.run_engine('customer_server.bot', 'custBot', inputs)

        output = adapter.get_all_output()
        self.assertIn("未查询到号码", output)
        self.assertIn("身份验证通过", output)
        self.assertIn("尊贵的 5G畅享套餐 用户", output)

    def test_8(self):
        print("\n=== Test 8: Noise Input & Fallback Logic ===")
        inputs = ["13800138000", "我想吃火锅", "查话费", "没有了"]
        adapter = self.run_engine('customer_server.bot', 'custBot', inputs)

        output = adapter.get_all_output()
        self.assertIn("抱歉，我没听懂", output)
        self.assertIn("账户余额", output)

    def test_9(self):
        print("\n=== Test 9: Context Isolation ===")
        inputs_a = ["13900139000", "办理流量包", "拒绝", "没有了"]
        adapter_a = self.run_engine('customer_server.bot', 'custBot', inputs_a)

        inputs_b = ["13800138000", "办理流量包", "没有了"]
        adapter_b = self.run_engine('customer_server.bot', 'custBot', inputs_b)

        output_a = adapter_a.get_all_output()
        output_b = adapter_b.get_all_output()

        self.assertIn("余额不足", output_a)
        self.assertIn("办理成功", output_b)

        self.assertNotIn("1200.50", output_a)
        self.assertNotIn("测试1", output_a)


if __name__ == '__main__':
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        sys.stdout = f
        runner = unittest.TextTestRunner(stream=f, verbosity=2)
        suite = unittest.TestLoader().loadTestsFromTestCase(TestEnterpriseScenario)
        runner.run(suite)