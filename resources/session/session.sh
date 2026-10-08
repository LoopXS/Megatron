#!/usr/bin/env bash
# Megatron Bot
# Copyright (C) 2020 Mᴇgᴀᴛrᴏn 
#
# This file is a part of < https://github.com/LoopXS/Megatron/ >
# PLease read the GNU Affero General Public License in
# <https://www.github.com/LoopXS/Megatron/blob/main/LICENSE/>.

clear
echo -e "\e[1m"
echo "    _______       __             _  __ "
echo "   / ____(_)___  / /_  ___  ____| |/ / "
echo "  / /   / / __ \/ __ \/ _ \/ ___/   /  "
echo " / /___/ / /_/ / / / /  __/ /  /   |   "
echo " \____/_/ .___/_/ /_/\___/_/  /_/|_|   "
echo "       /_/                             "
echo -e "\e[0m"
sec=5
spinner=(⣻ ⢿ ⡿ ⣟ ⣯ ⣷)
while [ $sec -gt 0 ]; do
    echo -ne "\e[33m ${spinner[sec]} Starting dependency installation in $sec seconds...\r"
    sleep 1
    sec=$(($sec - 1))
done
echo -e "\e[1;32mInstalling Dependencies ---------------------------\e[0m\n" # Don't Remove Dashes / Fix it
apt-get update
apt-get upgrade -y
pkg upgrade -y
pkg install python wget -y
wget https://raw.githubusercontent.com/LoopXS/Megatron/main/resources/session/ssgen.py
pip install telethon
clear
python3 ssgen.py
