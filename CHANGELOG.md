# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.61.0] - 2026-10-25

A sweep through the findings of two code review passes. Most of these are long-standing
bugs rather than regressions.

### Fixed
- Entering a result with any capitalisation, such as `!result Radiant`, updated the scoreboard correctly but matched no bets, so every winning bettor silently lost their stake and winnings.
- A newly created database was unusable: the metadata row was written without the `name` field every query filters on, so the first `!start`, `!result` or `!season` failed, and `update_metadata` duplicated the row rather than updating it. Existing databases were unaffected.
- `!shuffle` charged 500 RBUCKS, and persisted the charge, before working out the new teams - and that can fail whenever the signups have changed, which an admin using `!rm` during the transfer window is enough to cause. The player was left out of pocket with the teams untouched. The charge now happens once there is a shuffle to hand over.
- Two `!shuffle` commands in quick succession both read the same balance and both wrote it decremented once, giving two shuffles for the price of one.
- An accepted duel that no admin ever started stayed in the challenge list for the lifetime of the process, leaving its challenger unable to issue another and with no explanation.
- The expiry announcement was sent before the challenge was removed from the list, so a send that failed a day later left it stuck there permanently.
- A and B could each hold a live duel against the other. `!challenge` now spots the reverse pairing and points you at `!accept`.
- `!challenge` sent no message at all - appearing to do nothing - when the opponent of your existing challenge had since left the guild.
- Rejecting an opponent far below your MMR played the taunt and left the bot sitting in the voice channel indefinitely.
- `reset` raised when a game was abandoned before teams were balanced, leaving the game marked in progress and the bot unable to start or stop another until it was restarted, with every `!stop` refunding bets again on the way to the same error.
- A second `!start` issued while the first was still setting up could begin a second game, because `max_concurrency` releases as soon as the command returns rather than when the work is done.
- A bettor deregistered between placing a bet and the result aborted the payout part way through and skipped the reset, leaving a re-issued `!result` free to pay everyone a second time.
- `!balance` reported too few signups and then carried on into a guaranteed failure.
- Stale signups were never reaped: `cleanup_inactive_players` captured the current game once before its loop, when there is almost never a game in progress.
- Renaming yourself in Discord had consequences all over the place, as several checks compared a stored name against a current one. A renamed player could not be selected from more than ten signups, could not `!commend` or `!report`, could not `!shuffle`, was not moved into their team's voice channel, was silently skipped by a transfer refund, and could have a duel bet or payout misrouted. These all settle on Discord ids now.
- A refund that could not find everyone no longer announces that all transactions were refunded.
- `voice_client_disconnect` polled forever when there was no voice client to disconnect from, leaving an immortal task behind every `!reset`, `!challenge` and `!reject` where nobody was in voice.
- Background tasks that are never awaited are now kept referenced until they finish, rather than left for the garbage collector to claim mid-execution, and what they raise is logged rather than discarded.
- Seasons ended one game early.
- `!summon` raised `IndexError` instead of reporting a missing IHL role.
- `!recalibrate` accepted any MMR, bypassing the bounds `!register` enforces, and gave an unhelpful error for a non-numeric one.
- Challenge odds for a player missing from the database raised `RuntimeError: No active exception to re-raise`.
- `Player` could not be put in a set or used as a dict key.
- The message rejecting a duel against a much weaker player claimed your opponent had to be "within" 4000 MMR of yours, describing a symmetric rule. Challenging far above your own MMR is allowed and always was; only picking on someone far below it is not.

### Changed
- Team balancing generates the 126 valid matchups directly instead of building 31,626 and discarding the 99.6% that share a player. Same matchups, 36.3ms down to 0.37ms.
- Players are moved into and out of the team voice channels concurrently rather than one at a time, so starting and resetting a game no longer waits out ten sequential round trips to Discord.
- A shuffle that draws the teams you already have redraws without repeating the "Balancing teams..." and MMR messages, and gives up after ten attempts rather than looping until the dice oblige.
- `get_all` uses TinyDB's public API rather than reaching into `_read_table`.

## [1.60.1] - 2026-10-25
### Changed
- Bumped `aiohttp`, `multidict`, `idna`, `pygments` and `pytest`.

### Fixed
- The SBOM step of the publish workflow asked for the image under a tag that is never published, failing the workflow after the image had already been pushed. It now uses the digest from the build step.

## [1.60.0] - 2026-10-25
### Changed
- DNS failures are now logged as a single line naming the host that could not be resolved, rather than a full traceback. discord.py logs one of these per reconnect attempt, and an outage would otherwise bury every other log line.
- Logging is now set up before the bot is built, so startup is logged too.

## [1.59.1] - 2026-08-31
### Changed
- Bumped discordpy version due to introduction of DAVE protocol.

## [1.59.0] - 2025-12-30
### Changed
- Switched to using TOML config

## [1.58.0] - 2025-12-14
### Added
- Added Github CI/CD workflow
- Added code coverage tracking with `codecov`

### Changed
- Switched to using `ruff`

## [1.57.0] - 2025-09-01

### Added
- Added `!clear` command to permit an admin to remove everyone from the current signups.

### Changed
- Moving discord members from channels is now handled in a separate async task. This should hopefully result in a snappier start and end to a game.

## [1.56.2] - 2025-08-19

### Changed
- Bumped discord.py version to fix WebSocket 4006 error.

## [1.56.1] - 2024-11-24

### Changed
- Fixed bug where calling a command that invoked the `play_sound` function caused an `AttributeError` to be thrown.
- Fixed bug where if an admin executed the  `!stop` command while the game was during the transfer/betting phase, the bot would not reset to a clean state.
- Fixed bug where bets were not being formatted as integers when displaying bet results.

## [1.56.0] - 2024-10-08

### Added
- Added challenge mode. Players can now challenge each other to 1v1 duels.
- Bets now include a price. By default this is 2.0 for classic games and can vary between 1.01 and 101 for challenges.

### Changed
- Replaced database protocol with ABC.
- Simplified database API.
- Replaced all uses of TypedDict with Dataclass for consistency.
- Game state is now stored in the GameStore.

## [1.55.3] - 2024-08-26

### Added
- Added global exception handler to log uncaught exceptions.

### Changed
- Cleaned up Dockerfile, stopped copying in extraneous files.

## [1.55.2] - 2024-08-25

### Changed
- Command typo's will now be purged!

## [1.55.1] - 2024-08-24

### Changed
- Fixed bug in `play_sound` function which would, on occasion, sit forking `ffmpeg` forever more. 
- Fixed bug where game would hang if more than 10 players signed up and players would have to be benched.

## [1.55.0] - 2024-08-07

### Changed
- Betting window shortened to 1 minute.
- Player transfer window shortened to 1 minute.

## [1.54.1] - 2024-05-25

### Changed
- Fixed deregister command, was attempting to obtain Player record from database via name instead of id.
- Reverted back to players being moved channels after Betting phase.

## [1.54.0] - 2024-05-22

### Changed
- Betting window shortened from 3 to 2 minutes.
- The `!who` command no longer attempts to print current signups if there are none.
- Players will be moved channels after the Transfer phase instead of after the Betting phase.

## [1.53.0] - 2024-04-09

### Added
- Added a `!recalibrate` command to allow admins to change a player's MMR on the fly.

## [1.52.3] - 2024-04-02

### Changed
- Fixed bug in `!signup` command where the first call would not send a message to be displayed in Discord.

## [1.52.2] - 2024-04-01

### Changed
- Fixed bug in on_presence_update callback not removing a player from signups.

## [1.52.1] - 2024-04-01

### Changed
- Fixed bug in lobby cleanup routine.

## [1.52.0] - 2024-03-30

### Added
- Added a cleanup routine to the lobby that runs every hour to check for players who have been signed up too long.

## [1.51.3] - 2024-03-18

### Changed
- Fixed bug where audio played at end of game would terminate prematurely.

## [1.51.2] - 2024-02-09

### Changed
- Bot will now disconnect from voice channel when a game has ended.

## [1.51.1] - 2024-01-25

### Changed
- Bet phase has been reduced from 5 mins to 3 mins.

## [1.51.0] - 2024-01-25

### Changed
- Changed the order in which events occur during the start of a game. Players are kept in the same voice channel until after the betting phase is over.

## [1.50.1] - 2024-01-24

### Added
- Added missing pynacl dependency

## [1.50.0] - 2024-01-22

### Added
- Bot now plays sounds when some commands are called.
- Now logging discord.py output to separate log file.
- Added ffmpeg requirement in Dockerfile in order to play mp3 files.

### Changed
- When shuffling, now picks from the top 20 team combinations based on mmr instead of 5.
- Can now use the !bet command and specify amount as either first or second argument.

## [1.49.0] - 2024-01-03

### Changed
- Use discord ID for identifying users instead of display name.

## [1.48.0] - 2024-01-02

### Changed
- Bumped version for aiohttp and dpytest.

## [1.47.0]- 2023-11-26

### Changed
- Switched to using pyproject.toml

## [1.46.0] - 2023-11-25

### Changed
- Improved logging by using structlog.

## [1.45.1] - 2023-04-14

### Added
- Added upper limit to MMR submitted when registering for IHL.

## [1.45.0] - 2023-04-13

### Added
- Added !season command to show info on current IHL season.
- Added IHL section to config for tracking game count.

## [1.44.2] - 2023-04-13

### Changed
- Fixed bug where all rbucks were deducted on a bet loss.
- Fixed bug where betting on both sides resulted in too many rbucks being deducted.

## [1.44.1] - 2023-03-14

### Changed
- Fixed bug that happpened when attempting to add a new player to the database.

## [1.44.0] - 2023-03-09

### Added
- Added callback that cleans up misspelt commands from a text channel.

### Changed
- Simplified Database API.

## [1.43.0] - 2023-02-22

### Added
- Added a new set of dpytest based tests for testing commands.

### Changed
- discordpy upgraded to v2.0.
- Fixed a bug in ready check falsely reporting all players were ready.
- Fixed a bug in commend/report where the player being commended/reported and the player issuing the command were in the wrong order.
- Fixed a bug where calling !bet could have resulted in the bet not being registered.

## [1.42.5] - 2023-02-06

### Changed
- Side validation now working correctly.

## [1.42.4] - 2023-02-01

### Added
- Log message for the combined MMR of each team.

### Changed
- Should now send a message to Discord channel when a player attempts to report themselves.

## [1.42.3] - 2023-01-31

### Changed
- Stopped players being able to report/commend themselves.

## [1.42.2] - 2023-01-30

### Changed
- Removed call to Channels.set_teams function that no longer exists.

## [1.42.1] - 2023-01-29

### Changed
- Fixed bug where players were not moved Discord channels before and after game.

## [1.42.0] - 2023-01-29

### Added
- Added a commend/report system and an associated behaviour score for each player. Commend players with !commend {player_name} and report players with !report {player_name} {reason}.

### Changed
- Refactored how we manage game state, this should make cleanup way easier and we now have less to keep track of.
- Refactored various Cogs including Core and Lobby (previously PreGame).

### Removed
- Removed a load of awful tests, more to come at some point, maybe...
- Removed !reset command, just use !stop if you wish to abort the game.

## [1.41.1] - 2022-11-07

### Changed
- Fixed some member variables not being initialized on instantiating class.

## [1.40.0] - 2022-11-03

### Changed
- Tidied up type hints.
- Fixed broken tests.
- Now remove old cogs and replace with new cogs when we reset state.

## [1.40.2] - 2022-10-25

### Changed
- Fixed bug where shuffling could result in same teams.

## [1.40.1] - 2022-08-30

### Changed
- Fixed bug in setting streaks in TinyDB wrapper.

## [1.40] - 2022-08-30

### Added
- Now using TinyDB to store data instead of DynamoDB.

### Removed
- Removed all dependencies on AWS DynamoDB.

## [1.39.2] - 2022-08-28

### Changed
- Fixed bug where Player transfer and Betting windows remained open after a !stop command had been issued.

## [1.39.1] - 2022-08-21

### Changed
- Fixed bug where scoreboard if was < 2000 chars, we returned a tuple of characters instead of tuple of strings.

## [1.39] - 2022-05-27

### Removed
- Functionality to protect RBEEZAY from encountering complete melts  on his team.

## [1.38.1] - 2022-05-25

### Changed
- Only players that signed up to play can shuffle.

## [1.38] - 2022-05-25

### Added
- Added a !shuffle command which will shuffle the teams at the cost of 500 RBUCKS.

## [1.37] - 2022-05-18

### Changed
- Players who are about to participate in a game can now bet.
- Increased betting window from 2 minutes to 5 minutes.

## [1.36.1] - 2022-05-12

### Changed
- Winners of bets should now receive the expected number of RBUCKS.

## [1.36] - 2022-05-12

### Added
- Added RBUCKS where players can bet on the outcome of an IHL game.

## [1.35.1] - 2022-05-11

### Changed
- No longer able to accidentally issue multiple calls to !start/!stop/!result.

## [1.35] - 2022-05-11

### Changed
- Simplified code used to balance teams, now always balances using adjusted MMR.

## [1.34] - 2022-05-04

### Changed
- Users can only signup/signout once every 30s in order to prevent spamming OneHead post-game.
- Users cannot signup/signout while a game is in progress.

## [1.33] - 2022-05-04

### Added
- Members signed up to play a game are automatically signed out if they move/are moved to the AFK channel.

## [1.32] - 2022-04-14

### Changed
- DynamoDB field names can't contain spaces, added '_' into streak fields.

## [1.31] - 2022-04-14

### Added
- Added a loss streak field that keeps track of the current loss streak.

### Changed
- Renamed 'streak' field to 'win streak'.
- Scoreboard now split over multiple messages if it exceeds the max message length enforced by Discord.

## [1.30] - 2022-04-06

### Added
- Added a streak field to the scoreboard that keeps track of the current win streak.

## [1.29] - 2022-04-03

### Changed
- A w/l results in a +/- 50 rating score (previously this was 25).

## [1.28] - 2022-03-06

### Changed
- The register command only accepts an MMR greater or equal to 1000.

## [1.26] - 2022-02-12

### Changed
- Python 3 cosmetic changes: f-strings, type hinting etc.

## [1.25] - 2022-02-09

### Changed
- Tidied up Dockerfile.

## [1.24] - 2022-02-08

### Changed
- Updated requirements.txt, removed mock dependency and bumped Python version requirement.

## [1.23] - 2021-03-19

### Added
- Added !mh command to provide other players with inspirational mental health quotes.
- Added !mmr command to show the MMR that is used internally for balancing teams.

## [1.22] - 2021-02-11

### Changed
- !summon command now mentions by role instead of by user to comply with Discord 1.5 changes and the addition of 'intents'.
- !signup command output tidied up.

## [1.21] - 2021-02-08

### Changed
- Fixed bug where stale reference to OneHeadPreGame object was present in the OneHeadBalance object. This was causing
  players who were not signed up to be present in the lineups produced when a game was started.

## [1.20] - 2021-02-07

### Changed
- Tidying up of imports and file names.
- Fixed bug with multiple instances of OneHead objects existing, all objects are now cogs and referenced through the 
  global commands.Bot object.

## [1.19] - 2020-05-21

### Added
- Added config.json and config_example.json to enable the user to configure their bot.
- Updated README.md with information on requirements, features and config.json

### Removed
- Removed .env file and python-dotenv dependency.

## [1.18] - 2020-05-14

### Added
- Added /src directory and moved onehead_*.py file there.
- Added supporting docstrings/comments throughout.

### Changed
- Updated README.MD to reflect changes to docker build command.
- Refactored code in OneHeadBalance.
- Moved OneHeadChannels into separate file for consistency.

### Removed
- Removed need for OAUTH key during build process.
- Removed code duplication in OneHeadCore/OneHeadChannels.
- Removed need to explicitly reference OneHead version number when calling pip install inside Dockerfile.


## [1.17] - 2020-05-11

### Changed
- Switched to using a CHANGELOG.md file with a full changelog rather than only showing the most recent change(s).
- The !version command will now provide a link to CHANGELOG.md

## [1.16] - 2020-05-10
### Added
- All user commands now require IHL discord role.
### Changed
- Fixed the 'deregister' command, can now remove a player from the IHL database by typing !deregister \<name\>.


## [1.15] - 2020-05-05
### Changed
- Balancing teams now factors in both IHL rating and MMR. This is done by adding the difference between your IHL rating 
    and baseline rating (1500) to your MMR.
    
    e.g. IHL Rating = 1900 and MMR = 5000. Adjusted rating = 5000 + 400 == 5400.

## [1.14] - 2020-04-29
### Changed
- If there are more than 10 signups, players will be randomly selected to be placed on the bench. This will mean that
    they will not be able to play.
    
## [1.13] - 2020-04-29
### Changed
- Fixed bug when performing check to see if IHL Discord Channels already exist. This stopped players from being 
    moved channel and also resulted in duplicate channels.

## [1.12] - 2020-04-28
### Removed
- IHL Channels are no longer deleted upon stopping a game.

## [1.11] - 2020-04-20

### Added
- Patch note summary now available when using the !version command.
### Changed
- Picks and Nominations during a CM game are now case insensitive.
- Time to pick during a CM game has been increased from 20s to 30s.

## [1.10] - 2020-04-15

### Added
- Added Captain's Mode. Can be initiated by typing '!start cm'.
    Captains are nominated using the '!nominate' command and picks are made by the nominated captains using the '!pick'
    command.

## [1.0] - 2020-04-12

### Added
- Added version.py for storing version information.
- Added version command which displays the current version of OneHead.
- Added a remove command which allows an IHL Admin to remove a player from the signup pool.

### Changed
- Signups now reset after a game has finished.
