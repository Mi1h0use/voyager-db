from flask import Flask, render_template, jsonify, request, redirect, url_for, make_response, g
from functools import wraps
from database import get_reader_connection, get_writer_connection
from pprint import pprint
from helpers import *
from airport import airport_bp
from station import station_bp

app = Flask(__name__)

# Register blueprints
app.register_blueprint(airport_bp)
app.register_blueprint(station_bp)


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
@requires_permission('EDIT_STATIONS')
def accept_station():
    icao = request.form.get('icao')
    callsign = request.form.get('callsign_normal')
    
    # Get the redirect parameters with default empty strings
    continent = request.form.get('continent') or ""
    country = request.form.get('country') or ""
    last_updated = request.form.get('last_updated') or ""
    
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
    return redirect(url_for('verify', continent=continent, country=country, last_updated=last_updated))

@app.route('/edit_station', methods=['POST'])
@requires_auth
@requires_permission('EDIT_STATIONS')
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
    return redirect(url_for('verify', continent=continent, country=country, last_updated=last_updated, offset=offset))

@app.route('/verify')
@requires_auth
@requires_permission('EDIT_STATIONS')
def verify():
    continent = request.args.get('continent')
    country = request.args.get('country')
    last_updated = request.args.get('last_updated')
    
    with get_reader_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        # Build the query dynamically based on filters
        query = """
            SELECT s.*, a.name as airport_name, a.city, a.iso_country, a.latitude, a.longitude
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
            query += " AND DATE(s.last_updated) = %s"
            params.append(last_updated)
            
        # Add ORDER BY RAND() to get a random station
        query += " ORDER BY RAND() LIMIT 1"
            
        cursor.execute(query, params)
        stations = cursor.fetchall()
        
        if not stations:
            return render_template('verify.html', has_stations=False)
            
        station = stations[0]  # Get the single random station
        skyvector_url = get_skyvector_url(conn, station['icao'])
        user_contributions = get_user_contributions(conn, g.user_id)
        station_name = get_callsign_name(conn, station['callsign_normal'])
        return render_template('verify.html', station=station, has_stations=True,
                             continent=continent, country=country, last_updated=last_updated, skyvector_url=skyvector_url, user_contributions=user_contributions, station_name=station_name)

if __name__ == '__main__':
    app.run(debug=True)
