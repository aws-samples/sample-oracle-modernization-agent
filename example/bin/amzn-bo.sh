#!/bin/bash

# AMZN BackOffice Application Management Script
# Usage: ./amzn-bo.sh {start|stop|restart|status}

APP_NAME="amzn-backoffice"
APP_DIR="/home/ec2-user/workspace/src-orcl"
PID_FILE="$APP_DIR/bin/$APP_NAME.pid"
LOG_FILE="$APP_DIR/bin/$APP_NAME.log"
JAR_FILE="$APP_DIR/target/$APP_NAME-1.0.0.jar"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
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
    print_status "Starting $APP_NAME..."
    
    if is_running; then
        PID=$(cat "$PID_FILE")
        print_warning "$APP_NAME is already running (PID: $PID)"
        return 1
    fi
    
    # Build the application first
    print_status "Building application..."
    cd "$APP_DIR"
    mvn clean package -DskipTests > /dev/null 2>&1
    
    if [ $? -ne 0 ]; then
        print_error "Failed to build application"
        return 1
    fi
    
    # Start the application in background (completely detached)
    print_status "Starting application in background..."
    cd "$APP_DIR"
    
    # Use setsid to create a new session and completely detach from terminal
    setsid bash -c "
        exec java -jar '$JAR_FILE' > '$LOG_FILE' 2>&1 &
        echo \$! > '$PID_FILE'
    " &
    
    # Wait for PID file to be created
    sleep 2
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        # Wait a moment and check if it's still running
        sleep 3
        if is_running; then
            print_success "$APP_NAME started successfully (PID: $PID)"
            print_status "Log file: $LOG_FILE"
            print_status "Application URL: http://localhost:8080/amzn-bo"
            print_status "Use './bin/amzn-bo.sh logs -f' to follow logs"
            return 0
        else
            print_error "Failed to start $APP_NAME"
            print_error "Check log file: $LOG_FILE"
            return 1
        fi
    else
        print_error "Failed to create PID file"
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
    print_status "Stopping process (PID: $PID)..."
    
    # Try graceful shutdown first
    kill $PID
    
    # Wait for graceful shutdown
    for i in {1..10}; do
        if ! is_running; then
            print_success "$APP_NAME stopped successfully"
            rm -f "$PID_FILE"
            return 0
        fi
        sleep 1
    done
    
    # Force kill if graceful shutdown failed
    print_warning "Graceful shutdown failed, forcing termination..."
    kill -9 $PID
    rm -f "$PID_FILE"
    print_success "$APP_NAME forcefully stopped"
    return 0
}

# Function to restart the application
restart() {
    print_status "Restarting $APP_NAME..."
    stop
    sleep 2
    start
}

# Function to show application status
status() {
    print_status "Checking $APP_NAME status..."
    
    if is_running; then
        PID=$(cat "$PID_FILE")
        print_success "$APP_NAME is running (PID: $PID)"
        
        # Show memory usage
        MEMORY=$(ps -p $PID -o rss= | awk '{print int($1/1024)" MB"}')
        print_status "Memory usage: $MEMORY"
        
        # Show port status
        PORT_STATUS=$(netstat -tlnp 2>/dev/null | grep ":8080 " | grep "$PID")
        if [ -n "$PORT_STATUS" ]; then
            print_status "Listening on port 8080"
        else
            print_warning "Not listening on port 8080"
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
        case "$2" in
            -f|--follow)
                print_status "Following log file (Ctrl+C to exit)..."
                tail -f "$LOG_FILE"
                ;;
            -n)
                if [ -n "$3" ] && [[ "$3" =~ ^[0-9]+$ ]]; then
                    print_status "Showing last $3 lines of log file..."
                    tail -n "$3" "$LOG_FILE"
                else
                    print_error "Invalid number of lines: $3"
                    return 1
                fi
                ;;
            --error|--errors)
                print_status "Showing error logs..."
                grep -i "error\|exception\|failed" "$LOG_FILE" | tail -20
                ;;
            --warn|--warnings)
                print_status "Showing warning logs..."
                grep -i "warn" "$LOG_FILE" | tail -20
                ;;
            --clear)
                print_status "Clearing log file..."
                > "$LOG_FILE"
                print_success "Log file cleared"
                ;;
            --size)
                if [ -f "$LOG_FILE" ]; then
                    SIZE=$(du -h "$LOG_FILE" | cut -f1)
                    LINES=$(wc -l < "$LOG_FILE")
                    print_status "Log file size: $SIZE ($LINES lines)"
                else
                    print_error "Log file not found"
                fi
                ;;
            "")
                print_status "Showing last 50 lines of log file..."
                tail -50 "$LOG_FILE"
                ;;
            *)
                print_error "Unknown log option: $2"
                echo "Available options:"
                echo "  logs         - Show last 50 lines"
                echo "  logs -f      - Follow logs in real-time"
                echo "  logs -n NUM  - Show last NUM lines"
                echo "  logs --error - Show error logs"
                echo "  logs --warn  - Show warning logs"
                echo "  logs --clear - Clear log file"
                echo "  logs --size  - Show log file size"
                return 1
                ;;
        esac
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
        echo "Usage: $0 {start|stop|restart|status|logs [options]}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the application in background"
        echo "  stop    - Stop the application"
        echo "  restart - Restart the application"
        echo "  status  - Show application status"
        echo "  logs    - Show application logs"
        echo ""
        echo "Log options:"
        echo "  logs         - Show last 50 lines"
        echo "  logs -f      - Follow logs in real-time"
        echo "  logs -n NUM  - Show last NUM lines"
        echo "  logs --error - Show error logs only"
        echo "  logs --warn  - Show warning logs only"
        echo "  logs --clear - Clear log file"
        echo "  logs --size  - Show log file size"
        echo ""
        echo "Examples:"
        echo "  $0 start"
        echo "  $0 status"
        echo "  $0 logs -f"
        echo "  $0 logs -n 100"
        echo "  $0 logs --error"
        exit 1
        ;;
esac

exit $?
