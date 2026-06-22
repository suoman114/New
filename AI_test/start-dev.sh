#!/bin/bash
JAR=/mnt/d/AI_test/target/LTER-infra-R1.0.0.jar
LOG=/tmp/lter-infra.log
PID_FILE=/tmp/lter-infra.pid

# 기존 프로세스 종료
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    kill "$OLD_PID" 2>/dev/null && echo "Stopped old process PID=$OLD_PID"
fi

echo "" > "$LOG"
nohup java -jar "$JAR" --spring.profiles.active=dev >> "$LOG" 2>&1 &
echo $! > "$PID_FILE"
echo "Started LTER-infra PID=$(cat $PID_FILE)"
echo "Log: $LOG"
