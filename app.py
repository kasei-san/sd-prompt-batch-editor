import os
from dotenv import load_dotenv
from flask import Flask, render_template

load_dotenv()

app = Flask(__name__)

APP_PORT = int(os.getenv('APP_PORT', '4644'))


@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=APP_PORT, debug=False)
