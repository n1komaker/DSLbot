import threading
import uuid
import os
import glob
from flask import Flask, render_template, request, jsonify, session
from lark import Lark
from src.interpreter import BotInterpreter, RuntimeEngine
from src.web import WebAdapter
from src.llm_client import LLMService
from src.db_manager import DBManager

app = Flask(__name__)
app.secret_key = "dsl_key"

active_sessions = {}
DB_PATH = 'bot_data.db'
SCRIPTS_DIR = 'examples'
current_flows = {}
current_script_name = ""


def get_db():
    return DBManager(DB_PATH)

def get_available_scripts():
    files = glob.glob(os.path.join(SCRIPTS_DIR, "*.bot"))
    return [os.path.basename(f) for f in files]


def load_dsl(filename):
    global current_flows, current_script_name
    grammar_file = 'src/dsl_parser/grammar.lark'
    script_path = os.path.join(SCRIPTS_DIR, filename)

    if not os.path.exists(script_path):
        raise FileNotFoundError(f"Script {filename} not found")

    with open(grammar_file, 'r', encoding='utf-8') as f: grammar = f.read()
    with open(script_path, 'r', encoding='utf-8') as f: script = f.read()

    parser = Lark(grammar, parser='lalr')
    interpreter = BotInterpreter()
    ast = parser.parse(script)
    interpreter.transform(ast)

    current_flows = interpreter.flows
    current_script_name = filename
    return current_flows


try:
    scripts = get_available_scripts()
    if scripts:
        load_dsl(scripts[0])
    else:
        print("Warning: No .bot scripts found in examples/")
except Exception as e:
    print(f"Startup Error: {e}")


def run_bot_thread(adapter, flows, bot_name):
    db = get_db()
    engine = RuntimeEngine(flows, db_manager=db, io_adapter=adapter)

    try:
        llm = LLMService()
        engine.set_llm_service(llm)
        engine.run(bot_name)
    except Exception as e:
        print(f"Error: {e}")
        adapter.send(f"System Error: {e}")
    finally:
        db.close()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/scripts', methods=['GET'])
def list_scripts():
    return jsonify({
        "scripts": get_available_scripts(),
        "current": current_script_name
    })


@app.route('/api/switch_script', methods=['POST'])
def switch_script():
    filename = request.json.get('filename')
    try:
        load_dsl(filename)
        active_sessions.clear()
        session.clear()
        return jsonify({"status": "ok", "current": filename})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/start_chat', methods=['POST'])
def start_chat():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())

    uid = session['user_id']

    if uid in active_sessions:
        del active_sessions[uid]

    adapter = WebAdapter()
    active_sessions[uid] = adapter

    bot_names = list(current_flows.keys())
    if not bot_names:
        return jsonify({"error": "No bot defined in script"}), 400

    target_bot = bot_names[0]

    t = threading.Thread(target=run_bot_thread, args=(adapter, current_flows, target_bot))
    t.daemon = True
    t.start()

    return jsonify({"status": "ok", "bot_name": target_bot})


@app.route('/send', methods=['POST'])
def send_msg():
    uid = session.get('user_id')
    if not uid or uid not in active_sessions:
        return jsonify({"error": "Session expired"}), 400
    msg = request.json.get('message')
    active_sessions[uid].push_user_input(msg)
    return jsonify({"status": "ok"})


@app.route('/poll')
def poll_msg():
    uid = session.get('user_id')
    if uid and uid not in active_sessions:
        return jsonify([{"type": "system", "action": "reload"}])
    if not uid or uid not in active_sessions:
        return jsonify([])
    msgs = active_sessions[uid].get_pending_messages()
    return jsonify(msgs)


@app.route('/reset', methods=['POST'])
def reset():
    uid = session.get('user_id')
    if uid in active_sessions:
        del active_sessions[uid]
    session.clear()
    return jsonify({"status": "ok"})


if __name__ == '__main__':
    app.run(debug=True, port=5000)