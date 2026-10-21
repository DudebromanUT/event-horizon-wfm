# Event Horizon

Pocket workforce management that works with no signal. Erlang C and Erlang A staffing, the
cheapest staffing level once hang-ups have a cost, AI containment and agent-assist what-ifs,
pooling, lending agents between queues, chat concurrency, and a clock for every site that
shows where customer hours land in each site's day across daylight-saving changes.

It's a web app you add to your Home Screen (plain HTML, CSS and JavaScript in `docs/`, no
frameworks), backed by a Python engine (`horizon/`) that the command line, Pythonista and Claude
can use. The two engines are checked against each other on every push, so they can't disagree.

Forecasting and scheduling come next (see [Roadmap](#roadmap)).

## On your phone

**Host it** (once) with GitHub Pages: Settings → Pages → Build and deployment → Deploy from a
branch → `main`, folder `/docs` → Save. On a free GitHub plan the repository has to be public; the
code holds no personal data, because your sites, hours and costs live only on your devices. The
app is then at `https://dudebromanut.github.io/event-horizon-wfm/`. (A host that can publish a private
repository, such as Cloudflare or Netlify, also works: no build command, publish directory `docs`.)

**Install it.** Open the address in Safari, tap Share → Add to Home Screen (keep *Open as Web
App* on), open the new Horizon icon once while online, and wait for **Offline ready** at the
top. From then on it opens with no signal. When a new version is pushed, a banner offers
**Update**.

**Your sites.** The app starts with example sites. Put in your own under Sites → Edit sites,
or open a **setup link** (`…/#setup=…`), which loads a whole set of sites in one tap. Edit sites
→ Copy setup link makes one from your current sites, to set up another phone. Everything you
enter stays in that browser on that device.

## The screens

- **Calc**: the agents you need for one interval. Erlang A when you give an average caller
  patience, Erlang C when you leave it blank. The chart is the service-level cliff around the
  answer; tap a bar for its numbers. Add shrinkage and costs for FTE, cost per interval, and the
  cheapest staffing level once hang-ups have a cost.
- **What-if**: AI containment and agent assist, pooling queues, lending agents from one queue to
  another, chat concurrency.
- **Sites**: each site's local time, whether it's open, the clock changes in the next six weeks,
  and where 8:00 New York and 8:00 London land in each site's day before and after each change.

## The Python engine

```
python3 -m horizon calc 100 5:00 --patience 2:00 --max-abandon 5 --shrinkage 35 --cost 28
python3 -m horizon calc 60 4:00 --patience 1:30 --cost 28 --abandon-cost 75
python3 -m horizon contain 100 5:00 --contained 20 --aht-change 10
python3 -m horizon pool 120@5:30 80@5:30 40@5:30
python3 -m horizon move --from "Customer service" 100@5:00 22 --to Fraud 40@7:00 9 --agents 2 --patience 3:00
python3 -m horizon chat 60 --aht 1=6:00 2=8:00 3=14:00
python3 -m horizon sites --at 2026-11-04T13:00
```

Or from Python: `from horizon import required_agents; required_agents(100, 300, patience=120)`.
The engine also has models with no screen yet: async messaging backlog, SMS batch limits,
outbound hours and attempt-cap reach (`horizon/channels.py`).

**Pythonista, as a lab.** The engine is pure Python 3.10 with no dependencies, so it runs in
Pythonista too. `horizon_app.py` is a basic Pythonista front end, and
`pythonista/install_event_horizon.py` installs or updates the repository on the phone. It needs no
token while the repository is public; for a private one it asks once for a read-only token and
keeps it in the iOS keychain. To load your sites, copy your setup link and tap **Paste setup link**
on the app's Sites tab (iOS may ask to allow the paste). It saves them as `config/operation.json`,
which updates leave alone.

**Siri.** "Hey Siri, Staffing" asks three questions out loud (calls per half hour, handle time,
goal) and says how many agents you need, with no signal. It answers by voice in plain words:
"six hundred", "six and a half minutes", "eighty twenty". It reads back what it heard, so a
misheard number is easy to spot, and adds the staffing that keeps occupancy under your sites'
limit when that's higher. There is no language model in it; `staffing_shortcut.py` reads the
answers and the engine does the math. Build the shortcut once in the Shortcuts app, after the
Pythonista install:

1. New shortcut named **Staffing**.
2. **Ask for Input**, Number, "How many calls per half hour?", then **Set Variable** `Calls`.
3. **Ask for Input**, Text, "Handle time?", then **Set Variable** `Handle time`.
4. **Ask for Input**, Text, "Goal? For example, 80 20." (default answer `80/20`), then
   **Set Variable** `Goal`.
5. **Run Pythonista Script**: script `event-horizon/staffing_shortcut.py`, **Run in Pythonista**
   off, and `Calls`, `Handle time` and `Goal` as the arguments (three items, or one line as
   `Calls | Handle time | Goal`).
6. **Show Result** with the script's result. Siri reads it aloud.

## Tests

| Command | What it checks |
|---|---|
| `python3 run_tests.py` | The Python engine: Erlang A against a brute-force calculation and a call simulation, Erlang C against exact fractions, the built-in daylight-saving rules against the system time zone database for 2008–2036, the reports and command line, the Pythonista app against a strict stand-in for its `ui` module, the installer, and how the Siri script reads dictated answers. |
| `python3 scripts/golden.py --check` | `tests/web/golden.json`, Python's answers for a fixed set of cases, is up to date. |
| `node --test tests/web/engine.test.mjs` | The web app's JavaScript gives those same answers: staffing, money, what-ifs, every time zone offset and change, opening hours, and whole Sites screens. |
| `python3 scripts/build.py --check` | The generated `docs/sw.js` and `docs/app/defaults.js` are up to date. |
| `node tests/browser/clickthrough.cjs` | Every screen in Chromium at iPhone size with a fixed clock, then a reload with the network off. Needs `npm install --no-save playwright@1.56.1`. |

GitHub Actions runs all of them on every push, the Python ones on 3.10 (Pythonista's version)
and 3.13. After changing either engine, run `python3 scripts/golden.py` and commit the new
`golden.json`; after changing anything in `docs/`, run `python3 scripts/build.py` so the offline
copy updates.

## The models, and what they assume

- **Service level** is calls answered within the target ÷ calls *offered*, so hang-ups count
  against it.
- **Erlang A** (M/M/N+M) needs average caller **patience**. Estimate it from interval data as
  total seconds everyone waited (answered and abandoned) ÷ number of abandons.
- **Pair service level with caps.** With hang-ups in the model, a big queue can "meet" 80/20 by
  letting people abandon: 1,000 Erlangs at 3:00 patience hits 80/20 with 936 agents, 6.5%
  abandoning and 99.9% occupancy. The app always shows a hang-up limit and an occupancy limit.
- **Cheapest staffing** adds agent cost to the cost of hang-ups (a lost sale, a missed payment,
  a repeat call) and finds the level where the total is lowest.
- **Containment** savings are agents removed; the money lands at whichever site loses the hours.
- **Pooling** assumes cross-trained agents handle each call as fast as the specialists did.
- **Chat** treats each agent as `concurrency` seats, using the handle time measured at that
  concurrency.
- **Async messaging** (WhatsApp, Instagram, Messenger, 1:1 SMS) is workload against capacity with
  a backlog, not an Erlang queue.

## What's where

| Path | What it is |
|---|---|
| `docs/` | The web app. `app/engine.js` and `app/clock.js` are the JavaScript engine; `app/calc.js`, `whatif.js` and `sites.js` are the screens; `sw.js` is generated. |
| `horizon/` | The Python engine: `erlang.py`, `economics.py`, `whatif.py`, `channels.py`, `clock.py`, `config.py`, `report.py`, and `voice.py` for the Siri script (`staffing_shortcut.py`). |
| `config/operation.example.json` | The example sites, which also become the web app's starting sites. Your own go in `config/operation.json` (ignored by git), which the Pythonista app writes from a setup link. |
| `scripts/` | `build.py` (generated web files), `golden.py` (cross-check cases), `icons.cjs` (app icons). |
| `tests/` | Python tests, `web/` cross-checks, `browser/` click-through. |

## Roadmap

1. **Forecast**: forecasting on the phone (weekly seasonality, intraday curves, event
   multipliers for paydays, due dates and tax season), plus TimesFM 2.5 in GitHub Actions for
   P10–P90 ranges, cached on the phone for offline use.
2. **Schedule**: shift patterns built against each site's staffing needs in local time under your
   labor rules, as what-ifs alongside your workforce management system.
3. **Claude**: a Skill that bundles the engine so Claude runs the math instead of guessing it.
