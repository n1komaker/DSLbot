import os
from lark import Lark
from src.interpreter import BotInterpreter, RuntimeEngine
from src.llm_client import LLMService
from src.db_manager import DBManager

def main():
    grammar_file = 'src/dsl_parser/grammar.lark'
    script_file = 'examples/refund.bot'

    db = DBManager('bot_data.db')

    if not os.path.exists(grammar_file) or not os.path.exists(script_file):
        print("Files not found.")
        return

    with open(grammar_file, 'r', encoding='utf-8') as f:
        grammar = f.read()
    with open(script_file, 'r', encoding='utf-8') as f:
        script = f.read()

    parser = Lark(grammar, parser='lalr')
    interpreter = BotInterpreter()

    try:
        ast = parser.parse(script)
        interpreter.transform(ast)
    except Exception as e:
        print(f"Syntax Error: {e}")
        return

    engine = RuntimeEngine(interpreter.flows, db_manager=db)

    llm = LLMService()
    if llm.client:
        engine.set_llm_service(llm)

    engine.run("SqlBot")
    db.close()


if __name__ == "__main__":
    main()