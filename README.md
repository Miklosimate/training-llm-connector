# Garmin Light

A small Flask/WSGI application that:

1. logs in to Garmin Connect, including MFA;
2. fetches activities for one selected date;
3. fetches all available details for one activity;
4. returns a GPT-ready ZIP directly to the browser.

It does not use SQLite, save activities, cache ZIP files, or persist Garmin tokens. Login and MFA
objects exist only in the Python process memory and expire after one hour by default.

This uses the unofficial `garminconnect` package and private Garmin endpoints. Keep the app private.

## Requirements

- Python 3.12 or newer (`garminconnect 0.3.6` requires it)
- HTTPS
- one WSGI application process
- outbound HTTPS access to Garmin

## Local run

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export GARMIN_LIGHT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export GARMIN_LIGHT_SECURE_COOKIE=0
flask --app app run
```

Open <http://127.0.0.1:5000>.

## cPanel / Passenger deployment

The application is WSGI-compatible through `passenger_wsgi.py`. In cPanel's **Setup Python App**
or **Application Manager**:

1. Select Python 3.12 or newer.
2. Set the application root to the uploaded `garmin-light` directory.
3. Set the startup file to `passenger_wsgi.py`.
4. Set the application entry point to `application`.
5. Install `requirements.txt` in the application's virtual environment.
6. Add these environment variables:

   - `GARMIN_LIGHT_SECRET_KEY`: at least 32 random bytes represented as hex or base64
   - `GARMIN_LIGHT_SECURE_COOKIE=1`
   - `GARMIN_LIGHT_SESSION_TTL=3600`
   - `GARMIN_LIGHT_MAX_SESSIONS=8`

7. Configure Passenger for one application process. If the hosting control panel cannot guarantee
   one process, MFA or an active login may randomly disappear because the next request can reach a
   different process.
8. Restart the application.

No application data directory is required.

## Security and operational limits

- Put the app behind cPanel password protection or another access-control layer.
- Use HTTPS only. Garmin credentials are submitted through this page.
- The Flask cookie contains only a signed random session ID and CSRF token. Garmin credentials,
  OAuth state, activities, and generated ZIPs are not placed in the cookie.
- A Passenger restart, process recycle, or one-hour inactivity timeout logs the user out.
- Downloads are generated in memory and returned immediately. Large activities can temporarily use
  significant RAM.
- The server must permit outbound requests to Garmin Connect. Some shared hosts block or rate-limit
  these requests.

