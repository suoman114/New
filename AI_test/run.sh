#!/bin/bash

case $1 in
    start)

    nohup java -jar /mnt/d/AI_test/target/LTER-infra-R1.0.2.jar > /tmp/lter.log 2>&1 &

    echo "Started PID=$(cat /tmp/lter.pid)"
    sleep 2
    netstat -anp | grep 8080
    ;;
    stop)
    PID=`ps -ef | grep java | grep LTER | awk '{print $2}'`
        if [ -z $PID ]
        then
            echo "LTER_Infra is not running"
        else
            echo "stopping LTER"
                kill $PID
                sleep 1
                PID=`ps -ef | grep java | grep LTER | awk '{print $2}'`
                if [ ! -z $PID ]
                then
                    echo "kill -9"
                    kill -9 $PID
                fi
                echo "LTER stopped"
    fi
    ;;
esac

