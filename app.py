from flask import Flask, render_template, jsonify, request, redirect, url_for, make_response, g
from functools import wraps
from database import get_reader_connection, get_writer_connection
from pprint import pprint
import bcrypt
import json

app = Flask(__name__)

def check_auth(username, password):
    with get_reader_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM users WHERE username = %s",
            (username,)
        )
        user = cursor.fetchone()
        if user is None:
            return False
        
        # Convert password to bytes and compare with stored hash
        if bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            return user
        return False

def authenticate():
    response = make_response('Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401)
    response.headers['WWW-Authenticate'] = 'Basic realm="Login Required"'
    return response

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def get_station_json(cursor, station_id):
    cursor.execute("""
        SELECT id, callsign_normal, name, authoritative, type, source
        FROM stations
        WHERE id = %s
    """, (station_id,))
    row = cursor.fetchone()
    return row

def log_station_change(conn, station_id, old_val, new_val, user_id):
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO station_logs (user_id, station_id, old_val, new_val) VALUES (%s, %s, %s, %s)",
        (user_id, station_id, json.dumps(old_val), json.dumps(new_val))
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth:
            return authenticate()
            
        user = check_auth(auth.username, auth.password)
        if not user:
            return authenticate()
            
        # Store user info in Flask's g object
        g.username = auth.username
        g.user_id = user['id']
        return f(*args, **kwargs)
    return decorated
@app.route('/')
@requires_auth
def index():
    return render_template('index.html')

@app.route('/countries/<continent>')
@requires_auth
def get_countries(continent):
    with get_reader_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT `code`, `name` FROM countries WHERE continent = %s", (continent,))
        countries = cursor.fetchall()
    return jsonify(countries)

@app.route('/accept_station', methods=['POST'])
@requires_auth
def accept_station():
    icao = request.form.get('icao')
    callsign = request.form.get('callsign_normal')
    
    # Get the redirect parameters with default empty strings
    continent = request.form.get('continent') or ""
    country = request.form.get('country') or ""
    last_updated = request.form.get('last_updated') or ""
    offset = int(request.form.get('offset', 0))
    
    with get_writer_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        
        # Get the station ID and current state
        cursor.execute(
            "SELECT id FROM stations WHERE icao = %s AND callsign_normal = %s AND source = 'AI'",
            (icao, callsign)
        )
        result = cursor.fetchone()
        if not result:
            return jsonify({'message': 'Station not found or already processed'}), 400
            
        station_id = result['id']
        old_val = get_station_json(cursor, station_id)
        
        # Perform the update
        cursor.execute(
            "UPDATE stations SET source = 'HUMAN' WHERE id = %s",
            (station_id,)
        )
        
        # Get new state and log the change
        new_val = get_station_json(cursor, station_id)
        log_station_change(conn, station_id, old_val, new_val, g.user_id)
        
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'message': 'Station already has source HUMAN', 'error': str(cursor.statement)}), 400


    
    # Redirect to the next station
    return redirect(url_for('verify', continent=continent, country=country, 
                          last_updated=last_updated, offset=offset))

@app.route('/edit_station', methods=['POST'])
@requires_auth
def edit_station():
    icao = request.form.get('icao')
    callsign = request.form.get('callsign')
    action = request.form.get('action')
    
    # Get the redirect parameters with default empty strings
    continent = request.form.get('continent') or ""
    country = request.form.get('country') or ""
    last_updated = request.form.get('last_updated') or ""
    offset = int(request.form.get('offset', 0))
    
    with get_writer_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        
        # Get the station ID and current state
        cursor.execute(
            "SELECT id FROM stations WHERE icao = %s AND callsign = %s AND source = 'AI'",
            (icao, callsign)
        )
        result = cursor.fetchone()
        if not result:
            return jsonify({'message': 'Station not found or already processed'}), 400
            
        station_id = result['id']
        old_val = get_station_json(cursor, station_id)
        
        if action == 'save':
            cursor.execute(
                """UPDATE stations 
                   SET callsign_normal = %s, name = %s, source = 'HUMAN'
                   WHERE id = %s""",
                (request.form.get('callsign_normal'), request.form.get('name'), station_id)
            )
        elif action == 'delete':
            cursor.execute(
                """UPDATE stations 
                   SET callsign_normal = NULL, name = NULL, source = 'HUMAN'
                   WHERE id = %s""",
                (station_id,)
            )
        
        # Get new state and log the change
        new_val = get_station_json(cursor, station_id)
        log_station_change(conn, station_id, old_val, new_val, g.user_id)
        
        conn.commit()
    
    # Redirect to the next station
    return redirect(url_for('verify', continent=continent, country=country, 
                          last_updated=last_updated, offset=offset))

@app.route('/verify')
@requires_auth
def verify():
    continent = request.args.get('continent')
    country = request.args.get('country')
    last_updated = request.args.get('last_updated')
    offset = int(request.args.get('offset', 0))
    
    with get_reader_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        
        # Build the query dynamically based on filters
        query = """
            SELECT s.*, a.name as airport_name, a.city, a.country, a.latitude, a.longitude
            FROM stations s
            JOIN airports a ON s.icao = a.icao
            WHERE s.source = 'AI'
        """
        params = []
        
        if continent:
            query += " AND a.continent = %s"
            params.append(continent)
            
        if country:
            query += " AND a.iso_country = %s"
            params.append(country)
            
        if last_updated:
            query += " AND s.last_updated >= %s"
            params.append(last_updated)
            
        query += " ORDER BY RAND()"
        
        cursor.execute(query, params)
        stations = cursor.fetchall()
        
        
        if not stations or offset >= len(stations):
            return render_template('verify.html', has_stations=False)
            
        return render_template('verify.html', has_stations=True, station=stations[offset], 
                             total_stations=len(stations), current_index=offset,
                             continent=continent, country=country, last_updated=last_updated)

if __name__ == '__main__':
    app.run(debug=True)
