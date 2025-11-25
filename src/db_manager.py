import sqlite3

class DBManager:
    def __init__(self, db_path='bot_data.db'):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()

    def execute(self, sql, params=None):
        try:
            if params:
                self.cursor.execute(sql, params)
            else:
                self.cursor.execute(sql)
            self.conn.commit()
            return self.cursor.rowcount
        except Exception as e:
            print(f"[DB Error] {e}")
            return -1

    def fetch_one(self, sql, params=None):
        try:
            if params:
                self.cursor.execute(sql, params)
            else:
                self.cursor.execute(sql)
            result = self.cursor.fetchone()
            if result:
                return result[0]
            return None
        except Exception as e:
            print(f"[DB Error] {e}")
            return None

    def close(self):
        self.conn.close()