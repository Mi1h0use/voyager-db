from flask import Flask, render_template, jsonify, request, redirect, url_for
from database import get_reader_connection, get_writer_connection
from pprint import pprint

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

@app.route('/accept_station', methods=['POST'])
def accept_station():
    icao = request.form.get('icao')
    callsign = request.form.get('callsign_normal')
    
    # Get the redirect parameters
    continent = request.form.get('continent')
    country = request.form.get('country')
    last_updated = request.form.get('last_updated')
    offset = int(request.form.get('offset', 0))
    
    with get_writer_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE stations SET source = 'HUMAN' WHERE icao = %s AND callsign_normal = %s AND source = 'AI'",
            (icao, callsign)
        )
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'message': 'Station already has source HUMAN', 'error': str(cursor.statement)}), 400

    
    # Redirect to the next station
    return redirect(url_for('verify', continent=continent, country=country, 
                          last_updated=last_updated, offset=offset + 1))

@app.route('/edit_station', methods=['POST'])
def edit_station():
    icao = request.form.get('icao')
    callsign = request.form.get('callsign')
    action = request.form.get('action')
    
    # Get the redirect parameters
    continent = request.form.get('continent')
    country = request.form.get('country')
    last_updated = request.form.get('last_updated')
    offset = int(request.form.get('offset', 0))
    
    with get_writer_connection() as conn:
        cursor = conn.cursor()
        
        if action == 'save':
            # Update the station with new values
            cursor.execute(
                """UPDATE stations 
                   SET callsign_normal = %s, name = %s, source = 'HUMAN'
                   WHERE icao = %s AND callsign = %s AND source = 'AI'""",
                (request.form.get('callsign_normal'), request.form.get('name'), icao, callsign)
            )
        elif action == 'delete':
            # Set callsign_normal and name to NULL, mark as human-verified
            cursor.execute(
                """UPDATE stations 
                   SET callsign_normal = NULL, name = NULL, source = 'HUMAN'
                   WHERE icao = %s AND callsign = %s AND source = 'AI'""",
                (icao, callsign)
            )
        
        conn.commit()
    
    # Redirect to the next station
    return redirect(url_for('verify', continent=continent, country=country, 
                          last_updated=last_updated, offset=offset + 1))

@app.route('/verify')
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
            
        query += " ORDER BY s.callsign_normal"
        
        cursor.execute(query, params)
        stations = cursor.fetchall()
        
        pprint(stations[0])
        
        if not stations or offset >= len(stations):
            return render_template('verify.html', has_stations=False)
            
        return render_template('verify.html', has_stations=True, station=stations[offset], 
                             total_stations=len(stations), current_index=offset,
                             continent=continent, country=country, last_updated=last_updated)

if __name__ == '__main__':
    app.run(debug=True)
