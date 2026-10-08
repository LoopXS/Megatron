# Megatron UserBot

<p align="center">
  <img src="./resources/extras/heartless.jpg" alt="Megatron UserBot" width="220">
</p>

<h3 align="center">A powerful, modular and extensible Telegram UserBot built with Python & Telethon</h3>

<p align="center">
  <strong>Plugin-based architecture · Multi-database support · Assistant Bot · Media tools · Group management · Inline features</strong>
</p>

<p align="center">

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python)
![Telethon](https://img.shields.io/badge/Telethon-UserBot-2CA5E0?style=for-the-badge&logo=telegram)
![License](https://img.shields.io/badge/License-AGPL--3.0-blue?style=for-the-badge)
![Architecture](https://img.shields.io/badge/Architecture-Modular-success?style=for-the-badge)

</p>

---

## ✨ Overview

**Megatron** is a modular Telegram UserBot written in **Python** and built around **Telethon**.

The project is designed around a dynamic plugin architecture: most functionality is implemented as independent plugins that are discovered and loaded automatically at startup. This makes it possible to enable, disable, extend or replace individual features without modifying the core runtime.

The project also contains a dedicated `CythonX` runtime layer responsible for:

- Telegram client initialization
- Session validation
- Plugin loading
- Database abstraction
- Command decorators
- Permission and sudo handling
- Error handling
- Assistant Bot integration
- Manager functionality
- Addon loading
- Fast media upload/download helpers
- Localization
- Deployment/runtime utilities

---

## 🚀 Features

Megatron provides a large collection of Telegram automation and utility features.

### 👤 UserBot Core

- Customizable command handler
- Sudo system
- Owner-only commands
- Developer-only commands
- Dual command mode
- Edited-message command support
- Chat blacklist support
- Automatic plugin discovery
- Runtime plugin installation
- Plugin unloading
- Automatic command/help registration
- Centralized error handling
- Logging and crash reporting
- Configurable language
- Persistent configuration storage

### 🤖 Assistant Bot

The project can run a separate Telegram Bot account alongside the UserBot.

The Assistant can be used for:

- Inline functionality
- Private assistant commands
- Logging
- User interaction
- PM-related functionality
- Automatic BotFather setup
- Inline bot integration

If `USER_MODE` is enabled, the project can instead use the main client as the assistant.

### 🛡️ Administration

The included administration tools cover common Telegram moderation tasks:

- Ban / unban
- Temporary ban
- Kick
- Mute / unmute
- Promote / demote
- Pin / unpin
- Global ban
- Global mute
- Warning system
- Anti-flood
- Locks
- Blacklists
- Force subscription
- Automated moderation
- Admin utilities

### 👥 Group Management

Megatron includes tools for managing groups and channels:

- Chat information
- User management
- Group/channel creation
- Group picture management
- User removal
- Admin utilities
- Welcome messages
- Goodbye messages
- Thank-member system
- Tagging tools
- Chat actions
- Scheduled messages
- Night mode
- Group-specific filters

### 🎨 Media & Image Tools

The project contains multiple media-processing plugins.

Supported functionality includes:

- Image resizing
- Image conversion
- Image filters
- Blur
- Grayscale
- Negative effect
- Mirror
- Flip
- Sketch
- Toon effects
- Pixelation
- Borders
- GIF conversion
- GIF reverse
- GIF effects
- Video screenshots
- Video trimming
- Video sampling
- Audio trimming
- Audio conversion
- Media information
- Compression
- PDF processing
- QR generation and decoding
- Sticker tools
- Custom emoji tools
- Font generation
- Logo generation
- Glitch effects
- Web screenshots
- Background removal
- Telegraph uploads

### 📥 Download & Upload

Several plugins provide downloading and uploading functionality:

- Telegram media download/upload
- YouTube media tools
- Instagram downloads
- Twitter/X utilities
- Google Drive
- Pixeldrain
- Web upload services
- File sharing
- Repository ZIP generation
- Generic URL tools
- Fast Telethon upload/download helpers

### 🔎 Search & Information

Megatron includes utilities for:

- Web search
- Image search
- GitHub search
- Google-related search
- Weather
- Air quality
- Word meanings
- Synonyms
- Antonyms
- Wikipedia-style information
- User information
- IP information
- Telegram information
- URL inspection
- QR code processing
- Shazam
- Spotify utilities
- Instagram utilities
- Twitter utilities

### 🧠 AI & Smart Features

The project contains integrations for multiple AI-oriented services and APIs, including functionality exposed through the `chatgpt` plugin.

Depending on the configured external APIs/services, the project contains support for:

- ChatGPT-related commands
- GPT variants
- Gemini-related commands
- DALL-E-related commands
- AI image generation
- External AI APIs

These integrations may require additional API keys and/or external services.

### 🎮 Games & Fun

Included functionality covers:

- Inline games
- Emoji games
- Dice
- Darts
- Basketball
- Football
- Slot machine
- Text animations
- Fun commands
- Meme utilities
- Fake actions
- ASCII tools

### 🗂️ Notes, Snippets & Filters

Persistent chat utilities include:

- Notes
- Snippets
- Filters
- Echo responses
- Custom commands
- NSFW filters
- Profanity filtering
- Greetings
- AFK system
- Warning system

### 📡 Voice Chat

The project has optional Voice Chat support through `PyTgCalls`.

The repository supports a separate `VC_SESSION` and can dynamically load the external VCBot implementation when enabled.

### 🌐 Localization

Localization is implemented through YAML language files.

Currently included:

- 🇬🇧 English
- 🇮🇷 Persian
- 🇹🇷 Turkish

The language system can also dynamically translate missing strings when possible.

---

# 🧩 Architecture

The project is organized around a modular runtime rather than placing all functionality in a single bot file.

```text
                         ┌──────────────────────┐
                         │      Telegram API    │
                         └──────────┬───────────┘
                                    │
                              ┌─────▼─────┐
                              │ Telethon  │
                              └─────┬─────┘
                                    │
                         ┌──────────▼──────────┐
                         │     CythonX Core     │
                         │                      │
                         │ Client / Config      │
                         │ Decorators           │
                         │ Loader               │
                         │ Error Handling       │
                         │ Helpers              │
                         └───────┬──────┬──────┘
                                 │      │
                 ┌───────────────┘      └────────────────┐
                 │                                        │
          ┌──────▼──────┐                         ┌──────▼──────┐
          │   Plugins   │                         │   Assistant │
          │   plugins/  │                         │  assistant/ │
          └──────┬──────┘                         └─────────────┘
                 │
          ┌──────▼──────┐
          │   Addons    │
          │   addons/   │
          └──────┬──────┘
                 │
        ┌────────▼─────────┐
        │ Database Layer   │
        │ Redis / MongoDB  │
        │ PostgreSQL / DB  │
        └──────────────────┘
```

---

# 📁 Project Structure

```text
Megatron/
│
├── CythonX/                     # Core runtime
│   ├── _misc/                   # Decorators, wrappers and support utilities
│   ├── dB/                      # Database helper modules
│   ├── fns/                     # Shared functions and utilities
│   ├── startup/                 # Startup, client and deployment logic
│   ├── configs.py               # Environment/configuration variables
│   ├── loader.py                # Dynamic plugin loader
│   ├── exceptions.py
│   ├── version.py
│   └── __main__.py              # Main runtime entry point
│
├── plugins/                     # Official plugins
│
├── assistant/                   # Assistant Bot modules
│   └── manager/                 # Group manager modules
│
├── strings/                     # Localization
│   └── strings/
│       ├── en.yml
│       └── fa.yml
│
├── resources/
│   ├── fonts/                   # Fonts used by media/font tools
│   ├── extras/                  # Images and other runtime assets
│   ├── session/                 # Session generation utilities
│   └── startup/                 # Startup/deployment scripts
│
├── spotifysearch/               # Spotify helper implementation
│
├── requirements.txt             # Main Python dependencies
├── addons.txt                   # Additional addon dependencies
├── .env.sample                  # Environment variable template
├── Dockerfile / Dock            # Container deployment
├── docker-compose.yml           # Docker Compose configuration
├── heroku.yml                   # Heroku container configuration
├── Procfile                     # Process definition
├── installer.sh                 # Linux installation script
└── startup                      # Startup wrapper
```

---

# 🔌 Plugin System

One of the main design principles of Megatron is its plugin-based architecture.

Official plugins live inside:

```text
plugins/
```

At startup, `CythonX.loader.Loader` scans the plugin directory and dynamically imports the available Python modules.

Plugins can register commands using the project's decorators.

For example:

```python
from CythonX._misc._decorators import heartless_cmd


@heartless_cmd(pattern="hello$")
async def hello(event):
    await event.edit("Hello from Megatron!")
```

The command handler is automatically registered with Telethon.

---

## Plugin Loading

The loader supports:

- Automatic discovery
- Include lists
- Exclude lists
- Single-plugin loading
- Addon loading
- Post-load hooks
- Runtime command registration
- Plugin command tracking
- Help generation

The main loader is:

```text
CythonX/loader.py
```

Additional startup plugin orchestration is implemented in:

```text
CythonX/startup/loader.py
```

---

# 🧱 Plugin Inventory

The repository contains a broad set of official plugins.

### Administration & Moderation

```text
admintools
antiflood
autoban
blacklist
cleanaction
forcesubscribe
globaltools
locks
mute
nsfwfilter
profanityfilter
warn
```

### Group & Chat Management

```text
broadcast
bot
chats
echo
greetings
notes
schedulemsg
tag
timebio
userlogs
```

### UserBot Management

```text
asst_cmd
core
database
devtools
sudo
usage
variables
```

### Media & Image Processing

```text
audiotools
beautify
compressor
converter
giftools
glitch
imagetools
mediatools
resize
videotools
```

### File & Storage

```text
downloadupload
fileshare
gdrive
pixeldrain
repozip
ziptools
webupload
```

### Social / Web Services

```text
instagram
twitter
youtube
igmusic
search
unsplash
shazam
spotifysearch
```

### Telegram Media & Stickers

```text
customemoji
stickertools
qrcode
story
reaction
logo
fontgen
```

### AI / Smart Services

```text
chatgpt
writer
calculator
words
weather
```

### Fun & Games

```text
emojigame
inlinegames
fakeaction
extra
specialtools
```

### Utility Plugins

```text
utilities
tools
urltools
profile
polls
converter
other
f2l
```

### Internal / Framework Plugins

Plugins beginning with `_` are primarily internal/runtime components, including:

```text
_chatactions
_heartless
_help
_inline
_userlogs
_wspr
```

These should generally be treated as framework-level components rather than ordinary user-facing plugins.

---

# 🗄️ Database Layer

Megatron provides an abstraction layer that allows persistent configuration and plugin data to be stored using different backends.

The database system is implemented in:

```text
CythonX/startup/_database.py
```

and plugin-specific database helpers are located in:

```text
CythonX/dB/
```

## Supported Backends

The runtime supports:

| Backend | Configuration |
|---|---|
| Redis | `REDIS_URI` / `REDISHOST` |
| MongoDB | `MONGO_URI` |
| PostgreSQL | `DATABASE_URL` |
| Local database | Automatic fallback |

The selection order is effectively:

```text
Redis
  ↓
MongoDB
  ↓
PostgreSQL
  ↓
LocalDB
```

For local deployments without a remote database, the project can fall back to its local database implementation.

---

## Database Modules

The repository contains dedicated database helpers for features such as:

```text
AFK
AntiFlood
Assistant Commands
Blacklist
Blacklist Chats
Bot Chat
Echo
File Store
Filters
Force Subscribe
Global Ban/Mute
Greetings
Mute
Notes
NSFW
Premium / Custom Emoji
Snippets
Voice Chat Sudo
Warnings
```

This keeps feature-specific persistence separate from the core runtime.

---

# 🔐 Configuration

Configuration is primarily read from environment variables and persistent database settings.

A minimal configuration looks like:

```env
API_ID=
API_HASH=
SESSION=
REDIS_URI=
REDIS_PASSWORD=
```

See:

```text
.env.sample
```

for the minimal environment template.

---

## Required Variables

### `API_ID`

Telegram API ID obtained from Telegram's official developer portal.

### `API_HASH`

Telegram API hash associated with the API ID.

### `SESSION`

A Telethon-compatible String Session for the account that will run the UserBot.

### Database

One of the following storage configurations can be used:

```env
REDIS_URI=
REDIS_PASSWORD=
```

or:

```env
MONGO_URI=
```

or:

```env
DATABASE_URL=
```

If no external database is configured, the local database backend may be used.

---

# ⚙️ Optional Configuration

The project also supports a large number of optional settings.

Some of the most important ones are:

| Variable | Purpose |
|---|---|
| `BOT_TOKEN` | Assistant Bot token |
| `LOG_CHANNEL` | Logging channel |
| `VC_SESSION` | Separate Voice Chat session |
| `VCBOT` | Enable Voice Chat Bot |
| `ADDONS` | Enable external addons |
| `ADDONS_URL` | Custom addon repository |
| `HNDLR` | Main command handler |
| `DUAL_MODE` | Enable dual command mode |
| `DUAL_HNDLR` | Secondary command handler |
| `SUDO_HNDLR` | Sudo command handler |
| `USER_MODE` | Use UserBot as assistant |
| `MANAGER` | Enable group manager |
| `PMBOT` | Enable PM bot features |
| `ASSISTANT` | Enable Assistant functionality |
| `TAKE_EDITS` | Process edited messages |
| `EXCLUDE_OFFICIAL` | Disable selected official plugins |
| `INCLUDE_ONLY` | Load only selected official plugins |
| `EXCLUDE_ADDONS` | Disable selected addons |
| `INCLUDE_ADDONS` | Load only selected addons |
| `LANGUAGE` | Localization language |
| `TIMEZONE` | Timezone-related features |
| `OPENAI_API` | AI functionality |
| `GDRIVE_AUTH_TOKEN` | Google Drive functionality |
| `PIXELDRAIN_API_KEY` | Pixeldrain functionality |
| `SPOTIFY` | Spotify-related features |
| `TWITTER_USERNAME` | Twitter/X integration |
| `TWITTER_EMAIL` | Twitter/X integration |
| `TWITTER_PASSWORD` | Twitter/X integration |

Many additional feature-specific settings are stored in the persistent database rather than the initial `.env` file.

---

# 🎛️ Command Handlers

The default command prefix is:

```text
.
```

For example:

```text
.help
.info
.id
.sudo
```

The handler can be changed through the database configuration.

### Main Handler

```text
HNDLR
```

Default:

```text
.
```

### Dual Mode

The project can optionally use a second handler:

```text
DUAL_HNDLR
```

Default:

```text
/
```

### Sudo Handler

The sudo command prefix is controlled by:

```text
SUDO_HNDLR
```

---

# 🧑‍💻 Sudo & Permission System

Commands are not simply exposed to every user.

The decorator system supports several permission levels:

```text
Owner
  │
  ├── Full Sudo
  │
  ├── Sudo
  │
  ├── Admin
  │
  ├── Developer
  │
  └── Normal User
```

Plugin commands can specify restrictions such as:

```python
@heartless_cmd(
    pattern="example$",
    owner_only=True,
)
```

or:

```python
@heartless_cmd(
    pattern="example$",
    admins_only=True,
)
```

or:

```python
@heartless_cmd(
    pattern="example$",
    fullsudo=True,
)
```

The decorator system also supports:

- Group-only commands
- Admin-only commands
- Owner-only commands
- Developer-only commands
- Sudo-aware commands
- Assistant commands
- Manager commands

---

# 🧰 Core Utilities

The `CythonX/fns/` directory provides shared functionality used throughout the project.

Important modules include:

```text
admins.py
executor.py
FastTelethon.py
gDrive.py
helper.py
info.py
misc.py
tools.py
ytdl.py
```

These provide functionality such as:

- Admin checks
- Shell execution
- Fast Telegram transfers
- Google Drive integration
- HTTP requests
- Formatting helpers
- Media helpers
- YouTube utilities
- General Telegram utilities

---

# ⚡ Fast Upload / Download

Megatron includes custom asynchronous upload/download helpers based around the FastTelethon implementation.

This is used by media-related features to provide:

- Progress reporting
- Asynchronous transfers
- Telegram file uploads
- Telegram file downloads

Relevant implementation:

```text
CythonX/fns/FastTelethon.py
```

---

# 🌍 Localization

Localization is handled through:

```text
strings/
```

Current language files:

```text
strings/strings/en.yml
strings/strings/fa.yml
```

The active language can be configured through:

```text
LANGUAGE
```

The string loader also attempts to provide fallback/translation behavior when a requested translation is not explicitly present.

---

# 🐳 Docker

The repository includes container deployment support.

The main Docker setup installs system-level dependencies including:

- Python
- FFmpeg
- Git
- curl
- wget
- unzip
- GnuPG

and starts the project using:

```bash
python3 -m CythonX
```

### Build

```bash
docker build -t megatron .
```

### Run

```bash
docker run --env-file .env megatron
```

---

# 🐳 Docker Compose

A `docker-compose.yml` file is included.

Run:

```bash
docker compose up -d --build
```

Check logs:

```bash
docker compose logs -f
```

Stop:

```bash
docker compose down
```

---

# ☁️ Heroku / Container Deployment

The repository contains:

```text
heroku.yml
Procfile
app.json
```

The project is configured around a worker process running the CythonX runtime.

The deployment configuration supports environment variables for:

- Telegram API credentials
- Session
- Redis
- MongoDB
- PostgreSQL
- Assistant Bot
- Log Channel
- Voice Chat

---

# 🖥️ Local Installation

## 1. Clone the repository

```bash
git clone https://github.com/LoopXS/Megatron.git
cd Megatron
```

---

## 2. Create a virtual environment

Linux/macOS:

```bash
python3 -m venv venv
source venv/bin/activate
```

Windows:

```powershell
python -m venv venv
venv\Scripts\activate
```

---

## 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

Some optional plugins may require additional packages.

The repository also contains:

```text
resources/startup/optional-requirements.txt
```

which can be installed when needed.

---

## 4. Obtain Telegram API credentials

Create Telegram API credentials and obtain:

```text
API_ID
API_HASH
```

from Telegram's official developer portal:

https://my.telegram.org/

---

## 5. Generate a Session

The repository includes a session-generation utility.

Run:

```bash
bash sessiongen
```

The generated String Session should be kept private.

Alternatively, a compatible Telethon String Session can be supplied through:

```env
SESSION=
```

---

## 6. Configure `.env`

Copy the sample:

```bash
cp .env.sample .env
```

Then configure:

```env
API_ID=123456
API_HASH=your_api_hash
SESSION=your_string_session

REDIS_URI=your_redis_host
REDIS_PASSWORD=your_redis_password
```

---

## 7. Start Megatron

The primary runtime entry point is:

```bash
python3 -m CythonX
```

The repository also contains a startup wrapper:

```bash
bash startup
```

---

# 🧪 Development

For development, the most important directories are:

```text
CythonX/
plugins/
assistant/
strings/
```

A typical development workflow is:

```bash
git clone https://github.com/LoopXS/Megatron.git
cd Megatron

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.sample .env
# Configure .env

python3 -m CythonX
```

---

# ➕ Creating a Plugin

A basic plugin can be created under:

```text
plugins/myplugin.py
```

Example:

```python
from CythonX._misc._decorators import heartless_cmd


@heartless_cmd(pattern="hello$")
async def hello(event):
    await event.edit("Hello from Megatron!")
```

After restarting the UserBot, the loader discovers the plugin automatically.

For plugins requiring additional permissions:

```python
@heartless_cmd(
    pattern="hello$",
    owner_only=True,
)
async def hello(event):
    await event.edit("Hello, owner!")
```

---

# 🔄 Runtime Plugin Installation

The project contains a safe plugin installation mechanism.

Plugins can be installed dynamically through the UserBot's plugin-management functionality.

Before installation, the runtime checks plugin source code for potentially dangerous patterns such as:

```text
os.system
subprocess
exec
eval
__import__
file writes
shutil operations
session-related access
API credential access
```

This is implemented through the project's `KEEP_SAFE` mechanism.

> **Important:** This is a heuristic security check, not a sandbox. Never install untrusted Python code simply because it passes the check.

---

# 🧩 Addons

Megatron can optionally load external addons.

Addon configuration is controlled by settings such as:

```text
ADDONS
ADDONS_URL
INCLUDE_ADDONS
EXCLUDE_ADDONS
```

The startup system can clone/update an addon repository and load its Python plugins dynamically.

By default, the addon loader is designed around the project's external addon repository configuration.

---

# 📦 Dependencies

The main dependency list includes packages for:

- Telethon
- HTTP networking
- YouTube / media downloading
- Git integration
- Redis
- Voice Chat
- Telegraph
- Image/media processing
- External APIs

Core requirements are declared in:

```text
requirements.txt
```

Additional addon-related dependencies are declared in:

```text
addons.txt
```

Optional startup dependencies are available in:

```text
resources/startup/optional-requirements.txt
```

Some features install or require their dependencies only when the corresponding functionality is enabled.

---

# 🎙️ Voice Chat

Voice Chat support is optional.

The project can use:

```env
VC_SESSION=
VCBOT=true
```

The startup system checks for the Voice Chat dependency and can load the external VCBot implementation.

Voice Chat functionality is exposed through the `vctools` plugin.

---

# 📊 Logging & Error Handling

Megatron provides centralized logging through the `CythonX` runtime.

Logs are written to files such as:

```text
heartless.log
```

The command decorator also captures plugin exceptions and can send detailed crash information to the configured log channel.

Error information may contain:

- Project version
- Telethon version
- Date/time
- Chat ID
- Sender ID
- Command/event text
- Traceback
- Exception details

For production deployments, configuring a private log channel is recommended.

---

# 🔧 Useful Runtime Settings

A number of settings can be configured through the database system.

Examples include:

```text
HNDLR
DUAL_HNDLR
SUDO_HNDLR
DUAL_MODE
USER_MODE
ASSISTANT
MANAGER
PMBOT
VCBOT
LOG_CHANNEL
LOG_OFF
TAKE_EDITS
EXCLUDE_OFFICIAL
INCLUDE_ONLY
EXCLUDE_ADDONS
INCLUDE_ADDONS
LANGUAGE
TIMEZONE
```

Feature-specific settings are also maintained by individual plugins.

---

# 🗃️ Persistent Feature Data

The project uses individual database modules instead of forcing every feature into a single monolithic database implementation.

For example:

```text
CythonX/dB/afk_db.py
CythonX/dB/notes_db.py
CythonX/dB/filter_db.py
CythonX/dB/warn_db.py
CythonX/dB/mute_db.py
CythonX/dB/greetings_db.py
CythonX/dB/snips_db.py
```

This structure makes feature development and maintenance easier.

---

# 🔒 Security

A Telegram UserBot operates with access to the Telegram account associated with its Session.

Treat the following as **highly sensitive credentials**:

```text
SESSION
API_HASH
BOT_TOKEN
REDIS_PASSWORD
MONGO_URI
DATABASE_URL
VC_SESSION
API keys
third-party service credentials
browser cookies
```

### Never publish them publicly.

Especially important:

> **Do not commit `.env`, Telegram sessions, API credentials or browser cookies to Git.**

The repository currently contains a `cookies.txt` file. If that file contains active browser authentication cookies, it should **not** be committed to a public repository. Any credentials/cookies that have already been exposed publicly should be revoked or rotated.

A safer `.gitignore` should include entries such as:

```gitignore
.env
*.session
*.session-journal
cookies.txt
heartless*.log
*.log
```

---

# ⚠️ Important Operational Notes

### 1. This is a UserBot

The project operates through a Telegram user account/session and should be used responsibly.

### 2. Telegram API limits apply

Telegram may apply flood limits to accounts performing large numbers of requests.

Megatron includes handling for `FloodWaitError`, but this does not eliminate Telegram's limits.

### 3. Third-party APIs may change

Features such as:

```text
YouTube
Instagram
Twitter/X
Google
Spotify
AI services
Image services
```

may depend on external APIs or websites whose behavior can change independently of Megatron.

### 4. Optional features have optional dependencies

Not every plugin necessarily works immediately after installing only the base requirements.

Some plugins require additional packages, binaries, API keys or external accounts.

### 5. Do not run untrusted plugins

Plugins are Python code and therefore can execute arbitrary operations if they are written to do so.

---

# 🧭 Startup Flow

The main runtime roughly follows this sequence:

```text
python -m CythonX
        │
        ▼
Load environment/configuration
        │
        ▼
Initialize logging
        │
        ▼
Initialize database
        │
        ▼
Validate Telegram Session
        │
        ▼
Create Telethon client
        │
        ▼
Initialize Assistant / VC client
        │
        ▼
Run startup tasks
        │
        ▼
Load official plugins
        │
        ├──────► Load Assistant plugins
        │
        ├──────► Load Manager plugins
        │
        ├──────► Load Addons
        │
        └──────► Load Voice Chat plugins
        │
        ▼
Register commands & handlers
        │
        ▼
UserBot Ready
```

---

# 🏗️ Core Components

## `CythonX`

The core runtime of the project.

Responsible for:

- Client lifecycle
- Configuration
- Startup
- Database
- Loading
- Telegram event handling
- Shared utilities

---

## `CythonX.loader`

Dynamic plugin loader.

```python
Loader(path="plugins")
```

It supports:

- Plugin discovery
- Include/exclude rules
- Addon loading
- Module imports
- Error isolation

---

## `CythonX._misc._decorators`

Contains the main command decorator:

```python
heartless_cmd()
```

This layer handles:

- Telegram event registration
- Permission checks
- Sudo
- Owner checks
- Admin checks
- Assistant commands
- Manager commands
- Dual mode
- Error handling
- Flood waits
- Plugin command tracking

---

## `CythonX.startup._database`

Database abstraction layer supporting:

```text
Redis
MongoDB
PostgreSQL
LocalDB
```

---

## `CythonX.dB`

Feature-specific persistence modules.

---

## `plugins`

The primary user-facing feature layer.

---

## `assistant`

Assistant Bot functionality.

---

## `assistant/manager`

Group Manager functionality.

---

# 📚 File Reference

| File / Directory | Purpose |
|---|---|
| `CythonX/__main__.py` | Main application startup |
| `CythonX/__init__.py` | Core runtime initialization |
| `CythonX/configs.py` | Environment configuration |
| `CythonX/loader.py` | Dynamic plugin loader |
| `CythonX/startup/` | Startup/runtime system |
| `CythonX/dB/` | Database helpers |
| `CythonX/fns/` | Shared utilities |
| `CythonX/_misc/` | Decorators and wrappers |
| `plugins/` | Official plugins |
| `assistant/` | Assistant Bot |
| `assistant/manager/` | Group Manager |
| `strings/` | Localization |
| `resources/fonts/` | Font assets |
| `resources/session/` | Session utilities |
| `resources/startup/` | Startup/deployment scripts |
| `requirements.txt` | Main dependencies |
| `.env.sample` | Basic environment template |
| `Dockerfile` | Docker deployment |
| `docker-compose.yml` | Docker Compose |
| `installer.sh` | Installation/setup script |

---

# 🧑‍🔧 Troubleshooting

## `No String Session found`

Make sure:

```env
SESSION=
```

contains a valid Telethon String Session.

---

## `Wrong string session`

Generate a new Session and make sure the complete string is copied without modification.

---

## Database connection errors

Verify the selected backend configuration.

### Redis

```env
REDIS_URI=
REDIS_PASSWORD=
```

### MongoDB

```env
MONGO_URI=
```

### PostgreSQL

```env
DATABASE_URL=
```

If multiple backends are configured, remember that the runtime selects the available backend according to its database initialization logic.

---

## Plugin fails to load

Check the log file:

```text
heartless.log
```

The loader isolates plugin import failures and logs the associated exception.

Also check whether the plugin requires an optional dependency.

---

## Media commands fail

Verify that system dependencies such as:

```text
ffmpeg
mediainfo
git
```

are installed when required by the corresponding feature.

---

## Voice Chat does not start

Check:

```env
VC_SESSION=
VCBOT=true
```

and make sure the required Voice Chat dependency is installed.

---

# 🛠️ Recommended Production Setup

For a long-running deployment, a typical setup is:

```text
Linux VPS
   │
   ├── Python 3.10+
   ├── FFmpeg
   ├── Git
   ├── Redis
   └── Megatron
          │
          ├── Telegram User Session
          ├── Assistant Bot
          ├── Plugins
          └── Persistent Database
```

---

# 📜 License

This project is distributed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

See:

```text
LICENSE
```

for the complete license text.

---

# 🙏 Credits

Megatron is based on the ecosystem and work of several open-source projects.

Special thanks to:

- [Lonami](https://github.com/LonamiWebs/) and the **Telethon** project
- Contributors to the upstream UserBot ecosystem
- Open-source developers whose libraries and services are used throughout the project
- Everyone who has contributed plugins, fixes and improvements
- [T.me/DarkPentester](https://t.me/DarkPentester)

---

# 🤝 Contributing

Contributions are welcome.

A good contribution should:

1. Keep the plugin architecture intact.
2. Avoid hard-coding secrets.
3. Follow the existing asynchronous programming style.
4. Reuse existing helpers where possible.
5. Keep feature-specific database logic inside `CythonX/dB/`.
6. Add localization strings when introducing user-facing text.
7. Avoid unnecessary changes to the core runtime.
8. Document new dependencies.
9. Test the plugin before submitting it.
10. Never include Session strings, cookies, API keys or other credentials in commits.

---

# 📌 Development Guidelines

When adding a new feature:

```text
New Feature
    │
    ├── Command/Event
    │       ↓
    │   plugins/<feature>.py
    │
    ├── Persistent data?
    │       ↓
    │   CythonX/dB/<feature>_db.py
    │
    ├── User-facing text?
    │       ↓
    │   strings/strings/*.yml
    │
    └── Shared functionality?
            ↓
        CythonX/fns/
```

This keeps the project modular and prevents feature-specific logic from leaking into the core runtime.

---

# ⭐ Project Philosophy

Megatron is built around a simple idea:

> **Keep the core small, keep features modular, and make the UserBot extensible.**

The combination of:

```text
Telethon
+
CythonX Core
+
Dynamic Plugins
+
Persistent Database
+
Assistant Bot
+
Optional Addons
```

allows the project to function as a flexible Telegram automation platform rather than a single-purpose bot.

---

# 🚀 Quick Start

For experienced users, the shortest setup path is:

```bash
git clone https://github.com/LoopXS/Megatron.git
cd Megatron

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.sample .env
```

Configure:

```env
API_ID=YOUR_API_ID
API_HASH=YOUR_API_HASH
SESSION=YOUR_TELETHON_SESSION

REDIS_URI=YOUR_REDIS_HOST
REDIS_PASSWORD=YOUR_REDIS_PASSWORD
```

Then:

```bash
python3 -m CythonX
```

Once startup completes, the UserBot loads its configured plugins and becomes ready to receive commands.

---

<p align="center">

<strong>Megatron UserBot</strong><br>
Built with Python & Telethon

</p>
