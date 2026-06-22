#!/bin/bash
nohup java -jar /mnt/d/AI_test/target/LTER-infra-R1.0.11.jar > /tmp/lter.log 2>&1 &
echo $! > /tmp/lter.pid
echo "Started PID=$(cat /tmp/lter.pid)"
