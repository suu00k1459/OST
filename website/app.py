import os
import re
import csv
import math
from datetime import datetime
from flask import Flask, render_template, request, abort, url_for


def get_processed_dir():
    # data/processed relative to the repository root (go up from website/ -> root -> data/processed)
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    return os.path.join(base, 'data', 'processed')


def get_file_stats(filepath):
    """Get stats for a CSV file: row count, column count, file size, last modified."""
    stats = {
        'rows': 0,
        'cols': 0,
        'size_kb': 0,
        'modified': 'Unknown'
    }
    
    try:
        # File size
        size_bytes = os.path.getsize(filepath)
        stats['size_kb'] = round(size_bytes / 1024, 2)
        
        # Last modified
        mtime = os.path.getmtime(filepath)
        stats['modified'] = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
        
        # Row and column counts
        with open(filepath, 'r', newline='', encoding='utf-8') as fh:
            reader = csv.reader(fh)
            try:
                header = next(reader)
                stats['cols'] = len(header)
                stats['rows'] = sum(1 for _ in reader) + 1  # +1 for header
            except StopIteration:
                pass
    except Exception:
        pass
    
    return stats


def list_device_files():
    processed = get_processed_dir()
    if not os.path.isdir(processed):
        return []
    files = [f for f in os.listdir(processed) if f.lower().endswith('.csv')]

    def keyfn(name):
        # Return a consistent tuple key so sorting never compares int and str directly.
        # If the filename contains a number, sort by (0, number, name) so numeric files
        # come first in numeric order; otherwise sort by (1, lowercased name).
        m = re.search(r"(\d+)", name)
        if m:
            try:
                num = int(m.group(1))
                return (0, num, name.lower())
            except ValueError:
                pass
        return (1, name.lower())

    return sorted(files, key=keyfn)


# Templates and static folders are in the same directory as this file
TEMPLATES = os.path.join(os.path.dirname(__file__), 'templates')
STATIC = os.path.join(os.path.dirname(__file__), 'static')

app = Flask(__name__, template_folder=TEMPLATES, static_folder=STATIC)


@app.route('/')
def index():
    files = list_device_files()
    if not files:
        # no processed data yet
        return render_template('index.html', devices=[], no_data=True, total=0)

    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1
    try:
        per_page = int(request.args.get('per_page', 12))
    except ValueError:
        per_page = 12

    per_page = max(1, min(200, per_page))
    total = len(files)
    total_pages = math.ceil(total / per_page)
    page = max(1, min(page, total_pages))

    start = (page - 1) * per_page
    end = start + per_page
    page_files = files[start:end]

    processed = get_processed_dir()
    devices = []
    for fname in page_files:
        fpath = os.path.join(processed, fname)
        stats = get_file_stats(fpath)
        devices.append({
            'name': fname,
            'preview_url': url_for('device', filename=fname),
            'stats': stats
        })

    return render_template('index.html', devices=devices, page=page, per_page=per_page, total=total, total_pages=total_pages, no_data=False)


@app.route('/device/<path:filename>')
def device(filename):
    # Only allow base filename
    filename = os.path.basename(filename)
    files = list_device_files()
    if filename not in files:
        abort(404, f"Device file not found: {filename}")

    processed = get_processed_dir()
    path = os.path.join(processed, filename)

    # Get stats
    stats = get_file_stats(path)
    
    # Read CSV header + a few rows for preview
    preview_rows = []
    header = []
    try:
        with open(path, 'r', newline='', encoding='utf-8') as fh:
            reader = csv.reader(fh)
            try:
                header = next(reader)
            except StopIteration:
                header = []
            for i, row in enumerate(reader):
                if i >= 100:
                    break
                preview_rows.append(row)
    except Exception as e:
        abort(500, f"Failed to read file: {e}")

    return render_template('device.html', filename=filename, header=header, rows=preview_rows, stats=stats)


if __name__ == '__main__':
    # Run on 0.0.0.0 so it's reachable from other machines if needed; debug True for development
    app.run(host='0.0.0.0', port=8080, debug=True)
