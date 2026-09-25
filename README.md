# Chaos Cities — Android multiplayer prototype

Every player controls one city. Each city has 320 persistent, distinctly named personality weights, grouped into ten sortable and collapsible categories, plus population, food, wealth, morale, tech, and weirdness. The server grants one Chaos Token every real hour, up to a balance of 30. Players spend currencies on locally generated chaos offers for their own city or attacks on another player's city. Six one-use offers are prepared per player; spent offers are deleted and replaced, and the whole menu rotates every six hours. The local model also chooses a small bonus stat and one trait for each offer, within server limits. Each event shows exact before-and-after changes, including traits and currency spent.

There are two rarer currencies. **Anomaly Shards** sometimes come from strange City AI incidents. **Reality Cores** can arrive from very rare incidents once a city's weirdness ramp has advanced. Bigger events require Shards, and the most extreme events require a Core. Nothing can be bought with real money.

A local Qwen model prepares one-use chaos choices, hero names, and building plans ahead of time. Used entries are removed from their queues and never recycled. The model also chooses from bounded ambient incident types, invents headlines, and speaks as the city in the event log. Effects stay inside server-defined limits; if the model is unavailable, the server uses built-in fallbacks. On the current demo, the city checks for an incident every ten minutes. Free city jobs have been retired.

**Reality drift** opens over 90 real days. A new city starts with low weirdness and gentle events. Its weirdness cap rises gradually, with a progress bar and timer in the app; more extreme events and rarer heroes unlock later. Existing cities keep their previous accumulated weirdness as hidden history while their displayed weirdness follows the new age-based cap.

**Special citizens** can join during City AI incidents. A new city begins with one equipped hero slot plus a reserve roster and can buy up to two more slots. Previously equipped citizens keep their places. Equipped heroes add daily food, wealth, morale, or tech based on their tier: Common, Uncommon, Rare, Epic, Legendary. Rare tiers unlock as the city ages. The SQLite database stores player cities, one-use offers, hero rosters, event history, and consumed title hashes in a persistent Docker volume. It uses WAL mode for concurrent reads.

**Special buildings** begin with one plot; the tech tree and shop allow up to five. They spend Wealth. The local model prepares one-use funny names and descriptions for a pantry (+3 daily Food, 18 Wealth), bazaar (+3 daily Wealth, 22), workshop (+2 daily Tech, 24), theater (+2 daily Morale, 20), and bastion (+8 battle defense, 26). Each type can be built once. Existing structures and plots remain owned.

**Trait battles** sample twenty random traits from both cities. A city's total level never decides the outcome; each side has at least a 35% chance to win. The winner takes up to two points from each of three sampled traits and has a 30% chance to take one of the loser's special citizens when one is available. The local model writes a unique, personality-based event after the server commits the results. Battles cost 8 Wealth, with a four-hour attacker cooldown and a one-hour protection period for the defender. New cities have a one-hour shield, and each attacker can challenge a particular rival twice per 24 hours. A defender can receive at most six hostile events (battles or Chaos Token attacks) in a rolling 24 hours. Both players can inspect the twenty sampled traits and the win chance in the battle log. The rival page displays 30-day win/loss records.

**City trades** let a mayor propose a citizen swap, a Wealth exchange, a gift, or a request. Nothing moves until the addressed mayor accepts. Both citizens' current ownership and both cities' Wealth are checked again at acceptance; transferred citizens enter the destination's reserve roster. Offers expire after 48 hours, and a city may have at most three open offers. A sender may make ten proposals in 24 hours, with at most four to one rival; canceled offers still count. Either side can close an offer before acceptance. The local model writes a funny receipt after a completed trade, while the server records the exact transfer.

**Research and Cash:** Each city receives a small Cash stipend plus 0.02 Cash per point of Wealth each hour. The branch-focused dot tree requires a Tech score, earlier connected research, and Cash. One research project runs at a time, with a timer and progress in the selected dot's tooltip. Its effect starts when the timer finishes. The shop buys faster Cash income, passive Food/Morale/Tech/Wealth growth, hero chairs, and building plots. Passive stat growth begins at 0.001 points per hour and saves fractions until a whole point is reached. The existing daily food and population simulation still runs once per real day.

**City stats:** Food is produced and eaten daily; a shortage shrinks population. Morale above 45 plus food above 35 allows one new citizen per day. Wealth below 10 lowers morale, while wealth at least 100 raises it. Tech adds one daily food for each full 35 points. Equipped heroes add their daily bonuses.

**Citizens and appearance:** Every population point has a named resident with one of 36 races. A local model replaces fallback names in small batches when available. Each race has a preferred enemy and deals double damage in a matching battle duel. Equipped special citizens retain their daily stat bonus and add tier-based battle power and matching trait bonuses; they gain an extra bonus when a fighter from their ally race is present. Battle odds still stay within 35–65%. The Help tab explains the rules. The compact five-stat strip stays visible on every tab. A city can be renamed, and its dark-friendly scenery follows one of 72 gradual landscape and mood paths over the 90-day reality ramp.

## Play this local demo

The server is currently running in Docker Desktop at **http://127.0.0.1:3010/** on this computer and **http://192.168.1.190:3010/** on the home network. The [project board](http://127.0.0.1:3010/board) shows current progress and planned work. The demo city Oddville is already on the local server as an attack target. Home-network access depends on the Windows firewall allowing private-network TCP port 3010.

The Android debug APK is available in the [demo release](https://github.com/lordsali256/chaos-cities/releases/tag/v0.3.2-demo). A local build also writes `ChaosCities-demo.apk` in this folder. To move an existing city, open **My city key & server → Show transfer QR** in the desktop browser, then scan it with the phone camera and open it in Chaos Cities. The QR carries the private city key, so show it only to your own phone. Home-network play uses `http://192.168.1.190:3010`; internet play requires an HTTPS server. The app now times out unreachable servers with a visible error.

The APK is a prototype debug build, not a Play Store release. The QR handoff still needs an interactive on-device check when the Pixel is unlocked. Google login is on hold. This version uses a stable demo signing key for future debug updates. Save your city key before replacing or uninstalling the app.

## Google sign-in (on hold)

Google sign-in is paused at the owner's request. The app currently shows city-key login; the optional OAuth implementation remains in source for later work.

1. In the [Google Auth Platform](https://console.cloud.google.com/auth/overview), create or select a project. Set its branding to **Chaos Cities** and choose an audience that allows your friends to sign in. During testing, add each friend's Google account as a test user if Google requires it.
2. In **Clients**, create a **Web application** client. Add `http://localhost:3010` and `http://127.0.0.1:3010` as Authorized JavaScript origins for desktop tests. Add your eventual `https://your-domain` origin when the public server is ready. Copy the web **client ID**, not the client secret.
3. For the Android APK, also create an **Android** client for package `com.chaoscities.game`. Use SHA-1 `63:45:B7:DB:4E:EB:46:1C:88:E4:13:E7:CF:75:C5:60:F2:2D:A7:33` for this demo APK's signing key. A future release key will have a different fingerprint.
4. Put the web client ID in your local `.env` as `GOOGLE_CLIENT_ID=...`, then restart with `docker compose up -d --build`. The ID may be public, but keep the `.env` file and any client secret out of GitHub. The server verifies each Google ID token and creates one city for each Google account. Its app session lasts 30 days; signing in again renews it.

Google account cities are separate from existing city-key cities in this first version. No existing data is deleted. On Android, enter your server address before selecting Google; a public server must use HTTPS. Google sign-in is not active until the client ID is supplied and tested.

## Host for friends

1. Copy this directory to a machine that runs Docker and can receive internet traffic. Keep the existing free-LLM stack on that same Docker host; the game joins its `free-llm-stack_private` network and calls Ollama locally. If you host the game alone, run `docker network create free-llm-stack_private`; the game still works with built-in event reports when Ollama is unavailable.
2. Copy `.env.example` to `.env`. Set `GAME_DOMAIN` to a domain name whose DNS record points to your host. Set a private `INVITE_CODE` and give that code only to friends. Do not put the code in a public repository. `DAY_SECONDS=86400` means a real economy day and `TOKEN_SECONDS=3600` means one token hour. `AMBIENT_SECONDS` controls City AI incident cadence.
3. Forward public TCP ports 80 and 443 to that machine. Run `docker compose -f compose.yaml -f compose.public.yaml up -d --build` there. Caddy obtains and renews HTTPS certificates automatically. If the host already has a reverse proxy, use `docker compose up -d --build` and connect that proxy to the `chaos-cities_default` Docker network with upstream `server:8000`. A proxy running directly on the host can use `127.0.0.1:3010`.
4. Friends install the APK and enter `https://<your-domain>` plus the invite code. Each installation saves one city key. The host should back up the `chaos-cities_game_data` Docker volume, which contains the SQLite database.

The project does not publish your server automatically. This computer's `.env` binds the demo to its home network. On a public host, use HTTPS and set `PHONE_SERVER_URL` to that HTTPS address so transfer QRs point to it.

## Prototype limits

- Google sign-in offers one city per Google account after configuration. City keys remain as a fallback and still allow additional cities, so a strict one-human-one-city policy is not yet enforced.
- Invite code is shared and reusable. It keeps strangers out of small friend games but is not a full account system.
- This is an Android debug APK. Before a larger public launch, add account recovery, rate limits, moderation tools, notifications, automated backups, and a release signing process.
- Trade offers are asynchronous; both mayors need to visit the app to propose and accept. Chaos Tokens are earned over time and cannot be bought.
- Building and battle rules are prototype balancing values and may change after playtesting.
- The 320 traits use new display names, but existing cities keep their original underlying weights and progress. The previous local database was backed up inside its Docker volume as `chaos-before-tech-tree.db` before this update.

## Build

The server uses `compose.yaml` and keeps its SQLite database in a Docker volume. The Android source is in `mobile/`; the app uses Capacitor. To update the APK after editing `mobile/www`, run `npm install`, `npm run android`, then `docker build -f Dockerfile.android --output type=local,dest=.. .` from `mobile/`. The build runs inside Docker, including a free Android SDK and Gradle.
