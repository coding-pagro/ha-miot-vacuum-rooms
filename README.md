# MIoT Vacuum Rooms

Add-on integration for the **official Xiaomi Home integration** in Home Assistant. Some robot vacuums only show up there as raw MIoT entities (`notify.…_a_17_1`, `sensor.…_p_17_13`). This integration builds a usable interface on top of them, without the Xiaomi cloud map or extra credentials:

- **Clean rooms by name**, also several rooms in a chosen order
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
| Integration code | Tested in a Home Assistant test environment, **not yet installed in a live instance** |
| Whole-floor service | **Untested**, command derived from app behaviour |
| Other models | Unverified. They only work if they use the same MIoT specification (service 17) with the same numbers and values |

## Requirements

- Official Xiaomi Home integration set up with the robot vacuum
- The device has entities with these suffixes (service 17):
  - Actions (`notify`): `a_17_1`, `a_17_26`, `a_17_27`, `a_17_28`, `a_17_46`, `a_17_50`
  - Sensors (`sensor`): `p_17_10`, `p_17_13`, `p_17_14`, `p_17_34`, `p_17_65`
- If one of them is missing, the setup names it.

## Installation

1. HACS → Integrations → menu → *Custom repositories* → enter the repository URL, category *Integration*.
2. Download, then restart Home Assistant.
3. Settings → Devices & services → *Add integration* → "MIoT Vacuum Rooms" → select the vacuum (`vacuum.…`).

Repository: https://github.com/coding-pagro/ha-miot-vacuum-rooms

## Learning rooms

The robot's room IDs are not the numbers shown on the app map. Example from a Jonr P20 Pro: a room numbered 7 on the map had ID 5 on the robot.

**Option A, service:** Developer tools → Actions → `miot_vacuum_rooms.learn_room`, enter a name, run it. Then start exactly that room in the app, wait a moment and cancel the run in the app. The ID is stored under the name.

- Only a *new* change of the sensor counts. The previous run must have finished (sensor empty).
- Starting several rooms at once is rejected.
- A new name for a known ID replaces the old name.

**Option B, text:** Integration → *Configure* → Rooms, one room per line as `Name=ID`.

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
- The service switches to **Customised** mode and waits up to 10 seconds for confirmation. In this mode the **per-room settings from the app** apply (suction power, water level, passes per room). The global select entities have no effect on the run.
- By default it only starts when the robot is on its dock (`docked`). Starting in the middle of a job made the robot lose its orientation. The condition can be switched off in the options.
- The mode stays on Customised afterwards.

Every learned room also gets a "Clean …" button that calls the same service for that one room.

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

```
python -m venv venv && venv/bin/pip install pytest-homeassistant-custom-component
venv/bin/pytest
```
