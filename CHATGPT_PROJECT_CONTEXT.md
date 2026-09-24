# Chaos Cities: project context

This file is a portable summary for a ChatGPT Project. The development conversation itself is a Codex task and cannot currently be moved into a ChatGPT Project's chat history.

## Vision

Each player owns one living city with 320 unique personality traits. A local LLM writes the city's strange incidents, rotating chaos choices, special citizens, building names, and PvP stories. The game should be funny and increasingly absurd over months rather than bizarre from the first minute. Friends will eventually play through an Android app against a privately hosted public server.

## Current playable prototype

- Docker server on the owner's computer at http://127.0.0.1:3010/ with a persistent SQLite database and local Ollama content generator.
- Android debug APK in the project folder. Public play needs an HTTPS server and invite configuration.
- One Chaos Token each hour; Shards and Cores come from City AI incidents.
- Cash earned hourly from Wealth; passive city growth starts at 0.001 per hour, with a shop and branching Tech tree for upgrades.
- Heroes in Common, Uncommon, Rare, Epic, and Legendary tiers. New cities start with one equipped slot; more can be purchased. Existing cities retain previously equipped slots.
- Funny AI-named special buildings. New cities start with one plot; more can be purchased. Existing cities retain built structures.
- PvP battles randomly sample 20 traits and five named residents from each city, keep winning odds between 35% and 65%, and generate a unique local-AI event. Preferred enemy races deal double damage. Winners take trait points and may take a special citizen.
- Tabbed game pages with compact stats, sortable and collapsible trait groups, City AI event log, glossary, and a 90-day weirdness ramp across 72 gradual color paths.
- Google sign-in is coded for browser and Android but awaits the owner's Google OAuth client ID and device test. City keys remain available.
- A project board is available at http://127.0.0.1:3010/board and in PROJECT_BOARD.md.

## Earlier decisions

- Player-entered prompts and free city jobs were removed. Players choose prepared chaos events and interact through the economy, research, and PvP.
- Local model content is bounded by server-controlled mechanics. Secrets and city keys are not sent to hosted model providers.
- Preserve existing cities and the SQLite volume through updates. A backup made before the tech-tree migration is in the game Docker volume as `/data/chaos-before-tech-tree.db`.
- Keep tools free where practical; the game runs in Docker Desktop and uses local AI.

## Next work

See PROJECT_BOARD.md for the live status. Planned work includes public HTTPS deployment, Google sign-in configuration, phone testing, richer hero abilities, and battle/economy balancing.

## Project files

- `server/main.py`: game rules and API
- `mobile/www/app-v2.js`: app interface
- `mobile/www/extra.css`: app styling
- `compose.yaml`: Docker server
- `README.md`: setup and hosting instructions
- `PROJECT_BOARD.md`: current board

Never upload `.env`, city keys, or database backups into a shared ChatGPT Project.
