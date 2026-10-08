import asyncio
import os
import time
from random import choice

import requests
from telethon import Button, events
from telethon.tl import functions, types  # pylint:ignore

from CythonX import *
from CythonX._misc._assistant import asst_cmd, callback, in_pattern
from CythonX._misc._decorators import heartless_cmd
from CythonX._misc._wrappers import eod, eor, prememoji
from CythonX.dB import DEVLIST, heartless_IMAGES
from CythonX.dB.premium_db import *
from CythonX.fns.helper import *
from CythonX.fns.misc import *
from CythonX.fns.tools import *
from CythonX.startup._database import _BaseDatabase as Database
from CythonX.version import __version__, heartless_version
from strings import get_help, get_string

udB: Database

Redis = udB.get_key
con = TgConverter
quotly = Quotly()
OWNER_NAME = heartless_bot.full_name
OWNER_ID = heartless_bot.uid

heartless_bot: heartlessClient
asst: heartlessClient

LOG_CHANNEL = udB.get_key("LOG_CHANNEL")

try:
    os.system(f"git config user.name 'LoopXS'")
    os.system(f"git config user.email 'LoopXS@github.com'")
    LOGS.info("Successfully set the git username and email")
except Exception as e:
    LOGS.info(f"Error occured in git add : {str(e)}")


def inline_pic():
    INLINE_PIC = udB.get_key("INLINE_PIC")
    if INLINE_PIC is None:
        INLINE_PIC = choice(heartless_IMAGES)
    elif INLINE_PIC == False:
        INLINE_PIC = None
    return INLINE_PIC


Telegraph = telegraph_client()

List = []
Dict = {}
InlinePlugin = {}
N = 0
cmd = heartless_cmd
STUFF = {}

# Chats, which needs to be ignore for some cases
# Considerably, there can be many
# Feel Free to Add Any other...

NOSPAM_CHAT = []

KANGING_STR = [
    "Using Witchery to kang this sticker...",
    "Plagiarising hehe...",
    "Inviting this sticker over to my pack...",
    "Kanging this sticker...",
    "Hey that's a nice sticker!\nMind if I kang?!..",
    "Hehe me stel ur stiker...",
    "Ay look over there (☉｡☉)!→\nWhile I kang this...",
    "Roses are red violets are blue, kanging this sticker so my pack looks cool",
    "Imprisoning this sticker...",
    "Mr.Steal-Your-Sticker is stealing this sticker... ",
]

ATRA_COL = [
    "DarkCyan",
    "DeepSkyBlue",
    "DarkTurquoise",
    "Cyan",
    "LightSkyBlue",
    "Turquoise",
    "MediumVioletRed",
    "Aquamarine",
    "Lightcyan",
    "Azure",
    "Moccasin",
    "PowderBlue",
]

emojidict = {
    "dir": [5433653135799228968, 5017546864392668003, 5931718859366075705],
    "star": [4976558436708778794, 5287573013070360336],
    "git": [6012602873190290473, 5933540612694347912],
    "gplay": [6012412627613913850, 6005624796874805845, 5931594395508805861],
    "insta": [6012406511580484246, 5935998223045889696, 5429244905920673045, 6298711741656205491, 5301209173457910527],
    "shield": [6012683352287482800],
    "record": [6005631638757708253, 6003338925085561474],
    "tg": [5017077798129369907, 6255593645848660539, 6296303781126604562],
    "ban": [5949458495932731725, 5852487725051023314],
    "utube": [5934029049260150525],
    "spot": [5935973449674527211, 5350434575321407442],
    "king": [5911153495095906417, 5415644153243517562],
    "fprint": [5899838712992240333],
    "prem": [5897862946431701391, 4976558436708778794, 5926968513867550458, 5287573013070360336, 5852827336705053876, 6300559565435963297, 5364047804878570490],
    "play": [5415808049195531172],
    "load": [5260343246831237239, 5310041868191407556, 5971895400792067820, 5971944878815317190],
    "comp": [5800961642351038386],
    "phone": [5800750183931188489],
    "music": [5924827335231540757, 5431351772062954805, 5429263327035419602],
    "admin": [6298555228752971886],
    "run": [5301083932211550593, 5300999883996536855],
    "vscode": [5301201579955725162],
    "py": [5300928913956938544],
    "owner": [5429182100613904863],
    "kali": [5431872747300991644, 5949503687578619382],
    "ai": [5855132205134647532],
    "warn": [4927486932113425461, 5364241851500997604, 5213205860498549992],
    "win": [5933679370202778681, 5927109109621984802, 6298333093044422573],
    "vip": [6219549292458150316],
    "wait" : [5326015457155620929],
    "delete" : [6298650293559101195],
    "live" : [5415968410389467390],
    "invalid" : [5956091557525327060],
    
}
for key, value in emojidict.items():
    for i in value:
        if is_emp(i) is None:
            add_emp(key, i)
