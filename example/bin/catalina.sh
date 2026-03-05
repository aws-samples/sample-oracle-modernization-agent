#!/bin/bash

# Tomcat-style log management for Spring Boot Application
# Usage: ./catalina.sh {start|stop|run|logs}

APP_NAME="amzn-backoffice"
APP_DIR="/home/ec2-user/workspace/src-orcl"
PID_FILE="$APP_DIR/bin/$APP_NAME.pid"
CATALINA_OUT="$APP_DIR/bin/catalina.out"
JAR_FILE="$APP_DIR/target/$APP_NAME-1.0.0.jar"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            return 0
        else
            rm -f "$PID_FILE"
            return 1
        fi
    else
        return 1
    fi
}

# Tomcat-style start (background)
start() {
    print_status "Starting $APP_NAME in background..."
    
    if is_running; then
        PID=$(cat "$PID_FILE")
        print_warning "$APP_NAME is already running (PID: $PID)"
        return 1
    fi
    
    # Build first
    cd "$APP_DIR"
    mvn clean package -DskipTests > /dev/null 2>&1
    
    if [ $? -ne 0 ]; then
        print_error "Failed to build application"
        return 1
    fi
    
    # Start in background, output to catalina.out
    cd "$APP_DIR"
    nohup java -jar "$JAR_FILE" > "$CATALINA_OUT" 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"
    
    sleep 3
    if is_running; then
        print_success "$APP_NAME started successfully (PID: $PID)"
        print_status "Output redirected to: $CATALINA_OUT"
        print_status "Application URL: http://localhost:8080/amzn-bo"
    else
        print_error "Failed to start $APP_NAME"
        print_error "Check catalina.out: $CATALINA_OUT"
        return 1
    fi
}

# Tomcat-style run (foreground)
run() {
    print_status "Starting $APP_NAME in foreground..."
    
    if is_running; then
        PID=$(cat "$PID_FILE")
        print_warning "$APP_NAME is already running (PID: $PID)"
        return 1
    fi
    
    # Build first
    cd "$APP_DIR"
    mvn clean package -DskipTests
    
    if [ $? -ne 0 ]; then
        print_error "Failed to build application"
        return 1
    fi
    
    # Run in foreground
    print_status "Running application in foreground (Ctrl+C to stop)..."
    cd "$APP_DIR"
    java -jar "$JAR_FILE"
}

# Stop application
stop() {
    print_status "Stopping $APP_NAME..."
    
    if ! is_running; then
        print_warning "$APP_NAME is not running"
        return 1
    fi
    
    PID=$(cat "$PID_FILE")
    print_status "Stopping process (PID: $PID)..."
    
    kill $PID
    
    for i in {1..10}; do
        if ! is_running; then
            print_success "$APP_NAME stopped successfully"
            rm -f "$PID_FILE"
            return 0
        fi
        sleep 1
    done
    
    print_warning "Graceful shutdown failed, forcing termination..."
    kill -9 $PID
    rm -f "$PID_FILE"
    print_success "$APP_NAME forcefully stopped"
}

# Show logs (like tail -f catalina.out)
logs() {
    if [ -f "$CATALINA_OUT" ]; then
        case "$2" in
            -f|--follow)
                print_status "Following catalina.out (Ctrl+C to exit)..."
                tail -f "$CATALINA_OUT"
                ;;
            -n)
                if [ -n "$3" ] && [[ "$3" =~ ^[0-9]+$ ]]; then
                    tail -n "$3" "$CATALINA_OUT"
                else
                    print_error "Invalid number of lines: $3"
                    return 1
                fi
                ;;
            "")
                tail -50 "$CATALINA_OUT"
                ;;
            *)
                print_error "Unknown option: $2"
                echo "Usage: $0 logs [-f] [-n NUM]"
                return 1
                ;;
        esac
    else
        print_error "catalina.out not found: $CATALINA_OUT"
        return 1
    fi
}

# Show version info
version() {
    print_status "AMZN BackOffice Application"
    print_status "Spring Boot Application (Tomcat-style management)"
    print_status "Java Version: $(java -version 2>&1 | head -n 1)"
    if [ -f "$JAR_FILE" ]; then
        print_status "JAR File: $JAR_FILE"
        print_status "JAR Size: $(du -h "$JAR_FILE" | cut -f1)"
    fi
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    run)
        run
        ;;
    logs)
        logs "$@"
        ;;
    version)
        version
        ;;
    *)
        echo "Usage: $0 {start|stop|run|logs|version}"
        echo ""
        echo "Commands:"
        echo "  start   - Start application in background (like Tomcat)"
        echo "  stop    - Stop application"
        echo "  run     - Run application in foreground"
        echo "  logs    - Show catalina.out logs"
        echo "  version - Show version information"
        echo ""
        echo "Log options:"
        echo "  logs       - Show last 50 lines"
        echo "  logs -f    - Follow logs (like tail -f catalina.out)"
        echo "  logs -n N  - Show last N lines"
        echo ""
        echo "Examples:"
        echo "  $0 start"
        echo "  $0 logs -f"
        echo "  $0 stop"
        exit 1
        ;;
esac

exit $?
