# Garmin Light

Garmin Light is a small Flask application for exporting Garmin activities and reviewing
GPT-generated structured workouts before uploading them to Garmin.

## Deployment link

The production application is deployed at:

<https://training.miklosifoto.hu>

Use this HTTPS address to log in to Garmin, export an activity ZIP, download the GPT workout prompt,
and review or upload a generated `plan.json`.

The application:

1. logs in to Garmin Connect and supports Garmin MFA;
2. fetches activities from a selected date;
3. fetches all available details for the selected activity;
4. creates the ZIP in memory and sends it directly to the browser;
5. downloads a GPT prompt containing the accepted workout JSON structure;
6. validates and previews a returned `plan.json`;
7. uploads and optionally schedules each explicitly approved workout.

It does not use SQLite, save activities, cache ZIP files, or persist Garmin authentication tokens.
Login state and the reviewed workout queue exist only in the running Python process. Restarting or
recycling the application logs the user out and clears the queue.

The Flask cookie-signing secret is created automatically in `.garmin-light-secret` on first start.
This is application configuration only; it contains no Garmin credentials or workout data.

> Garmin Light uses the community-maintained `garminconnect` package and unofficial Garmin Connect
> endpoints. Garmin may change or rate-limit these endpoints. Keep this application private.

## ZIP contents

Depending on which data Garmin provides for the activity, the downloaded ZIP contains:

- `analysis_prompt_and_report.md`
- `full_workout.json`
- `metrics.csv`
- SVG charts for available heart-rate, speed, cadence, elevation, and power data
- `original_fit.zip`, containing Garmin's original FIT download

## Workout upload workflow

1. Download `garmin_light_workout_prompt.md` from the application.
2. Give that file to GPT along with your training context.
3. Save GPT's JSON-only response as `plan.json`.
4. Upload `plan.json` to Garmin Light.
5. Resolve any validation errors.
6. Inspect the complete normalized workout.
7. Check the explicit approval box.
8. Choose whether to schedule it on its planned date.
9. Upload the approved workout to Garmin.

Validation never changes Garmin. Workouts are uploaded one at a time only after approval.

The light schema supports:

- running, cycling, and swimming;
- warmup, main, interval, recovery, rest, cooldown, and other steps;
- time, distance, and lap-button end conditions;
- heart-rate, power, cadence, and pace targets;
- zone or minimum/maximum targets;
- repeat groups.

The downloadable Markdown prompt is the authoritative schema guide and includes a complete valid
example.

## Requirements

- Python 3.11 or newer
- outbound HTTPS access to Garmin Connect
- HTTPS when deployed
- a WSGI application host such as cPanel Passenger

Garmin Light pins `garminconnect 0.3.2`, which supports Python 3.10+, but Python 3.11 or newer is
recommended for deployment.

## Run locally

Open a terminal in the `garmin-light` directory.

### macOS or Linux

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
export GARMIN_LIGHT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export GARMIN_LIGHT_SECURE_COOKIE=0
flask --app app run
```

Open <http://127.0.0.1:5000>.

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
$env:GARMIN_LIGHT_SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
$env:GARMIN_LIGHT_SECURE_COOKIE = "0"
flask --app app run
```

Open <http://127.0.0.1:5000>.

`GARMIN_LIGHT_SECURE_COOKIE=0` is only for local HTTP development. Production must use HTTPS and
`GARMIN_LIGHT_SECURE_COOKIE=1`.

## Run tests

After activating the virtual environment:

```bash
python -m pip install pytest ruff
pytest -q
ruff check .
```

## Deploy with cPanel / ugyfeladmin

The deployment works when the hosting account provides cPanel's **Setup Python App** or
**Application Manager**, Python 3.11+, Passenger/WSGI, and outbound HTTPS access.

For the exact no-SSH procedure, see `CPANEL_UPLOAD_ONLY.md`.

### 1. Prepare and upload the files

Upload the contents of this directory to a private application directory in your hosting account,
for example:

```text
/home/CPANEL_USER/garmin-light/
```

The deployed directory must contain at least:

```text
garmin-light/
├── app.py
├── CPANEL_UPLOAD_ONLY.md
├── exporter.py
├── garmin_client.py
├── gpt_prompt.py
├── passenger_wsgi.py
├── requirements.txt
├── workout_plan.py
├── static/
│   └── style.css
└── templates/
    └── index.html
```

Do not put Garmin credentials, a `.env` file, an existing token directory, or the original
dashboard database in the uploaded directory.

You can upload the folder through cPanel **File Manager**, SFTP, Git deployment, or a ZIP archive.
If you upload a ZIP, extract it before creating the Python application.

### 2. Create the Python application

In cPanel or ugyfeladmin:

1. Open **Setup Python App**. Some installations call this **Application Manager**.
2. Click **Create Application**.
3. Select Python **3.11** or newer.
4. Set **Application root** to `garmin-light`.
5. Select `training.miklosifoto.hu` as the application domain.
6. Leave the **Application URL path** blank so the app is served from the domain root.
7. Set **Application startup file** to `passenger_wsgi.py`.
8. Set **Application entry point** to `application`.
9. Create or save the application.

The important WSGI configuration is:

```text
Application URL: training.miklosifoto.hu
URL path:       leave blank
Startup file:   passenger_wsgi.py
Entry point:    application
```

### 3. Install dependencies

If cPanel provides a **Run Pip Install** button, select `requirements.txt` and run it.

If the control panel displays a virtual-environment activation command, copy that command into
cPanel **Terminal**, then install the dependencies. The exact home directory and Python version
will differ:

```bash
source /home/CPANEL_USER/virtualenv/garmin-light/3.11/bin/activate
cd /home/CPANEL_USER/garmin-light
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Installation is successful when both Flask and `garminconnect` install without errors.

If `curl-cffi` cannot be installed, the shared hosting environment is missing a compatible wheel or
required system support. This normally cannot be fixed from an unprivileged cPanel account; ask the
hosting provider or deploy on a VPS/container host.

### 4. Application secret and optional environment variables

No key-generation command is required. If `GARMIN_LIGHT_SECRET_KEY` is not configured, the
application creates this file automatically on first start:

```text
/home/CPANEL_USER/garmin-light/.garmin-light-secret
```

The file is created with owner-only permissions where supported. Keep it in place so browser
sessions remain valid across Passenger restarts.

Environment variables remain optional overrides:

| Variable | Purpose |
| --- | --- |
| `GARMIN_LIGHT_SECRET_KEY` | Overrides the automatically generated file secret. |
| `GARMIN_LIGHT_SECRET_FILE` | Changes the automatic secret-file location. |
| `GARMIN_LIGHT_SECURE_COOKIE` | Defaults to `1`; use `0` only for local HTTP development. |
| `GARMIN_LIGHT_SESSION_TTL` | Inactivity timeout in seconds. Default: `3600`. |
| `GARMIN_LIGHT_MAX_SESSIONS` | Maximum number of in-memory sessions. Default: `64`. |

### 5. Use one application process

Garmin login and MFA state are held in process memory. The same Passenger process must receive the
login, MFA, activity-list, and download requests.

Configure the application for one process if your hosting panel exposes that option. If it does
not, ask the provider whether the Python application can be limited to one Passenger process.

Symptoms of multiple processes include:

- MFA succeeds but the next page asks you to log in again;
- login randomly disappears between requests;
- activity download reports that the Garmin session expired.

The application remains stateless on disk, but process-local state is necessary while one user is
logged in.

### 6. Enable HTTPS and access protection

Before entering Garmin credentials:

1. enable an SSL certificate for the domain or subdomain;
2. confirm the application opens with `https://`;
3. optionally protect the URL using cPanel **Directory Privacy**, HTTP Basic Authentication, a VPN,
   or another access-control layer.

Do not use the application over plain HTTP. Garmin credentials are submitted through its login
form.

### 7. Restart and verify

Use **Restart Application** in cPanel after installing dependencies or changing environment
variables.

Then verify:

1. <https://training.miklosifoto.hu> loads over HTTPS;
2. Garmin login works;
3. MFA works if enabled;
4. selecting a date shows that day's activities;
5. **Download full ZIP** returns a valid ZIP;
6. **Download prompt.md** returns the GPT schema prompt;
7. uploading a valid `plan.json` displays a review queue;
8. an approved workout can be uploaded and scheduled;
9. logging out removes the active in-memory session and workout queue.

No database migration, writable data directory, cron job, or background worker is required.

## Updating the deployment

To deploy a new version:

1. upload and overwrite the application source files;
2. run `python -m pip install -r requirements.txt` if dependencies changed;
3. restart the Python application in cPanel;
4. log in again, because restarting clears Garmin session state.

Do not overwrite the production `GARMIN_LIGHT_SECRET_KEY` when updating.

## Troubleshooting

### The application shows an internal server error

Check the Python application log or cPanel error log. Common causes are:

- Python is older than 3.11;
- dependencies were not installed in the application's virtual environment;
- `passenger_wsgi.py` or the `application` entry point is configured incorrectly;
- the uploaded directory structure is wrong.

Test imports from the application virtual environment:

```bash
cd /home/CPANEL_USER/garmin-light
python -c "from passenger_wsgi import application; print(application)"
```

### Login or MFA disappears

Passenger may be running multiple processes or recycling the process. Configure one application
process. A process restart always logs users out by design.

### Garmin rejects the login

- Confirm the credentials at <https://connect.garmin.com/>.
- Complete any Garmin security prompt.
- Wait before retrying if Garmin rate-limited the server IP.
- Shared-hosting IP addresses can have poor reputation or may be rate-limited by Garmin.

### No activities appear

- Confirm the selected date and the Garmin account.
- Confirm that the activity is already synchronized to Garmin Connect.
- Check whether the server can make outbound HTTPS requests.

### The ZIP download fails for a long activity

ZIPs are generated in memory. A large activity with many samples can exceed the shared host's memory
or request-time limit. Increase the cPanel Python application's memory/time limits if available, or
use a VPS/container host.

### The site keeps returning to the login page

Confirm:

- the site is opened using HTTPS;
- `GARMIN_LIGHT_SECURE_COOKIE=1` is configured;
- the application is not switching between HTTP and HTTPS;
- the browser accepts cookies;
- Passenger is using one process.

## Security and data handling

- Garmin credentials are used for the current login request and are not written to disk.
- Garmin tokens are not persisted.
- Activities and generated ZIPs are not written to disk.
- Uploaded workout JSON and review status are held only in process memory.
- A successful Garmin workout ID is retained in memory before scheduling is attempted, preventing a
  duplicate upload when scheduling is retried during the same process lifetime.
- The browser cookie contains only a signed random session ID and CSRF token.
- Responses use `Cache-Control: no-store`.
- Login state expires after inactivity and is destroyed on logout or process restart.
- The application should remain private and accessible only over HTTPS.
