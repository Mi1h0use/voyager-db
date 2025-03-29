from flask import Blueprint, render_template, redirect, url_for, request
from database import get_reader_connection
from fuzzywuzzy import fuzz, process

airport_bp = Blueprint('airport', __name__)

@airport_bp.route('/airport/search')
def search():
    search_term = request.args.get('q', '')
    if not search_term:
        return render_template('error.html', message="No search term provided")

    with get_reader_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        
        # Try exact ICAO match first
        cursor.execute("SELECT icao, name, city FROM airports WHERE icao = %s", (search_term.upper(),))
        exact_match = cursor.fetchone()
        
        if exact_match:
            return redirect(url_for('airport.details', icao=exact_match['icao']))
        
        # If no exact match, try fuzzy search on name and city
        cursor.execute("SELECT DISTINCT icao, name, city FROM airports")
        all_airports = cursor.fetchall()
        
        # Create search strings for fuzzy matching
        search_results = []
        for airport in all_airports:
            name_score = fuzz.ratio(search_term.lower(), airport['name'].lower())
            city_score = fuzz.ratio(search_term.lower(), airport['city'].lower()) if airport['city'] else 0
            max_score = max(name_score, city_score)
            
            if max_score > 60:  # Threshold for fuzzy matching
                search_results.append({
                    'icao': airport['icao'],
                    'name': airport['name'],
                    'city': airport['city'],
                    'score': max_score
                })
        
        search_results.sort(key=lambda x: x['score'], reverse=True)
        
        if len(search_results) == 1:
            return redirect(url_for('airport.details', icao=search_results[0]['icao']))
        elif len(search_results) > 1:
            return render_template('airport_search.html', results=search_results)
        else:
            return render_template('error.html', message="No airports found matching your search")

@airport_bp.route('/airport/<icao>')
def details(icao):
    with get_reader_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT DISTINCT callsign_normal, name, type 
            FROM stations 
            WHERE icao = %s
            ORDER BY type DESC
        """, (icao.upper(),))
        stations = cursor.fetchall()
        
        # Get airport details
        cursor.execute("SELECT name, city FROM airports WHERE icao = %s", (icao.upper(),))
        airport = cursor.fetchone()
        
        if not airport:
            return render_template('error.html', message="Airport not found")
            
        return render_template('airport_details.html',
                             title="Airport Details",
                             airport=airport,
                             stations=stations,
                             icao=icao.upper())
