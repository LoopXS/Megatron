# Mᴇgᴀᴛrᴏn Bot
# Copyright (C) 2020 Mᴇgᴀᴛrᴏn 
# This file is a part of < https://github.com/CipherX1-ops/Megatron/ >
# PLease read the GNU Affero General Public License in <https://www.github.com/CipherX1-ops/Megatron/blob/main/LICENSE/>


FROM theteamultroid/ultroid:main

# set timezone
ENV TZ=Asia/Tehran

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \

    # cloning the repo and installing requirements.
    && git clone https://github.com/LoopXS/Megatron.git /root/LoopXS/ \
    && pip3 install --no-cache-dir -r root/LoopXS/requirements.txt \
    && pip3 install --no-cache-dir -r root/LoopXS/resources/startup/optional-requirements.txt \
    && pip3 uninstall av -y && pip3 install av --no-binary av

# changing workdir
WORKDIR /root/LoopXS/

# start the bot
CMD ["bash", "resources/startup/startup.sh"]
