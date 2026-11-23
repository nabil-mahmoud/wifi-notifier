import os
import json
import io
import datetime
import base64
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
import qrcode
from py_vapid import Vapid
from cryptography.hazmat.primitives import serialization
from pywebpush import webpush, WebPushException

app = Flask(__name__)

BASE_DIR = os.path.dirname(__file__)
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
SUBSCRIPTIONS_FILE = os.path.join(BASE_DIR, 'subscriptions.json')
PRIVATE_KEY_PATH = os.path.join(BASE_DIR, 'private_key.pem')

# 1. Initialize or Load VAPID Keys
def get_vapid_keys():
    v = Vapid()
    if not os.path.exists(PRIVATE_KEY_PATH):
        v.generate_keys()
        v.save_key(PRIVATE_KEY_PATH)
    else:
        v = Vapid.from_file(PRIVATE_KEY_PATH)
        
    pub_bytes = v.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    b64_pub = base64.urlsafe_b64encode(pub_bytes).decode('utf-8').rstrip('=')
    return b64_pub

VAPID_PUBLIC_KEY = get_vapid_keys()

# 2. Config & Subscriptions Storage
DEFAULT_CONFIG = {
    "wifi_ssid": "WE-WiFi",
    "wifi_password": "",
    "public_url": "http://127.0.0.1:5001",
    "history": []
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG

def save_config(cfg):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def load_subscriptions():
    if not os.path.exists(SUBSCRIPTIONS_FILE):
        return []
    try:
        with open(SUBSCRIPTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def save_subscriptions(subs):
    with open(SUBSCRIPTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(subs, f, ensure_ascii=False, indent=2)

# Simplify User Agent for Display
def parse_device(ua_string):
    ua = ua_string.lower()
    if 'android' in ua:
        dev = 'Android Phone'
        if 'samsung' in ua: dev = 'Samsung Phone'
        elif 'xiaomi' in ua or 'redmi' in ua: dev = 'Xiaomi Phone'
    elif 'iphone' in ua:
        dev = 'Apple iPhone'
    elif 'ipad' in ua:
        dev = 'Apple iPad'
    elif 'macintosh' in ua or 'mac os' in ua:
        dev = 'Mac Computer'
    elif 'windows' in ua:
        dev = 'Windows PC'
    else:
        dev = 'Mobile Device'
        
    if 'chrome' in ua and 'safari' in ua:
        browser = 'Chrome'
    elif 'safari' in ua:
        browser = 'Safari'
    elif 'firefox' in ua:
        browser = 'Firefox'
    else:
        browser = 'Browser'
        
    return f"{dev} ({browser})"

# 3. Routes
@app.route('/')
def index():
    cfg = load_config()
    subs = load_subscriptions()
    return render_template('index.html', config=cfg, subscribers=subs)

@app.route('/portal')
def portal():
    cfg = load_config()
    return render_template('portal.html', config=cfg)

@app.route('/card')
def card():
    cfg = load_config()
    return render_template('card.html', config=cfg)

@app.route('/sw.js')
def service_worker():
    response = send_from_directory(os.path.join(BASE_DIR, 'static'), 'sw.js')
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@app.route('/manifest.json')
def manifest():
    return send_from_directory(os.path.join(BASE_DIR, 'static'), 'manifest.json')

@app.route('/api/vapid-public-key')
def vapid_key():
    return jsonify({"publicKey": VAPID_PUBLIC_KEY})

@app.route('/api/subscribe', methods=['POST'])
def subscribe():
    data = request.json or {}
    sub_info = data.get('subscription')
    ua = data.get('userAgent', request.headers.get('User-Agent', ''))
    
    if not sub_info or not sub_info.get('endpoint'):
        return jsonify({"success": False, "error": "Invalid subscription object"}), 400
        
    subs = load_subscriptions()
    endpoint = sub_info['endpoint']
    
    # Avoid duplicate endpoints
    subs = [s for s in subs if s.get('subscription', {}).get('endpoint') != endpoint]
    
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
    new_entry = {
        "subscription": sub_info,
        "userAgent": ua,
        "device": parse_device(ua),
        "created_at": now_str
    }
    subs.append(new_entry)
    save_subscriptions(subs)
    
    return jsonify({"success": True, "message": "تم تسجيل الهاتف بنجاح!"})

@app.route('/api/send', methods=['POST'])
def send_push():
    cfg = load_config()
    data = request.json or {}
    
    title = data.get('title', 'تنبيه من شبكة الواي فاي')
    message = data.get('message', '').strip()
    urgent = bool(data.get('urgent', False))
    
    if not message:
        return jsonify({"success": False, "error": "نص الرسالة مطلوب"}), 400
        
    subs = load_subscriptions()
    if not subs:
        return jsonify({"success": False, "error": "لا يوجد هواتف مسجلة بعد في الشبكة"}), 400
        
    payload = json.dumps({
        "title": title,
        "body": message,
        "urgent": urgent,
        "icon": "/static/icons/icon.png",
        "badge": "/static/icons/icon.png",
        "url": "/portal"
    }, ensure_ascii=False)
    
    sent_count = 0
    stale_endpoints = []
    
    for item in subs:
        sub_info = item.get('subscription')
        if not sub_info:
            continue
        try:
            webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=PRIVATE_KEY_PATH,
                vapid_claims={"sub": "mailto:admin@local.network"}
            )
            sent_count += 1
        except WebPushException as ex:
            print(f"WebPush error: {ex}")
            # If 404 or 410, subscription is dead / revoked
            if ex.response and ex.response.status_code in (404, 410):
                stale_endpoints.append(sub_info.get('endpoint'))
        except Exception as e:
            print(f"General send error: {e}")
            
    # Remove dead subscriptions if any
    if stale_endpoints:
        subs = [s for s in subs if s.get('subscription', {}).get('endpoint') not in stale_endpoints]
        save_subscriptions(subs)
        
    # Save to history
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
    record = {
        "title": title,
        "message": message,
        "urgent": urgent,
        "timestamp": now_str,
        "sent_count": sent_count
    }
    history = cfg.get('history', [])
    history.insert(0, record)
    cfg['history'] = history[:30]
    save_config(cfg)
    
    return jsonify({
        "success": True,
        "sent": sent_count,
        "message": f"تم إرسال الإشعار لـ {sent_count} هاتف بنجاح! 🚀"
    })

@app.route('/api/settings', methods=['POST'])
def update_settings():
    cfg = load_config()
    data = request.json or {}
    
    if 'wifi_ssid' in data:
        cfg['wifi_ssid'] = data['wifi_ssid'].strip()
    if 'wifi_password' in data:
        cfg['wifi_password'] = data['wifi_password'].strip()
    if 'public_url' in data and data['public_url'].strip():
        cfg['public_url'] = data['public_url'].strip().rstrip('/')
        
    save_config(cfg)
    return jsonify({"success": True, "config": cfg})

@app.route('/qr/wifi.png')
def qr_wifi():
    cfg = load_config()
    ssid = cfg.get('wifi_ssid', 'MyWiFi')
    pwd = cfg.get('wifi_password', '')
    content = f"WIFI:T:WPA;S:{ssid};P:{pwd};;"
    img = qrcode.make(content)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

def get_public_url():
    cfg = load_config()
    custom_url = cfg.get('public_url', '').strip()
    if custom_url and not custom_url.startswith('http://127.0.0.1'):
        return custom_url.rstrip('/')
    # Fallback to current request URL if available
    try:
        from flask import request
        if request and request.host_url:
            return request.host_url.rstrip('/')
    except Exception:
        pass
    return "http://localhost:5001"

@app.route('/qr/portal.png')
def qr_portal():
    portal_url = f"{get_public_url()}/portal"
    img = qrcode.make(portal_url)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
