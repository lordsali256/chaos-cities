# Chaos Cities project board

Updated 2026-09-25. This is the source of truth for what is playable and what remains. The browser view is at http://127.0.0.1:3010/board.

## Done

- [x] Containerized game server, persistent SQLite data, local Ollama content generation, and Android debug app.
- [x] One city per player, 320 unique traits, ten trait categories, city incident log, and gradual 90-day weirdness ramp.
- [x] Rotating chaos choices, rare Shards and Cores, citizens with Common through Legendary rarity, and unique special buildings.
- [x] One Chaos Token earned each hour, independent from the daily food and population simulation.
- [x] Cash earned hourly from Wealth; passive Food, Morale, Tech, and Wealth growth begins at 0.001 per hour.
- [x] Upgrade shop and 51-dot technology tree with tap details; new cities begin with one hero chair and one building plot.
- [x] Event log shows the ten latest entries in each category.
- [x] City jobs retired; City AI incidents can grant rare currencies.
- [x] Battles sample twenty random traits; either side can win, trait points transfer, and special citizens can change cities.
- [x] Separate app pages and collapsible trait groups.
- [x] Local Hosting homepage restored, with a startup retry for the website database.
- [x] Android build and USB installation tested on the Pixel 11 Pro XL; USB server forwarding works while connected.
- [x] Twelve skyline stages gradually change with city weirdness, from ordinary morning to surreal reality.
- [x] Five optional city specializations with distinct hourly bonuses, free first choice, and a daily switch cooldown.
- [x] City-to-city trade proposals for special citizens and Wealth, with acceptance, decline, cancellation, expiry, and exact results.
- [x] Battle results reveal all twenty sampled traits and the actual win chance.
- [x] Rival screen shows 30-day win/loss records; defenders can review sampled traits in their battle log.
- [x] New cities have a one-hour PvP shield; each attacker is limited to two challenges per rival in 24 hours.
- [x] Chaos Token attacks also respect the one-hour new city shield and give defenders an hour to recover.
- [x] Latest multiplayer APK installed on the Pixel 11 Pro XL; USB server forwarding restored.
- [x] Fixed blank Android launch screen caused by incorrect bundled asset paths; verified the welcome screen on the Pixel.
- [x] Home-network server access and phone QR handoff for an existing city; unreachable servers now report an error instead of waiting indefinitely.
- [x] Public GitHub repository and downloadable Android demo release published; credentials, database files, and signing key excluded.
- [x] Latest Android APK installed on the Pixel over USB; interactive check waits for the phone to be unlocked.
- [x] Compact five-stat strip on every tab, easier research map navigation with inline details, city renaming, and a Getting Started glossary.
- [x] Seventy-two gradual landscape and mood color paths with a meadow starting point.
- [x] Named residents across 36 races; preferred enemies and equipped hero ally bonuses participate in bounded PvP odds.
- [x] Optional Google sign-in flow in web and Android, with server-side token verification and 30-day sessions; awaits the owner's Google OAuth client ID for live testing.
- [x] Research runs on a server-owned timer; the branch-focused dot tree shows countdown and progress in the node tooltip and details.
- [x] Trait groups can be switched off for a flat sortable list, with the choice saved on the device.
- [x] Each city gets a funny daily notice; the local model prepares the next day's notice while a stable fallback covers gaps.
- [x] City page highlights the strongest recent positive event rewards.
- [x] Battles now play a 42-second animated reveal with commentary based on sampled traits; the local model supplies ticker lines when available.
- [x] Android v0.3.1 demo built, installed on the Pixel, and published as a public GitHub prerelease.
- [x] Defenders can receive at most six hostile events in 24 hours across battles and Chaos Token attacks.
- [x] Trade proposals are limited to ten per day and four per rival, including canceled offers.
- [x] Concurrent multiplayer tests cover simultaneous PvP attacks and trade acceptance against a temporary database.
- [x] Edge-case tests confirm an underdog can win, trait totals are conserved, and unauthenticated or unrelated cities cannot use protected trade and battle actions.
- [x] A live local-model story check found an early winner reveal; battle commentary now filters winner and loser spoilers until the reveal.
- [x] Public deployment requires a private invite code and HTTPS game domain; its proxy sends basic security headers.
- [x] SQLite online backup command checks integrity without stopping the game; a private host copy can be kept outside Git.
- [x] City listings and event feeds require a city key; the standalone feed is limited to the signed-in city's events.
- [x] Public sign-ups are capped at five new cities per public IP per day, using hashed addresses; public mode requires a long invite code.
- [x] Repeated temporary-city playtest covers forty PvP battles, citizen transfers, trait conservation, and eight Wealth trades.
- [x] Equipped citizens have stable Guard, Rally, or Focus combat roles; battle records show each citizen's actual contribution.

## Verify and polish

- [ ] Playtest economy costs, tech gates, battle rewards, and citizen theft with multiple real players.
- [ ] Complete an interactive Pixel playtest with the latest multiplayer APK while the phone is unlocked.
- [ ] Scan the city QR with the Pixel camera and verify the complete Android sign-in once the phone reconnects.
- [ ] Tune local AI battle generation for variety and accurate personality descriptions.
- [ ] Google OAuth is on hold at the owner's request; city-key entry remains the visible login.
- [ ] Add richer individual hero abilities and more detailed combat feedback.
- [ ] Add account recovery and further abuse protection before public hosting.

## Planned

- [ ] Deploy to the owner's HTTPS server and invite friends.
- [ ] Further battle art and effects after phone playtesting.

## Decisions still open

- Cash prices and hourly income are first-pass balancing values.
- Tech research costs Cash and requires a Tech score and connected prerequisite nodes.
- Existing player cities keep previously equipped heroes and built buildings, so their slot count may be greater than a new city's starting count.
