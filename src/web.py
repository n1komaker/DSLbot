import queue

class WebAdapter:
    def __init__(self):
        self.input_queue = queue.Queue()
        self.output_queue = queue.Queue()

    def send(self, text):
        self.output_queue.put({"type": "bot", "content": text})

    def receive(self):
        self.output_queue.put({"type": "system", "action": "wait_input"})
        return self.input_queue.get()

    def push_user_input(self, text):
        self.input_queue.put(text)

    def get_pending_messages(self):
        messages = []
        while not self.output_queue.empty():
            messages.append(self.output_queue.get())
        return messages