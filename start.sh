#!/bin/bash
cd "$(dirname "$0")"

# Kill old instances if running
pkill -f "python3 app.py" 2>/dev/null
pkill -f "cloudflared tunnel" 2>/dev/null

echo "🚀 جاري تشغيل خادم الإشعارات الخاص..."
python3 app.py > app.log 2>&1 &
APP_PID=$!

sleep 2

echo "🔒 جاري تشغيل النفق المشفر الآمن (HTTPS)..."
./cloudflared tunnel --url http://127.0.0.1:5001 > cloudflare.log 2>&1 &
TUNNEL_PID=$!

sleep 4
TUNNEL_URL=$(grep -o 'https://[a-zA-Z0-9.-]*\.trycloudflare\.com' cloudflare.log | head -n 1)

if [ -n "$TUNNEL_URL" ]; then
    echo "✅ الرابط المشفر النشط: $TUNNEL_URL"
    curl -s -X POST http://127.0.0.1:5001/api/settings \
      -H "Content-Type: application/json" \
      -d "{\"public_url\": \"$TUNNEL_URL\"}" > /dev/null
fi

echo ""
echo "=========================================================="
echo "🎉 النظام يعمل الآن بنجاح وبشكل خاص ومستقل 100%!"
echo "لوحة تحكم المدير: http://localhost:5001"
echo "رابط بوابة المشتركين (HTTPS): $TUNNEL_URL/portal"
echo "كارت الطباعة: http://localhost:5001/card"
echo "=========================================================="

wait $APP_PID
