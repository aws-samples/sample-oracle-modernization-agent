#!/bin/bash

# AMZN BackOffice Application Management Script (Maven Version)
# Usage: ./amzn-bo-maven.sh {start|stop|restart|status}

APP_NAME="amzn-backoffice-maven"
APP_DIR="/home/ec2-user/workspace/src-orcl"
PID_FILE="$APP_DIR/bin/$APP_NAME.pid"
LOG_FILE="$APP_DIR/bin/$APP_NAME.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Function to check if application is running
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

# Function to start the application
start() {
    print_status "Starting $APP_NAME with Maven..."
    
    if is_running; then
        PID=$(cat "$PID_FILE")
        print_warning "$APP_NAME is already running (PID: $PID)"
        return 1
    fi
    
    # Start the application in background using Maven
    print_status "Starting application in background..."
    cd "$APP_DIR"
    nohup mvn spring-boot:run > "$LOG_FILE" 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"
    
    # Wait a moment and check if it's still running
    sleep 5
    if is_running; then
        print_success "$APP_NAME started successfully (PID: $PID)"
        print_status "Log file: $LOG_FILE"
        print_status "Application URL: http://localhost:8080/amzn-bo"
        return 0
    else
        print_error "Failed to start $APP_NAME"
        print_error "Check log file: $LOG_FILE"
        return 1
    fi
}

# Function to stop the application
stop() {
    print_status "Stopping $APP_NAME..."
    
    if ! is_running; then
        print_warning "$APP_NAME is not running"
        return 1
    fi
    
    PID=$(cat "$PID_FILE")
    print_status "Stopping Maven process tree (PID: $PID)..."
    
    # Kill the entire process tree (Maven spawns child processes)
    pkill -P $PID
    kill $PID
    
    # Wait for shutdown
    for i in {1..15}; do
        if ! is_running; then
            print_success "$APP_NAME stopped successfully"
            rm -f "$PID_FILE"
            return 0
        fi
        sleep 1
    done
    
    # Force kill if needed
    print_warning "Graceful shutdown failed, forcing termination..."
    pkill -9 -P $PID
    kill -9 $PID
    rm -f "$PID_FILE"
    print_success "$APP_NAME forcefully stopped"
    return 0
}

# Function to restart the application
restart() {
    print_status "Restarting $APP_NAME..."
    stop
    sleep 3
    start
}

# Function to show application status
status() {
    print_status "Checking $APP_NAME status..."
    
    if is_running; then
        PID=$(cat "$PID_FILE")
        print_success "$APP_NAME is running (PID: $PID)"
        
        # Show child processes
        CHILDREN=$(pgrep -P $PID | wc -l)
        print_status "Child processes: $CHILDREN"
        
        # Show port status
        PORT_STATUS=$(netstat -tlnp 2>/dev/null | grep ":8080 ")
        if [ -n "$PORT_STATUS" ]; then
            print_status "Listening on port 8080"
        else
            print_warning "Not listening on port 8080 yet"
        fi
        
        # Show recent log entries
        if [ -f "$LOG_FILE" ]; then
            print_status "Recent log entries:"
            tail -5 "$LOG_FILE"
        fi
    else
        print_error "$APP_NAME is not running"
        return 1
    fi
}

# Function to show logs
logs() {
    if [ -f "$LOG_FILE" ]; then
        if [ "$2" = "-f" ]; then
            print_status "Following log file (Ctrl+C to exit)..."
            tail -f "$LOG_FILE"
        else
            print_status "Showing last 50 lines of log file..."
            tail -50 "$LOG_FILE"
        fi
    else
        print_error "Log file not found: $LOG_FILE"
        return 1
    fi
}

# Main script logic
case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    logs)
        logs "$@"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs [-f]}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the application in background (Maven)"
        echo "  stop    - Stop the application"
        echo "  restart - Restart the application"
        echo "  status  - Show application status"
        echo "  logs    - Show application logs"
        echo "  logs -f - Follow application logs"
        exit 1
        ;;
esac

exit $?
