# User guide

## Connect and follow

Connect a Launch Control XL 3 through USB. XL View connects automatically when it can identify the controller. The bottom-right MIDI button opens connection controls: device selection, Connect/Disconnect and Scan. Green means connected, red means disconnected and amber means connecting.

Follow controller is on by default in Settings → General. When available, it follows Custom Mode changes made on the hardware. Unsaved edits suspend following so that a mode switch cannot replace your draft. Use Resume following when ready.

The bottom tiles show slot names read from the controller. The outline is your editing destination; LIVE marks the currently active hardware mode. Clicking a tile reads it, but does not switch modes on the controller. Slot 16 Default is read-only and does not expose its factory mapping.

## Read the display

Move a control to see its last received MIDI value and assignment. Relative values are raw incoming relative messages, not reconstructed plugin values. A dash means the value is unknown. Imported names are controller labels; the application does not discover DAW parameter names.

## Edit

Click a knob, fader or button to open the right-side editor. Change its name, message type, number, channel, range or supported behavior. LED colors are available for controls that have LEDs. A mode name supports up to 16 ASCII characters; control names support up to 31.

Ctrl-click toggles individual selections. Shift-click selects a range in left-to-right row order; Ctrl+Shift adds a range. Shared edits, Copy and Paste are in the same panel. Undo edit and Changes appear only while the editor is open. Click the large mode name to rename it.

Edits stay in the local draft until sent. Use the single-control send button for one selection, or Send entire mode for the complete mode. Check the destination slot before sending. A single-control send retains the hardware mode name and merges the selected control into a fresh read; it does not apply an unsent mode rename.

Settings → General can enable Preview changes before sending; it is off by default. Before a write, XL View saves a local backup. A successful write requires a matching readback. If verification fails, the slot may have changed partially: reconnect, read it again and use the backup if needed. Undo edits the local draft; it is not a hardware undo command.

## Preset library

Save preset stores the current mode locally. Preset library provides file import/export, device import, version selection, loading for editing and sending to the active slot. Loading alone never writes hardware. Identical latest saves are deduplicated; same-name presets share one entry. The five latest versions remain active, and older versions are moved to an archive. Automatic slot backups are separate.

Custom Modes configure the controller's outgoing MIDI. Your plugin may need its own MIDI Learn or DAW mapping to respond. Save those instrument settings in the appropriate plugin preset or DAW project.

## Appearance

Use the pin icon for Always on top. The editing panel expands the window to the right. Settings → Control labels controls font, scale, bold, text color and background; changes are previewed immediately and persist locally. These settings never change controller memory or `.syx` files.

## Where data lives

| Edition | Application | Presets and backups |
| --- | --- | --- |
| Installed | `%LOCALAPPDATA%\Programs\XL View` | `%LOCALAPPDATA%\XL View\presets` |
| Source | Your checkout | `presets` inside the checkout |
| Portable | Entire extracted application folder | `presets` beside the executable; a developer `dist/XL View` build uses the project-level `presets` folder |

Subfolders include `library`, `backups` and `archive/library`. Preferences use Qt's `GearStation/XL View` settings namespace. Installed updates and uninstall preserve user data. The installer does not bundle personal mappings.

## Troubleshooting

- **No controller:** reconnect USB, open the MIDI panel and Scan. Check that it is an XL 3, not an earlier XL model.
- **Port busy:** disconnect Components or another app holding the MIDI port. Keep one connected XL View instance. Concurrent DAW access depends on the driver.
- **Follow unavailable:** the separate DAW port may be occupied; you can still select an editing slot manually if the main MIDI connection is available.
- **No moving values:** check the connected device, LIVE mode and MIDI channel. An edited draft can differ from the hardware mapping until sent. Read again after external edits.
- **Plugin does not respond:** ensure MIDI reaches the instrument and that its assignments match the controller. XL View's successful send verifies controller memory, not plugin routing.

For unresolved problems, include Settings → General MIDI diagnostics and reproduction steps in a GitHub issue. Review logs for private information first.
