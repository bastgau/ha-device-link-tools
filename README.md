# HA Device Link Tools for Home Assistant

[![Maintainer: bastgau](https://img.shields.io/badge/maintainer-bastgau-orange?logo=github&logoColor=%23959da5&labelColor=%232d333a)](https://github.com/bastgau)
[![Made with Python](https://img.shields.io/badge/Made_with-Python-blue?style=flat&logo=python&logoColor=%23959da5&labelColor=%232d333a)](https://www.python.org/)
[![Made for Home Assistant](https://img.shields.io/badge/Made_for-Homeassistant-blue?style=flat&logo=homeassistant&logoColor=%23959da5&labelColor=%232d333a)](https://www.home-assistant.io/)
[![GitHub Release](https://img.shields.io/github/v/release/bastgau/ha-device-link-tools?logo=github&logoColor=%23959da5&labelColor=%232d333a&color=%230e80c0)](https://github.com/bastgau/ha-device-link-tools/releases)
[![HACS validation](https://github.com/bastgau/ha-device-link-tools/actions/workflows/validate-for-hacs.yml/badge.svg)](https://github.com/bastgau/ha-device-link-tools/actions/workflows/validate-for-hacs.yml)
[![HASSFEST validation](https://github.com/bastgau/ha-device-link-tools/actions/workflows/validate-with-hassfest.yml/badge.svg)](https://github.com/bastgau/ha-device-link-tools/actions/workflows/validate-with-hassfest.yml)

<p align="center" width="192">
    <img src="https://raw.githubusercontent.com/bastgau/ha-device-link-tools/refs/heads/main/custom_components/device_link_tools/brand/icon.png">
</p>

## Description

Home Assistant custom integration to link existing entities to an existing device, for entities whose integration offers no device option. Links are recorded and re-applied, so they survive restarts and reloads.

## Installation

### Installation via HACS

1. Add this repository as a custom repository to HACS:

[![Add Repository](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=bastgau&repository=ha-device-link-tools&category=Integration)

2. Use HACS to install the integration.
3. Restart Home Assistant.
4. Set up the integration using the UI:

[![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=device_link_tools)

### Manual Installation

1. Download the integration files from the GitHub repository.
2. Place the `device_link_tools` folder in the `custom_components` directory of Home Assistant.
3. Restart Home Assistant.
4. Set up the integration using the UI:

[![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=device_link_tools)

## Actions

See **[Entities & Actions](docs/guide-explained-entities.md)** for the full list of sensors, binary sensors, the calendar and its attributes, the diagnostic cache-purge buttons, and the available actions.

## How it works?

### This integration only touches its own links

An entity is linked to **at most one device** — `RegistryEntry.device_id` is a single
field — so linking to a second device means moving, not adding.

Both mutating actions only act on a link this integration recorded:

- a link **recorded here** can be re-pointed to another device, or removed, in one call;
- a link set **elsewhere** is refused, by `add_identifier` and by `remove_identifier`
  alike;
- an entity with **no** link is linked as usual, and unlinking it is a no-op reported as
  `unchanged` — running the same script twice is safe.

The reason is that a link an entity's **own integration** declares cannot be changed from
here at all. An MQTT sensor with `device.identifiers`, or a template helper with a
`device_id`, gets its device written back by the entity platform on every restart, and
the re-application deliberately does not fight that: it only fills a link that is empty.
Moving or removing such a link would look like it worked and be undone at the next
restart, so it is refused instead — change it where it comes from: the helper's device
option, the MQTT discovery payload, and so on.

The **Unlink entities** step of the options flow lists only the entities this integration
recorded, for the same reason.

### From the UI

**Settings → Devices & services → Device Link Tools → Configure** offers the same two
operations with pickers: _Link entities to a device_ (an entity picker and a device
picker) and _Unlink entities_, which lists what is currently linked. This mirrors how the
template helper lets you pick a device, and writes to the same recorded links the actions
use.

### When a link can no longer be applied

If the device recorded for an entity can no longer be identified — it was removed, or it
was split between config entries so its identifiers now match several devices — a
**repairable issue** appears under Settings → System → Repairs. Fixing it asks for a
device again, or lets you submit nothing to stop tracking that entity. Until then the
entity simply stays unlinked; nothing is retried in a loop.

### Links survive restarts

An entity platform passes the device it knows about — or `None` — to the entity registry
every time it adds an entity, so the owning integration resets a manually set link on
every restart and on every reload of its config entry.

Every link made through these actions is therefore recorded in the config entry options
and re-applied when Home Assistant has started, and again whenever the registry clears
it. The re-application only fills in an empty link: if the owning integration sets a
device itself, that choice wins and nothing is overwritten. `remove_identifier` deletes
the recorded link, so an entity you unlink stays unlinked.

### Limitations

- **The entity must have a unique ID.** Entities without one never enter the entity
  registry and cannot be linked to a device by any means. For a YAML `rest` or
  `command_line` sensor, add `unique_id:` to its configuration and reload it.
- The integration writes to Home Assistant's internal registries. These APIs are not
  covered by any stability guarantee across major versions.
- Between Home Assistant starting and the re-application pass, an entity is briefly
  unlinked. An automation that triggers on area membership during startup can see the
  gap.

### What linking to a device changes

Beyond appearing on the device page, a linked entity follows the device
(`homeassistant/helpers/entity_registry.py`, `async_device_modified`):

- **Device deleted** — the entity is _not_ deleted. It does not belong to the device's
  config entry, so it is only unlinked.
- **Device disabled** — the entity is disabled too, and stops working.
- **Device renamed** — an entity whose name is not device-derived
  (`has_entity_name: false`, the usual case for REST and template YAML sensors) has its
  name rewritten with the device name as a prefix.
- **Area** — an entity with no area of its own inherits the device's area, and becomes
  reachable by area-based targeting.

There is no domain to respect: a Home Assistant device is not typed and routinely holds
entities from several domains. Attaching a `sensor` to a device that also carries a
`light` is normal, not a workaround.

History and statistics in `home-assistant_v2.db` are untouched — only the structural link
changes.

## Diagnostics

The integration entry has a **Download diagnostics** button (Settings → Devices & services → Device Link Tools → the three dots on the entry). It is the quickest way to report a problem: attach the file to an issue instead of describing symptoms.

## Debugging

To show info and debug logs for the Device Link Tools integration, enable logging in `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    # Log for Device Link Tools integration
    custom_components.device_link_tools: debug
```

## Troubleshooting

## Support & Contributions

If you encounter any issues or wish to contribute to improving this integration, feel free to open an issue or a pull request on the GitHub repository.

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/bastgau)

Enjoy!
