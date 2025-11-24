from lark import Lark
from src.interpreter import BotInterpreter, RuntimeEngine
from src.llm_agent.mock_llm import MockLLMService


def main():
    # 1. 加载文件
    grammar_file = 'src/dsl_parser/grammar.lark'
    script_file = 'examples/refund.bot'  # <--- 注意改成新的脚本

    try:
        with open(grammar_file, 'r', encoding='utf-8') as f:
            grammar = f.read()
        with open(script_file, 'r', encoding='utf-8') as f:
            script = f.read()
    except FileNotFoundError as e:
        print(f"文件未找到: {e}")
        return

    # 2. 编译阶段 (Parsing & Transformation)
    print(">>> 正在编译 DSL...")
    parser = Lark(grammar, parser='lalr')
    interpreter = BotInterpreter()  # 这是编译器

    try:
        ast = parser.parse(script)
        interpreter.transform(ast)  # 这会将解析结果存入 interpreter.flows
    except Exception as e:
        print(f"语法错误: {e}")
        return

    # 3. 准备运行时环境
    print(">>> 初始化运行时引擎...")
    engine = RuntimeEngine(interpreter.flows)

    # 注入 Mock LLM (关键步骤!)
    mock_llm = MockLLMService()
    engine.set_llm_service(mock_llm)

    # 4. 运行
    print(">>> 启动机器人...")
    # 注意：脚本里的 bot 名字叫 RefundBot
    engine.run("RefundBot")


if __name__ == "__main__":
    main()