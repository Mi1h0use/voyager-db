from flask import Blueprint, render_template, redirect, url_for, request
from database import get_reader_connection
from fuzzywuzzy import fuzz, process

station_bp = Blueprint('station', __name__)

@station_bp.route('/station/search')
def search():
    search_term = request.args.get('q', '')
    if not search_term:
        return render_template('error.html', message="No search term provided")

    with get_reader_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        
        # Try exact callsign match first
        cursor.execute("SELECT DISTINCT callsign_normal, name FROM stations WHERE callsign_normal = %s", 
                      (search_term.upper(),))
        exact_match = cursor.fetchone()
        
        if exact_match:
            return redirect(url_for('station.details', callsign=exact_match['callsign_normal']))
        
        # If no exact match, try fuzzy search on name
        cursor.execute("SELECT DISTINCT callsign_normal, name FROM stations")
        all_stations = cursor.fetchall()
        
        # Perform fuzzy matching on station names
        search_results = []
        for station in all_stations:
            if station['name']:  # Only match if name is not None
                score = fuzz.ratio(search_term.lower(), station['name'].lower())
                if score > 60:  # Threshold for fuzzy matching
                    search_results.append({
                        'callsign_normal': station['callsign_normal'],
                        'name': station['name'],
                        'score': score
                    })
        
        search_results.sort(key=lambda x: x['score'], reverse=True)
        
        if len(search_results) == 1:
            return redirect(url_for('station.details', 
                                  callsign=search_results[0]['callsign_normal']))
        elif len(search_results) > 1:
            return render_template('station_search.html', results=search_results)
        else:
            return render_template('error.html', message="No stations found matching your search")

@station_bp.route('/station/<callsign>')
def details(callsign):
    with get_reader_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT DISTINCT callsign_normal, name, source 
            FROM stations 
            WHERE callsign_normal = %s
        """, (callsign.upper(),))
        stations = cursor.fetchall()
        
        if not stations:
            return render_template('error.html', message="Station not found")
            
        return render_template('station_details.html', stations=stations)
