from flask import Flask, render_template, jsonify, request
from database import get_reader_connection, get_writer_connection

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/countries/<continent>')
def get_countries(continent):
    with get_reader_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT `code`, `name` FROM countries WHERE continent = %s", (continent,))
        countries = cursor.fetchall()
    return jsonify(countries)

@app.route('/verify')
def verify():
    continent = request.args.get('continent')
    country = request.args.get('country')
    last_updated = request.args.get('last_updated')
    
    return jsonify({
        'continent': continent,
        'country': country,
        'last_updated': last_updated
    })

if __name__ == '__main__':
    app.run(debug=True)
