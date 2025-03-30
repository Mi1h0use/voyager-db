# Voyager Data Project

A Flask-based web application with database connectivity.

## Setup

1. Ensure you have Python 3.8+ installed
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Make sure your `.env` file contains the following variables:
   - DB_HOST
   - DB_USER
   - DB_USER_RO
   - DB_PASSWORD
   - DB_NAME

## Running the Application

Run the application in debug mode using:
```
python -m flask run app -p 8000 --debug 
```
Deploy with docker-compose or a WSGI.

The application will be available at http://localhost:8000
