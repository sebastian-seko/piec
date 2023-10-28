#!/bin/bash
while :
do
	sudo python3 compare.py	
	sudo cp /data/message.txt /data/message2.txt
	read -p "Press enter to continue"
	clear
done
