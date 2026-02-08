import os
import subprocess
import uuid
import json
import base64
import threading
import traceback
from io import BytesIO
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, Response
from PIL import Image, PngImagePlugin

from metadata_parser import extract_metadata
from prompt_editor import apply_edits
from forge_client import ForgeClient

load_dotenv()

app = Flask(__name__)

APP_PORT = int(os.getenv('APP_PORT', '4644'))
OUTPUT_DIR = os.getenv('OUTPUT_DIR', './output')

# In-memory storage for uploaded images and generation sessions
uploaded_images = {}  # id -> { filename, filepath, metadata }
generation_sessions = {}  # session_id -> { events: [], done: bool }


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/version')
def version():
    """Return file timestamps for debugging."""
    files = ['app.py', 'metadata_parser.py', 'prompt_editor.py', 'forge_client.py']
    info = {}
    for f in files:
        p = os.path.join(os.path.dirname(__file__), f)
        if os.path.exists(p):
            info[f] = datetime.fromtimestamp(os.path.getmtime(p)).strftime('%Y-%m-%d %H:%M:%S')
    return jsonify(info)


@app.route('/api/upload', methods=['POST'])
def upload():
    """Upload a PNG file, extract metadata, return thumbnail + metadata."""
    if 'file' not in request.files:
        return jsonify({'error': 'ファイルがありません'}), 400

    file = request.files['file']
    if not file.filename.lower().endswith('.png'):
        return jsonify({'error': 'PNGファイルのみ対応しています'}), 400

    # Save to temp location
    img_id = str(uuid.uuid4())
    temp_dir = os.path.join(OUTPUT_DIR, '.tmp')
    os.makedirs(temp_dir, exist_ok=True)
    filepath = os.path.join(temp_dir, f'{img_id}.png')
    file.save(filepath)

    # Extract metadata
    metadata = extract_metadata(filepath)
    if metadata is None:
        os.remove(filepath)
        return jsonify({'error': 'SDメタデータが見つかりません (Forge/A1111形式のPNGのみ対応)'}), 400

    # Generate thumbnail (data URL)
    with Image.open(filepath) as img:
        img.thumbnail((200, 200))
        buf = BytesIO()
        img.save(buf, format='PNG')
        thumbnail = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()

    uploaded_images[img_id] = {
        'filename': file.filename,
        'filepath': filepath,
        'metadata': metadata,
    }

    return jsonify({
        'id': img_id,
        'filename': file.filename,
        'thumbnail': thumbnail,
        'metadata': metadata,
    })


@app.route('/api/check-forge')
def check_forge():
    """Check Forge API connection."""
    host = request.args.get('host', '127.0.0.1')
    port = request.args.get('port', '7860')
    client = ForgeClient(host, port)
    connected = client.check_connection()
    return jsonify({'connected': connected})


@app.route('/api/generate', methods=['POST'])
def generate():
    """Start batch generation."""
    data = request.get_json()
    if not data or 'images' not in data:
        return jsonify({'error': 'リクエストデータが不正です'}), 400

    images = data['images']
    edits = data.get('edits', {})
    host = data.get('host', '127.0.0.1')
    port = data.get('port', '7860')

    if not images:
        return jsonify({'error': '画像がありません'}), 400

    session_id = str(uuid.uuid4())
    generation_sessions[session_id] = {
        'events': [],
        'done': False,
    }

    # Start generation in background thread
    thread = threading.Thread(
        target=_generation_worker,
        args=(session_id, images, edits, host, port),
        daemon=True,
    )
    thread.start()

    return jsonify({'session_id': session_id})


def _generation_worker(session_id, images, edits, host, port):
    """Background worker for batch image generation."""
    session = generation_sessions[session_id]
    client = ForgeClient(host, port)

    # Prepare output directory path (created on first successful generation)
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    out_dir = os.path.join(OUTPUT_DIR, timestamp)
    out_dir_created = False

    # Group by model to minimize model switches
    model_groups = {}
    for img_data in images:
        model_key = img_data['metadata'].get('Model', '') + '|' + img_data['metadata'].get('Model hash', '')
        if model_key not in model_groups:
            model_groups[model_key] = []
        model_groups[model_key].append(img_data)

    # Flatten back to ordered list (grouped by model)
    ordered = []
    for group in model_groups.values():
        ordered.extend(group)

    total = len(ordered)
    success = 0
    failed = 0
    generated_files = []

    for i, img_data in enumerate(ordered):
        filename = img_data['filename']
        metadata = dict(img_data['metadata'])

        # Send progress event
        _add_event(session, 'progress', {
            'current': i + 1,
            'total': total,
            'filename': filename,
        })

        try:
            # Apply edits to prompts
            metadata['positive_prompt'] = apply_edits(
                metadata.get('positive_prompt', ''),
                edits.get('remove_positive', ''),
                edits.get('add_positive', ''),
            )
            metadata['negative_prompt'] = apply_edits(
                metadata.get('negative_prompt', ''),
                edits.get('remove_negative', ''),
                edits.get('add_negative', ''),
            )

            # Build payload and generate
            payload = client.build_payload(metadata)
            print(f"\n=== Payload for {filename} ===")
            print(json.dumps({k: v for k, v in payload.items() if k != 'infotext'}, ensure_ascii=False, indent=2))
            print(f"infotext:\n{payload.get('infotext', '(none)')}")
            print("=" * 40)
            result = client.txt2img(payload)

            # Save image
            if result.get('images'):
                img_b64 = result['images'][0]
                img_bytes = base64.b64decode(img_b64)

                if not out_dir_created:
                    os.makedirs(out_dir, exist_ok=True)
                    out_dir_created = True
                out_path = os.path.join(out_dir, filename)
                _save_image_with_metadata(img_bytes, out_path, result.get('info'))

                success += 1
                generated_files.append(filename)
                # Send payload info (without infotext raw text for brevity)
                payload_info = {k: v for k, v in payload.items() if k not in ('infotext', 'send_images', 'save_images', 'override_settings_restore_afterwards')}
                _add_event(session, 'image_done', {'filename': filename, 'payload': payload_info})
            else:
                failed += 1
                _add_event(session, 'error_event', {
                    'filename': filename,
                    'message': '画像データが返却されませんでした',
                })

        except Exception as e:
            failed += 1
            tb = traceback.format_exc()
            print(f"\n!!! Error for {filename} !!!")
            print(tb)
            _add_event(session, 'error_event', {
                'filename': filename,
                'message': str(e),
            })
            # Stop on first error
            break

    # Complete
    _add_event(session, 'complete', {
        'output_dir': os.path.abspath(out_dir),
        'output_subdir': os.path.basename(out_dir),
        'total': total,
        'success': success,
        'failed': failed,
        'files': generated_files,
    })
    session['done'] = True


def _save_image_with_metadata(img_bytes: bytes, out_path: str, info_json: str | None):
    """Save image bytes as PNG, preserving or restoring metadata."""
    img = Image.open(BytesIO(img_bytes))

    # Check if image already has parameters metadata
    existing_params = img.info.get('parameters')
    if existing_params:
        # Already has metadata, save as-is
        png_info = PngImagePlugin.PngInfo()
        png_info.add_text('parameters', existing_params)
        img.save(out_path, pnginfo=png_info)
        return

    # Try to restore from API response info
    if info_json:
        try:
            if isinstance(info_json, str):
                info = json.loads(info_json)
            else:
                info = info_json
            infotxt = info.get('infotexts', [None])[0]
            if infotxt:
                png_info = PngImagePlugin.PngInfo()
                png_info.add_text('parameters', infotxt)
                img.save(out_path, pnginfo=png_info)
                return
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            pass

    # Fallback: save without metadata
    img.save(out_path)


def _add_event(session, event_type, data):
    """Add an SSE event to the session queue."""
    session['events'].append({
        'event': event_type,
        'data': data,
    })


@app.route('/api/generate/progress')
def generate_progress():
    """SSE endpoint for generation progress."""
    session_id = request.args.get('session_id')
    if not session_id or session_id not in generation_sessions:
        return jsonify({'error': 'セッションが見つかりません'}), 404

    def event_stream():
        session = generation_sessions[session_id]
        sent = 0

        while True:
            # Send any new events
            while sent < len(session['events']):
                evt = session['events'][sent]
                yield f"event: {evt['event']}\ndata: {json.dumps(evt['data'], ensure_ascii=False)}\n\n"
                sent += 1

            if session['done'] and sent >= len(session['events']):
                # Clean up session after a delay
                break

            # Polling interval
            import time
            time.sleep(0.3)

        # Clean up
        if session_id in generation_sessions:
            del generation_sessions[session_id]

    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )


@app.route('/api/open-folder', methods=['POST'])
def open_folder():
    """Open a folder in Windows Explorer."""
    data = request.get_json()
    folder = data.get('path', '')
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        return jsonify({'error': 'ディレクトリが存在しません'}), 404
    subprocess.Popen(['explorer', folder])
    return jsonify({'ok': True})


@app.route('/api/output/<subdir>/<path:filename>')
def serve_output(subdir, filename):
    """Serve a generated image from the output directory."""
    from flask import send_from_directory
    directory = os.path.join(os.path.abspath(OUTPUT_DIR), subdir)
    return send_from_directory(directory, filename, mimetype='image/png')


if __name__ == '__main__':
    # Show file timestamps at startup for debugging
    _files = ['app.py', 'metadata_parser.py', 'prompt_editor.py', 'forge_client.py']
    print("=== SD Prompt Batch Editor ===")
    for _f in _files:
        _p = os.path.join(os.path.dirname(__file__), _f)
        if os.path.exists(_p):
            _mt = datetime.fromtimestamp(os.path.getmtime(_p)).strftime('%Y-%m-%d %H:%M:%S')
            print(f"  {_f}: {_mt}")
    print(f"  Port: {APP_PORT}")
    print("=" * 30)
    app.run(host='0.0.0.0', port=APP_PORT, debug=False)
