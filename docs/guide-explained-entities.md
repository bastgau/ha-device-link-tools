## Entities & Actions

The integration creates no entities. It only registers actions.

### `device_link_tools.read_identifiers`

Reads the identifiers of the device an entity is currently linked to. Returns a response,
so it needs a `response_variable` in a script.

```yaml
action: device_link_tools.read_identifiers
data:
  entity_id: sensor.boiler_temperature
response_variable: link
```

```yaml
entity_id: sensor.boiler_temperature
device_id: 9f2c1e...
identifiers:
  - ["mqtt", "8848_5"]
connections:
  - ["mac", "aa:bb:cc:dd:ee:ff"]
name: Boiler
```

`device_id` is `null` and `identifiers` empty when the entity is not linked to anything.

### `device_link_tools.add_identifier`

Links one or more entities to a device. The device is designated in one of three mutually
exclusive ways: picked directly, by the identifiers it carries, or by another entity
already linked to it. The picker is the easy one from the UI.

```yaml
action: device_link_tools.add_identifier
data:
  entity_id:
    - sensor.solar_power
    - sensor.grid_import
  device_id: 9f2c1e...
```

```yaml
action: device_link_tools.add_identifier
data:
  entity_id: sensor.solar_power
  identifiers: mqtt:8848_5
```

```yaml
action: device_link_tools.add_identifier
data:
  entity_id:
    - sensor.solar_power
    - sensor.grid_import
  source_entity_id: sensor.boiler_temperature # put them on that entity's device
```

Whichever you use, the link is recorded by the device's **identifiers**, so it survives a
device being recreated. A device that carries no identifiers at all (known only by its
connections) is refused, because such a link could not be restored after a restart.

Identifiers can be written in any of these forms, on their own or in a list:

```yaml
identifiers: mqtt:8848_5
identifiers: { domain: mqtt, identifier: "8848_5" }
identifiers: [["mqtt", "8848_5"]]
```

The last one is what `read_identifiers` returns, so its output can be fed straight back
in. A pair has to stay inside a list: a bare `["mqtt", "8848_5"]` is read as two
identifiers, and rejected as such.

### `device_link_tools.remove_identifier`

Unlinks entities from their device.

```yaml
action: device_link_tools.remove_identifier
data:
  entity_id: sensor.solar_power
```

The two mutating actions are admin-only. Automations and scripts run without a user
context and are unaffected.
