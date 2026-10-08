"""
**Get Answers from Chat GPT including OpenAI, Bing and Sydney**
**Or generate images with Dall-E-3XL**

Dall-E

• Examples: 
> `{i}dalle3 Will Smith eating spagbowl`
> `{i}dalle2 Christmas cat stuck in a tree`

• `{i}dalle2` HIGH Qualility Dall-E-2
• `{i}dalle3` IRL Dall-E-3

> `{i}igen Sexy girl`
> `{i}igen2 Christmas cat stuck in a tree`
> `{i}igen3 Man looking at lake`

**• Examples: **
> `{i}gpt2 How to get a url in Python`
> `{i}gpt3t write me an essay`
> `{i}gpt4 Tell me a joke` `can you tell me another`
> `{i}gt4p How to create list in python`
> `{i}gt4 How to create class in python`
> `{i}gemi Tell me a lots of jokes`

• `{i}gpt2` Safone API
• `{i}gpt3t` OpenAI GPT35-Turbo Powered by Alpha
• `{i}gpt4` Bing AI w History Powered by Alpha
• `{i}gt4p` `{i}gt4` GPT-4 Turbo History Powered by Lioabots
• `{i}gemi` Gemini Pro
• `{i}igen2` Dall-E-3XL ImageGen
• `{i}igen3` ProteusV0.2
"""

from typing import Any, Dict, Optional
import aiohttp
import base64
import asyncio
import openai as gt4p
from os import remove, system
from telethon import TelegramClient, events
from io import BytesIO
from PIL import Image
import requests
import json
from . import *


import os
import sys
from pydantic import BaseModel

try:
    import openai
except ImportError:
    system("pip3 install -q openai==0.28.0")
    import openai

from CythonX.fns.tools import AwesomeCoding
from . import (
    LOGS,
    async_searcher,
    check_filename,
    fast_download,
    udB,
    HNDLR,
    heartless_cmd,
    heartless_bot,
)

if udB.get_key("UFOPAPI"):
    UFoPAPI = udB.get_key("UFOPAPI")
else:
    UFoPAPI = "h32dfKsl8pQUxsNftkogIuDF32pYTwKluIY8emI1Hs" #Default API key for heartless
    

api_base = udB.get_key("GTPbase")
laiobots_api = udB.get_key("LIAOBOTSAPI")

# Global variable to store conversation history
gpt4_conversation_history = []


@heartless_cmd(
    pattern="(chat)?gt4p( ([\\s\\S]*)|$)",
)
async def handle_gpt4p(event):
    gt4p.api_key = laiobots_api
    gt4p.api_base = api_base
    global gpt4_conversation_history
    query = event.raw_text.split(f"{HNDLR}gt4p", 1)[-1].strip()
    reply = await event.respond("Generating answer...")

    # Append the user's query to the conversation history
    gpt4_conversation_history.append({"role": "user", "content": query})

    # Using OpenAI GPT-4 Turbo API with conversation history
    chat_completion = gt4p.ChatCompletion.create(
        model="gpt-4-plus",
        messages=gpt4_conversation_history,
        stream=False,
    )

    if isinstance(chat_completion, dict):
        answer = chat_completion.choices[0].message.content
    else:
        answer = ""
        for token in chat_completion:
            content = token["choices"][0]["delta"].get("content")
            if content is not None:
                answer += content

    # Append the AI's response to the conversation history
    gpt4_conversation_history.append({"role": "assistant", "content": answer})

    reply_text = (
        f"<b>Query:</b>\n~ <i>{query}</i>\n\n"
        f"<b>GPT:</b> <i>(OpenAI GPT-4 Turbo)</i>\n~ <i>{answer}</i>"
    )
    await reply.edit(reply_text, parse_mode="html")


@heartless_cmd(
    pattern="(chat)?gt4( ([\\s\\S]*)|$)",
    fullsudo=True,
)
async def handle_gpt4p(event):
    gt4p.api_key = laiobots_api
    gt4p.api_base = api_base
    global gpt4_conversation_history
    query = event.raw_text.split(f"{HNDLR}gt4", 1)[-1].strip()
    reply = await event.respond("Generating answer...")

    # Append the user's query to the conversation history
    gpt4_conversation_history.append({"role": "user", "content": query})

    # Using OpenAI GPT-4 Turbo API with conversation history
    chat_completion = gt4p.ChatCompletion.create(
        model="gpt-4-turbo-preview",
        messages=gpt4_conversation_history,
        stream=False,
    )

    if isinstance(chat_completion, dict):
        answer = chat_completion.choices[0].message.content
    else:
        answer = ""
        for token in chat_completion:
            content = token["choices"][0]["delta"].get("content")
            if content is not None:
                answer += content

    # Append the AI's response to the conversation history
    gpt4_conversation_history.append({"role": "assistant", "content": answer})

    reply_text = (
        f"<b>Query:</b>\n~ <i>{query}</i>\n\n"
        f"<b>GPT:</b> <i>(OpenAI GPT-4 Turbo)</i>\n~ <i>{answer}</i>"
    )
    await reply.edit(reply_text, parse_mode="html")


gpt35_conversation_history = []

@heartless_cmd(
    pattern="(chat)?gpt3t( ([\\s\\S]*)|$)",
)
async def handle_gpt35(message):
    base = b'\xff\xfeh\x00t\x00t\x00p\x00s\x00:\x00/\x00/\x00g\x00p\x00t\x00-\x00a\x00p\x00i\x00.\x00m\x00y\x00c\x00l\x00o\x00u\x00d\x00.\x00i\x00m\x00/\x00v\x001\x00'
    openai.api_key = "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"
    openai.api_base = base.decode('utf-16')
    global gpt35_conversation_history
    query = message.raw_text.split(f"{HNDLR}gpt3t", 1)[-1].strip()
    reply = await message.edit(f"`Generating answer...`")

    gpt35_conversation_history.append({"role": "user", "content": query})

    # Using OpenAI GPT-3.5 Turbo API
    chat_completion = openai.ChatCompletion.create(
        model="gpt-3.5-long",
        messages=gpt35_conversation_history,
        stream=True,
    )

    if isinstance(chat_completion, dict):
        answer = chat_completion.choices[0].message.content
    else:
        answer = ""
        for token in chat_completion:
            content = token["choices"][0]["delta"].get("content")
            if content is not None:
                answer += content

    gpt35_conversation_history.append({"role": "assistant", "content": answer})

    reply = (
        f"<b>Query:</b>\n~ <i>{query}</i>\n\n"
        f"<b>GPT:</b> <i>(OpenAI GPT-3.5)</i>\n~ <i>{answer}</i>"
    )
    await message.edit(reply, parse_mode="html")



bing_conversation_history = []


@heartless_cmd(
    pattern="(chat)?gpt4( ([\\s\\S]*)|$)",
)
async def handle_gpt4(message):
    base = b'\xff\xfeh\x00t\x00t\x00p\x00s\x00:\x00/\x00/\x00g\x00p\x00t\x00-\x00a\x00p\x00i\x00.\x00m\x00y\x00c\x00l\x00o\x00u\x00d\x00.\x00i\x00m\x00/\x00v\x001\x00'
    openai.api_key = "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"
    openai.api_base = base.decode('utf-16')
    global bing_conversation_history
    query = message.raw_text.split(f"{HNDLR}gpt4", 1)[-1].strip()
    reply = await message.edit(f"Generating answer...")

    bing_conversation_history.append({"role": "user", "content": query})

    chat_completion = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=bing_conversation_history,
        stream=True,
    )

    if isinstance(chat_completion, dict):
        answer = chat_completion.choices[0].message.content
    else:
        answer = ""
        for token in chat_completion:
            content = token["choices"][0]["delta"].get("content")
            if content is not None:
                answer += content

    bing_conversation_history.append({"role": "assistant", "content": answer})

    reply = (
        f"<b>Query:</b>\n~ <i>{query}</i>\n\n"
        f"<b>GPT:</b> <i>(CoPilot)</i>\n~ <i>{answer}</i>"
    )
    await message.edit(reply, parse_mode="html")


@heartless_cmd(
    pattern="(chat)?gpt2( ([\\s\\S]*)|$)",
)
async def chatgpt_v2(e):
    query = e.pattern_match.group(2)
    reply = await e.get_reply_message()
    if not query:
        if reply and reply.text:
            query = reply.message
    if not query:
        return await e.eor("`Gimme a Question to ask from ChatGPT`")

    eris = await e.eor("__Generating answer...__")
    payloads = {
        "message": query,
        "chat_mode": "assistant",
        "dialog_messages": "[{'bot': '', 'user': ''}]",
    }
    try:
        response = await async_searcher(
            "https://api.safone.dev/chatgpt",
            post=True,
            json=payloads,
            re_json=True,
            headers={"Content-Type": "application/json"},
        )
        if not (response and "message" in response):
            LOGS.error(response)
            raise ValueError("Invalid Response from Server")

        response = response.get("message")
        if len(response + query) < 4080:
            to_edit = f"<b>Query:</b> <i>(v2)</i>\n\n~ <i>{query}</i>\n\n<b>GPT:</b>\n~ <i>{response}</i>"
            await eris.edit(to_edit, parse_mode="html")
            return
        with BytesIO(response.encode()) as file:
            file.name = "gpt_response.txt"
            await e.respond(
                f"<i>{args[:1000]} ...</i>",
                file=file,
                reply_to=e.reply_to_msg_id or e.id,
                parse_mode="html",
            )
        await eris.delete()
    except Exception as exc:
        LOGS.exception(exc)
        await eris.edit(f"**GPT (v2) ran into an Error:** \n\n`{exc}`")


@heartless_cmd(
    pattern="(chat)?igen( ([\\s\\S]*)|$)",
)
async def handle_dalle3xl(message):
    query = message.raw_text.split(f"{HNDLR}igen", 1)[-1].strip()
    reply = await message.edit(f"Generating image...")

    try:
        response = AwesomeCoding(
            extra_headers={"api-key": UFoPAPI}, extra_payload={"query": query}
        )
        
        response_data = await async_searcher(
            url=response.opendalle_url.decode("utf-16"),
            post=True,
            headers=response.extra_headers,
            json=response.extra_payload,
            re_json=True,
        )

        if "randydev" in response_data:
            image_data_base64 = response_data["randydev"]["data"]
            image_data = base64.b64decode(image_data_base64)

            image_filename = "output.jpg"

            with open(image_filename, "wb") as image_file:
                image_file.write(image_data)

            caption = f"{query}"
            await reply.delete()
            await message.client.send_file(
                message.chat_id,
                image_filename,
                caption=caption,
                reply_to=(
                    message.reply_to_msg_id
                    if message.is_reply and message.reply_to_msg_id
                    else None
                ),
            )

            os.remove(image_filename)
        else:
            LOGS.exception(f"KeyError")
            error_message = response_data["detail"][0]["error"]
            await reply.edit(error_message)
            return

    except requests.exceptions.RequestException as e:
        ErrInfo(e)
        error_message = f"Error while generating image: {str(e)}"
        await reply.edit(error_message)

    except KeyError as e:
        ErrInfo(e)
        error_message = f"A KeyError occurred: {str(e)}, Try Again.."
        await reply.edit(error_message)
        await asyncio.sleep(3)
        await reply.delete()

    except Exception as e:
        LOGS.exception(f"Error: {str(e)}")
        error_message = f"An unexpected error occurred: {str(e)}"
        await reply.edit(error_message)


@heartless_cmd(
    pattern="(chat)?igen2( ([\\s\\S]*)|$)",
)
async def handle_dalle3xl(message):
    query = message.raw_text.split(f"{HNDLR}igen2", 1)[-1].strip()
    reply = await message.edit(f"Generating image...")

    try:
        response = AwesomeCoding(
            extra_headers={"api-key": UFoPAPI}, extra_payload={"query": query}
        )
        
        response_data = await async_searcher(
            url=response.dalle3xl_url.decode("utf-16"),
            post=True,
            headers=response.extra_headers,
            json=response.extra_payload,
            re_json=True,
        )

        if "randydev" in response_data:
            image_data_base64 = response_data["randydev"]["data"]
            image_data = base64.b64decode(image_data_base64)

            image_filename = "output.jpg"

            with open(image_filename, "wb") as image_file:
                image_file.write(image_data)

            caption = f"{query}"
            await reply.delete()
            await message.client.send_file(
                message.chat_id,
                image_filename,
                caption=caption,
                reply_to=(
                    message.reply_to_msg_id
                    if message.is_reply and message.reply_to_msg_id
                    else None
                ),
            )

            os.remove(image_filename)
        else:
            LOGS.exception(f"KeyError")
            error_message = response_data["detail"][0]["error"]
            await reply.edit(error_message)
            return

    except requests.exceptions.RequestException as e:
        ErrInfo(e)
        error_message = f"Error while generating image: {str(e)}"
        await reply.edit(error_message)

    except KeyError as e:
        ErrInfo(e)
        error_message = f"A KeyError occurred: {str(e)}, Try Again.."
        await reply.edit(error_message)
        await asyncio.sleep(3)
        await reply.delete()

    except Exception as e:
        LOGS.exception(f"Error: {str(e)}")
        error_message = f"An unexpected error occurred: {str(e)}"
        await reply.edit(error_message)


@heartless_cmd(
    pattern="(chat)?igen3( ([\\s\\S]*)|$)",
)
async def handle_proteusv02(message):
    query = message.raw_text.split(f"{HNDLR}igen3", 1)[-1].strip()
    reply = await message.edit(f"Generating image...")

    try:
        response = AwesomeCoding(
            extra_headers={"api-key": UFoPAPI}, extra_payload={"query": query}
        )

        response_data = await async_searcher(
            url=response.proteusv0_2_url.decode("utf-16"),
            post=True,
            headers=response.extra_headers,
            json=response.extra_payload,
            re_json=True,
        )

        if "randydev" in response_data:
            image_data_base64 = response_data["randydev"]["data"]
            image_data = base64.b64decode(image_data_base64)

            image_filename = "output.jpg"

            with open(image_filename, "wb") as image_file:
                image_file.write(image_data)

            caption = f"{query}"
            await reply.delete()
            await message.client.send_file(
                message.chat_id,
                image_filename,
                caption=caption,
                reply_to=(
                    message.reply_to_msg_id
                    if message.is_reply and message.reply_to_msg_id
                    else None
                ),
            )

            os.remove(image_filename)
        else:
            LOGS.exception(f"KeyError")
            error_message = response_data["detail"][0]["error"]
            await reply.edit(error_message)
            return

    except requests.exceptions.RequestException as e:
        ErrInfo(e)
        error_message = f"Error while generating image: {str(e)}"
        await reply.edit(error_message)

    except KeyError as e:
        ErrInfo(e)
        error_message = f"A KeyError occurred: {str(e)}, Try Again.."
        await reply.edit(error_message)
        await asyncio.sleep(3)
        await reply.delete()

    except Exception as e:
        ErrInfo(e)
        error_message = f"An unexpected error occurred: {str(e)}"
        await reply.edit(error_message)


gemini_conversation_history = []


@heartless_cmd(
    pattern="(chat)?gemi( ([\\s\\S]*)|$)",
)
async def handle_gemi(message):
    base = b'\xff\xfeh\x00t\x00t\x00p\x00s\x00:\x00/\x00/\x00g\x00p\x00t\x00-\x00a\x00p\x00i\x00.\x00m\x00y\x00c\x00l\x00o\x00u\x00d\x00.\x00i\x00m\x00/\x00v\x001\x00'
    openai.api_key = udB.get_key("OPENAI_API")
    openai.api_base = base.decode('utf-16')
    global gemini_conversation_history

    if not gemini_conversation_history:  # If gemini_conversation_history is empty
        await message.edit(f"`Searching for Gemini-Ultra. . .`")
        # Perform initial query
        initial_query = "Hello, Gemini-Ultra"
        gemini_conversation_history.append({"role": "user", "content": initial_query})
        chat_completion = openai.ChatCompletion.create(
            model="gemini-pro",
            messages=gemini_conversation_history,
            stream=True,
        )

        if isinstance(chat_completion, dict):
            answer = chat_completion.choices[0].message.content
        else:
            answer = ""
            for token in chat_completion:
                content = token["choices"][0]["delta"].get("content")
                if content is not None:
                    answer += content

        gemini_conversation_history.append({"role": "assistant", "content": answer})

    query = message.raw_text.split(f"{HNDLR}gemi", 1)[-1].strip()
    reply = await message.edit(f"`Generating answer...`")

    gemini_conversation_history.append({"role": "user", "content": query})

    try:
        chat_completion = openai.ChatCompletion.create(
            model="gemini-pro",
            messages=gemini_conversation_history,
            stream=True,
        )

        if isinstance(chat_completion, dict):
            answer = chat_completion.choices[0].message.content
        else:
            answer = ""
            for token in chat_completion:
                content = token["choices"][0]["delta"].get("content")
                if content is not None:
                    answer += content

        gemini_conversation_history.append({"role": "assistant", "content": answer})

        reply = (
            f"**Query:**\n~ __{query}__\n\n" f"**GPT:** __(Gemini-Ultra)__\n~ __{answer}__"
        )
        await message.edit(reply, parse_mode="markdown")

    except Exception as e:
        traceback.print_exc()  # Print the traceback for debugging
        # Handle the error by sending the reply as a .txt file
        filename = "error_reply.txt"
        with open(filename, "w") as file:
            file.write(reply)
        await message.respond(file=filename)
        os.remove(filename)


dall: str = (
    b"\xff\xfeh\x00t\x00t\x00p\x00s\x00:\x00/\x00/\x00s\x00a\x00n\x00c\x00h\x00i\x00t\x00x\x00i\x00m\x00a\x00g\x00e\x00.\x00o\x00n\x00r\x00e\x00n\x00d\x00e\x00r\x00.\x00c\x00o\x00m\x00"
)

async def get_image_urls_async(query):
    response = await async_searcher(
        f"{dall.decode('utf-16')}/dall-e-3/prompt=" + query, re_json=True
    )
    return [response[f"S{i}-Image"] for i in range(1, 5)]


async def download_images(image_urls):
    downloaded_paths = []
    for i, url in enumerate(image_urls, start=1):
        filename = f"image_{i}.png"
        response = await async_searcher(url, re_content=True)
        with open(filename, "wb") as f:
            f.write(response)
        downloaded_paths.append(filename)
    return downloaded_paths


async def send_images(message, query, image_paths):
    caption = f"Dᴀʟʟ-E-3:\n{query}"
    media = [await message.client.upload_file(path) for path in image_paths]
    await message.client.send_message(
        message.to_id, caption, file=media, parse_mode="markdown"
    )
    for path in image_paths:
        os.remove(path)


@heartless_cmd(
    pattern="(chat)?dalle2( ([\\s\\S]*)|$)",
)
async def handle_dalle2(message):
    query = message.raw_text.split(f"{HNDLR}dalle2", 1)[-1].strip()
    if query:
        reply = await message.eor(f"Generating image...")
    else:
        await message.eor(f"Invalid input try again", time=10)
        return

    try:
        url = await async_searcher(
            f"{dall.decode('utf-16')}/dall-e-2/prompt={query} in size of16:9.1024*1980 ratio",
            re_json=True,
        )
        image_url = url["img"]
        path, _ = await fast_download(
            image_url, filename=check_filename("dall-e-2.png")
        )
        await message.respond(
            f"Dᴀʟʟ-E-2\n{query}",
            file=path,
            reply_to=message.reply_to_msg_id or message.id,
            parse_mode="markdown",
        )
        remove("dall-e-2.png")
        await reply.delete()
    except FilePartsInvalidError:
        remove("dall-e-2.png")
        await reply.edit("An error occurred while sending the file. Please try again.")
    except Exception as e:
        ErrInfo(e, full=True)
        error_message = f"An unexpected error occurred: {str(e)}"
        await reply.eor(error_message, time=10)
   

@heartless_cmd(
    pattern="(chat)?dalle3( ([\\s\\S]*)|$)",
)
async def handle_dalle3(message):
    query = message.raw_text.split(f"{HNDLR}dalle3", 1)[-1].strip()
    if query:
        reply = await message.eor(f"Generating image...")
    else:
        await message.eor(f"Invalid input try again", time=10)
        return
    image_urls = await get_image_urls_async(query)
    try:
        image_paths = await download_images(image_urls)
        await send_images(message, query, image_paths)
        await reply.delete()
    except FilePartsInvalidError:
        await reply.eor(
            "An error occurred while sending the file. Please try again.", time=5
        )
    except Exception as e:
        ErrInfo(e, full=True)
        error_message = f"An unexpected error occurred: {str(e)}"
        await reply.eor(error_message, time=10)
