# MIoT Vacuum Rooms

Add-on integration for the **official Xiaomi Home integration** in Home Assistant. Some robot vacuums only show up there as raw MIoT entities (`notify.…_a_17_1`, `sensor.…_p_17_13`). This integration builds a usable interface on top of them, without the Xiaomi cloud map or extra credentials:

- **Clean rooms by name**, also several rooms in a chosen order
- **Own vacuum entity** with a safe start button, fan speed and **cleaning by Home Assistant areas** (`vacuum.clean_area`)
- **Select entities** for cleaning mode, suction power, water level, passes and route preference
- **One button per room**
- **Learn rooms**: briefly start a room in the app, and the integration picks up its room ID

It does not replace a map. The room IDs come from the robot, not from a map file (see Limitations).

The integration's UI is available in English and German.

## Status

| Part | State |
|---|---|
| Commands and values | Confirmed on a real **Jonr P20 Pro** (`xtl.vacuum.xm2216`) via the Xiaomi Home integration |
| Room start `[3, "[ID]"]`, Customised mode | Confirmed on the device (per-room settings from the app apply) |
| Room start with global settings (switch "Use room settings from the app" off) | **Untested** on the device |
| Integration code | Tested in a Home Assistant test environment, **not yet installed in a live instance** |
| Whole-floor service | **Untested**, command derived from app behaviour |
| Start verification with retry | Tested in the test environment only, **not tested on the device** (retry interval, deep-sleep behaviour) |
| Other models | Unverified. They only work if they use the same MIoT specification (service 17) with the same numbers and values |

## Requirements

- Home Assistant **2026.3.0** or later (first version with area cleaning for vacuums)
- Official Xiaomi Home integration set up with the robot vacuum
- The device has entities with these suffixes (service 17):
  - Actions (`notify`): `a_17_1`, `a_17_26`, `a_17_27`, `a_17_28`, `a_17_46`, `a_17_50`
  - Sensors (`sensor`): `p_17_9`, `p_17_10`, `p_17_13`, `p_17_14`, `p_17_34`, `p_17_65`
- Existing setups pick up sensors added in later versions (such as `p_17_9`) automatically on the next start.
- If one of them is missing, the setup names it.

## Installation

1. HACS → Integrations → menu → *Custom repositories* → enter the repository URL, category *Integration*.
2. Download, then restart Home Assistant.
3. Settings → Devices & services → *Add integration* → "MIoT Vacuum Rooms" → select the vacuum (`vacuum.…`).

Repository: https://github.com/coding-pagro/ha-miot-vacuum-rooms

## Learning rooms

The robot's room IDs are not the numbers shown on the app map. Example from a Jonr P20 Pro: a room numbered 7 on the map had ID 5 on the robot.

**Option A, dialog:** Settings → Devices & services → MIoT Vacuum Rooms → *Configure* → **Learn a room**. Enter a name (and, if needed, the wait time, default 90 s) and continue. When the dialog asks you to, start exactly that room in the app, wait a moment and cancel the run in the app. The dialog then shows "Learned *name* = ID *n*"; the room button is created. On a timeout or when several rooms were started, the dialog shows the reason and lets you try again; nothing is stored in that case.

**Option B, action:** Developer tools → Actions → `miot_vacuum_rooms.learn_room`, enter a name, run it, then start exactly that room in the app and cancel the run. Same logic as the dialog, usable from automations and scripts.

- Only a *new* change of the sensor counts. The previous run must have finished (sensor empty).
- Starting several rooms at once is rejected.
- A new name for a known ID replaces the old name.

**Option C, text:** Integration → *Configure* → Edit rooms and behaviour, one room per line as `Name=ID`.

Example:

```
Kitchen=2
Living room=7
Hallway=3
Bathroom=5
Bedroom=8
```

## Cleaning rooms

```yaml
action: miot_vacuum_rooms.clean_rooms
data:
  rooms:
    - Kitchen
    - Hallway
```

- The order of the names is the cleaning order.
- By default it only starts when the robot is on its dock (`docked`) **and no job is open** (job status `p_17_9` is `Idle`). Starting in the middle of a job made the robot lose its orientation. The robot also reports `docked` in the middle of a job, when it returns to wash the mop (job status `Area Pause`), and a robot with a paused job ignores new room starts. The condition can be switched off in the options.
- The start is verified: the cloud also confirms commands the robot never runs (e.g. during mop washing or the battery cycle). After sending, the integration waits up to 25 s until the job status (`p_17_9`) is no longer `Idle` and, for rooms, `p_17_34` lists the requested room IDs. Otherwise it sends again, up to 3 attempts, and then raises an error. Without the two sensors it sends once as before. Not yet tested on the device.

The switch **"Use room settings from the app"** (on the integration's device, default on, survives restarts) decides which settings apply:

| Switch | Behaviour |
|---|---|
| **On** (default) | The service switches to **Customised** mode and waits up to 10 seconds for confirmation. In this mode the **per-room settings from the app** apply (suction power, water level, passes per room). The global select entities have no effect on the run. The mode stays on Customised afterwards. |
| **Off** | The mode is **not** changed. The **global** cleaning mode, suction power, water level and passes apply to the selected rooms. If the global mode is *Customised*, the start is refused: pick another cleaning mode first. **Untested on the device:** only the room start in Customised mode is confirmed so far. |

The switch applies to everything that cleans rooms: `clean_rooms`, the room buttons, the start button of the vacuum entity and `vacuum.clean_area`.

Every learned room also gets a "Clean …" button that calls the same service for that one room.

## Vacuum entity

The integration adds its own vacuum entity (`vacuum.<device>`) to its device. It mirrors the state of the Xiaomi vacuum and is unavailable when that one is. One difference: when the robot is on its dock but a job is open, it does not show Docked. With a paused job (job status ends in `Pause`, e.g. after "return to base" during a run, or while the mop is washed in the middle of a job) it shows **Paused**, with a running job (e.g. washing the mop before it drives off) **Cleaning**. While the robot or its station reports an error code it shows **Error** (see Problems and error codes). The Xiaomi entity starts without a room selection, with whatever global mode is set, and even in the middle of a job. This entity does not:

| Button / action | What happens |
|---|---|
| Start | Robot **paused** away from the dock: resumes the paused run. Job **paused on the dock** (after "return to base" during a run, or while the mop is washed): refuses, resume or end the job in the app (resuming from the dock is untested). Otherwise: cleans **all learned rooms** like `clean_rooms` (same dock check). Without learned rooms it refuses. It never starts a run without a room selection. |
| Pause, stop, return to base | Passed through to the Xiaomi vacuum. **Stop** on the Jonr P20 Pro does **not** end a paused job (tested); end it in the app. |
| Fan speed | Global suction power, see below. Hidden while the cleaning mode is *Customised*. |
| `vacuum.clean_area` | Cleans the rooms mapped to the given areas, in the given order. |

**Area cleaning:** open the vacuum entity → settings → map Home Assistant areas to the learned rooms. Then areas work in `vacuum.clean_area`, for example from the vacuum card or a voice assistant:

```yaml
action: vacuum.clean_area
target:
  entity_id: vacuum.my_vacuum
data:
  cleaning_area_id:
    - kitchen
    - hallway
```

If the set of room IDs changes after you mapped the areas (learning a new room, forgetting one, or editing the IDs in the options), Home Assistant shows a repair notice. Open it and check the mapping again. Renaming a room keeps the mapping, because it is stored by room ID.

**Fan speed:** there are two suction power values. The **global** one (shown and set by the fan speed of this entity and by the "Suction power" select) and the **per-room** one from the app, which Home Assistant can neither read nor set. In *Customised* mode the robot uses the per-room value, so the fan speed of this entity only matters for room cleaning when **"Use room settings from the app" is off** (see Cleaning rooms). With the switch on, it has no effect on room cleaning.

So while the cleaning mode is *Customised*, the vacuum entity **hides its fan speed** (the control disappears from the dialog and `vacuum.set_fan_speed` is refused). It comes back as soon as another cleaning mode is selected. With the switch on, every room start sets *Customised*, so in practice the fan speed only shows when you deliberately pick another mode, which is exactly when it has an effect. The "Suction power" select stays available to set the global value at any time.

**Cleaning mode:** the vacuum dialog has no field for it, so the entity reports it as the attribute `cleaning_mode` (shown translated under *Attributes* in the dialog). To see and change it at a glance, put the "Cleaning mode" select next to the vacuum on your dashboard.

**Tip:** the Xiaomi vacuum entity is no longer needed on dashboards. You can hide it: Settings → Entities → select the Xiaomi vacuum → settings → *Visible* off. Do not disable or delete it, this integration reads its state and sends commands through it.

## Problems and error codes

The robot and its station report error codes as numbers (`0` = no error) in two sensors of the Xiaomi Home integration: `error` (`p_17_35`, robot) and `station_error` (`p_17_79`, station). This integration turns them into text:

- **Problem sensor** (diagnostic, on the integration's device): `No problem` while both codes are `0`, otherwise the translated text for the code. Unknown non-zero codes show as "Robot error (unknown code)" / "Station error (unknown code)"; the underlying state value, for automations, is `robot_unknown` / `station_unknown`. If both report an error at the same time, the robot error decides the text; the station code stays visible in its attribute. The raw codes are always available as the attributes `robot_error_code` and `station_error_code`. The sensor is unavailable when the source sensors are.
- **Vacuum entity:** while a code is non-zero it shows **Error** (instead of Paused/Docked) and has the translated problem as the attribute `problem`. When the code returns to `0`, it shows its normal state again.
- Build notifications or automations on the problem sensor; this integration does not send any, and it cannot clear errors.

Known codes (only codes confirmed on the device are listed):

| Source | Code | Meaning |
|---|---|---|
| Station | 4502 | Not enough water or no dirty water tank installed (the fresh water tank sensor then reads `Uninstalled`) |

**Fresh water tank** (`clean_water_cistern_p_17_51`): `Normal`, `Uninstalled`, `Unusable`, `FluidLow`. Other station sensors on the device: dirty water tank `drain_cistern_p_17_52` (`Nor`, `Uninstall`, `Unusable`), mop wash tank `mop_clean_tank_p_17_54` and dust bag `dust_bag_p_17_53` (`Nor`, `Uninstall`).

**Reporting a new code:** an unknown code shows as "Robot/Station error (unknown code)" (state value `robot_unknown` / `station_unknown`). Open an issue with the code (from the attributes), what the robot announced or the app showed at that moment, and what you did to clear it. To add a code yourself, put it into `ROBOT_ERROR_CODES` or `STATION_ERROR_CODES` in `const.py` (code → key, e.g. `1234: "robot_1234"`, with `1234` as a placeholder) and add that key under `entity.sensor.problem.state` and `entity.vacuum.vacuum.state_attributes.problem.state` in `translations/en.json` and `de.json`. Only add codes whose meaning is confirmed.

## Select entities

| Select | Values (command) | Source of state |
|---|---|---|
| Cleaning mode | Vacuum & mop (0), Vacuum (1), Mop (2), Vacuum, then mop (3), Customised (4) | Sensor |
| Suction power | Quiet (0), Standard (1), Strong (2), Max (3) | Sensor |
| Water level | Low (0), Medium (1), High (2) | **no sensor**, remembered only |
| Passes | Once (1), Twice (2) | Sensor |
| Route preference | Fast (0), Daily (1), Deep (2) | Sensor |

All values were confirmed on the device by switching them in the app and reading the sensors. Suction power "Max" and "Strong" partly come from the specification. "Strong" was observed.

**Cleaning mode:** The app has two similar modes, "Vacuum & mop" (both at once) and "Vacuum, then mop" (value 3). The app label does not make the difference obvious, only the value does.

**Water level:** The robot does not report it to Home Assistant. The entity shows the value last set *from Home Assistant*. Changes made in the app stay invisible.

## Other services

- `miot_vacuum_rooms.forget_room`: remove a room and its button
- `miot_vacuum_rooms.clean_floor`: whole floor with the global settings, **untested** (message `[1, "[]"]`)

With several vacuums, pass `entry_id` each time.

## Limitations

- **No map.** The map data lives in the Xiaomi cloud. Through the official integration, the robot only reports a map ID locally. The cloud map integrations in HACS do not list `xtl` robots in their device lists (not verified).
- **No zones.** They would need coordinates from the map.
- **Per-room settings** (the icons below the rooms in the app) can be neither read nor set. The format of the `customization-rooms` action is unknown.
- **New map, new IDs:** [Assumption] If rooms are re-divided in the app or the map is recreated, the IDs change. Learn the rooms again.
- Entities are recognised by the numbers at the end of their entity ID. Renaming entities does no harm (the mapping uses the entity registry), but a different naming scheme in the Xiaomi integration does.

## Development

The tests use [`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component), which runs on Linux and macOS, not on Windows. `requirements_test.txt` pins the release that matches the current Home Assistant version. Home Assistant 2026.3 and later need **Python 3.14**.

**One command for all environments:**

```
python scripts/check.py
```

It picks the mode from the environment and prints which one it chose and why. The exit code is the test result. Extra arguments go to pytest (local and WSL mode), e.g. `python scripts/check.py -k vacuum`.

| Environment | Mode |
|---|---|
| Linux, macOS | Runs `python -m pytest` locally. Needs a venv with `requirements_test.txt` installed (`python3.14 -m venv .venv && .venv/bin/pip install -r requirements_test.txt`). |
| Windows with WSL | Runs the tests inside WSL with the venv from the environment variable `MIOT_WSL_VENV` (a Linux path) or `.venv-wsl/` in the repository. If `requirements_test.txt` changed since the last run, it updates the venv first (with `uv` inside WSL). |
| Windows without WSL | **CI mode:** pushes the current branch and waits for the GitHub Actions run of this commit (needs a logged-in `gh`). It refuses to run on `main` or with uncommitted changes, because CI only tests commits. On failure it prints the failed log. |

Setting up the WSL venv (once, inside WSL, from the repository folder; later updates happen automatically):

```
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv --python 3.14 ~/.venvs/miot-vacuum-rooms
uv pip install --python ~/.venvs/miot-vacuum-rooms -r requirements_test.txt
```

Then set `MIOT_WSL_VENV=/home/<user>/.venvs/miot-vacuum-rooms` on Windows. A venv in your Linux home is much faster than one on the Windows drive and works for all checkouts. In git worktrees `MIOT_WSL_VENV` is required, because a `.venv-wsl/` only exists in the checkout where it was created.

**CI:** `.github/workflows/validate.yml` runs hassfest and the HACS validation (daily and on every push and pull request). `.github/workflows/tests.yml` runs the tests on every push and pull request against the minimum (2026.3.x) and the current (2026.10.x) Home Assistant version.

## Releasing

Releases are automated with [release-please](https://github.com/googleapis/release-please). It reads the Conventional Commit messages on `main`.

1. Develop as usual and test the change **manually in your local Home Assistant** before merging to `main`.
2. After each merge, release-please opens or updates a **release PR** with the next version and the changelog. It also updates `version` in `custom_components/miot_vacuum_rooms/manifest.json`.
3. Merge the release PR. This creates the tag `vX.Y.Z` and the GitHub release, which HACS offers as an update.

`tests/test_release.py` checks that `manifest.json`, `.release-please-manifest.json` and `release-please-config.json` stay consistent.

Notes:

- **First release:** `release-please-config.json` contains `"release-as": "0.1.0"`. Remove that line after the first release is published, otherwise every release PR would propose 0.1.0 again.
- **Repository setting:** *Settings → Actions → General → "Allow GitHub Actions to create and approve pull requests"* must be enabled, otherwise the workflow cannot open the release PR.
- **No checks on the release PR:** pull requests created with the default `GITHUB_TOKEN` do not trigger other workflows (tests, validation). To get those checks, store a personal access token as a secret and pass it to the action via `token:`.
