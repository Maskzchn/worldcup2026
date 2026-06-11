#!/bin/bash
# 2026世界杯竞猜平台 - 启动脚本
# 用法: bash run.sh [start|stop|restart]

cd "$(dirname "$0")"
APP_DIR="$PWD"
PID_FILE="$APP_DIR/wc2026.pid"
PORT=8888

start() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "服务已在运行，PID=$(cat $PID_FILE)"
        exit 1
    fi
    setsid python3 -u app.py >> "$APP_DIR/wc2026.log" 2>&1 &
    WC_PID=$!
    echo $WC_PID > "$PID_FILE"
    # 等待最多10秒让waitress启动
    for i in 1 2 3 4 5 6 7 8 9 10; do
        sleep 1
        if curl -s -o /dev/null http://127.0.0.1:$PORT/ 2>/dev/null; then
            echo "✅ 世界杯竞猜平台已启动"
            echo "   访问地址: http://localhost:$PORT"
            echo "   访问地址: http://<服务器IP>:$PORT"
            echo "   管理后台: http://<服务器IP>:$PORT/admin"
            echo "   日志文件: $APP_DIR/wc2026.log"
            return 0
        fi
    done
    echo "❌ 启动失败，查看日志: $APP_DIR/wc2026.log"
    exit 1
}

stop() {
    if [ -f "$PID_FILE" ]; then
        kill $(cat "$PID_FILE") 2>/dev/null
        rm -f "$PID_FILE"
        echo "服务已停止"
    else
        echo "服务未运行"
    fi
}

case "${1:-start}" in
    start) start ;;
    stop) stop ;;
    restart) stop; sleep 1; start ;;
    *) echo "用法: $0 [start|stop|restart]" ;;
esac