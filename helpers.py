from flask import request, make_response, g
import bcrypt
import json
from functools import wraps
from database import get_reader_connection
from pprint import pprint

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

def has_permission(conn, user_id, permission):
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM permissions WHERE user_id = %s AND permission = %s", (user_id, permission))
    return cursor.fetchone()[0] > 0

def requires_permission(permission):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not has_permission(get_reader_connection(), g.user_id, permission):
                return jsonify({'message': 'You do not have permission to perform this action'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

def get_skyvector_url(conn, icao):
    cursor = conn.cursor()
    cursor.execute("SELECT url FROM skyvector WHERE icao = %s",(icao,))
    result = cursor.fetchone()
    return ("https://skyvector.com" + result[0]) if result else None

def get_user_contributions(conn, user_id):
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM station_logs WHERE user_id = %s", (user_id,))
    return cursor.fetchone()[0]

def get_callsign_name(conn, callsign):
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT name FROM stations WHERE callsign_normal = %s AND source = 'VATSIM' LIMIT 1", (callsign,))
    result = cursor.fetchone()
    return result[0] if result else None