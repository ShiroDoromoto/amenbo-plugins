# Carrying data outward

English · [日本語](carrying-data-outward.ja.md)

A plugin that carries Amenbo's data off the device — a viewer, an audit trail, an automated backup, a
mirror in another tool — follows one way of doing it. The purposes differ; the road does not.

This document is that road, and nothing else. Writing the plugin itself is
[Writing a plugin](writing-a-plugin.md).

> The road out is available from Amenbo 11.0.0. Check whether `amenbo sync --help` answers on your machine.

## One-way, and read-only

Nothing you put outside comes back. There is no door on `sync` that writes, and no command that reads a
snapshot back in. Settling for one direction is what makes conflict resolution unnecessary rather than hard.

## The four doors

| Door | What it answers | When you use it |
| --- | --- | --- |
| `amenbo sync version` | one number for the window | before sending, to see whether anything moved. **Asked often** |
| `amenbo sync snapshot` | every record in the window, and where that stands in the ledger | first run, reset, and gap |
| `amenbo sync changes --since <cursor>` | which records moved since a cursor, and the cursor to come back with | ordinary running |
| `amenbo sync records --dataset <name> --ids <id,…>` | what those records now hold | reading back what the ledger named |

**Ask often, carry rarely.** The version answers without building a snapshot, so confirming that nothing
changed never costs you the whole window.

```json
{ "project_id": 3, "version": 4821 }
```

**Compare it for inequality, not for order.** A `restore` winds the store back and the version comes back
with it, so a number that went down still means changed. A window nothing has written since this build
began stamping answers `0`.

## The window is what you observe

Everything here is closed to the window the caller reads through. A plugin launched to observe one project
gets that project and nothing else — the same window `AMENBO_PLUGIN_REACH` names.

The version is the window's too. Churn in another project never moves yours.

## The cursor is yours to keep

Amenbo does not hold it. Store how far you have read as your own setting, and hand it back next time.

Your first cursor is named in the header of a `sync snapshot`.

```json
{
  "amenbo_sync": {
    "format": "amenbo-sync-json",
    "format_version": 1,
    "schema_version": "1",
    "app_version": "11.0.0",
    "taken_at": "2026-08-09T09:00:00+00:00",
    "project_id": 3,
    "cursor": 4795
  },
  "tables": { "project": [], "task": [], "decision": [] }
}
```

A snapshot is read from **one instant**, so nothing in it refers to something that is not in it, and a join
row travels only when both of its ends are inside the window. A plugin's secrets stay home. An attachment's
row travels and names the bytes it stands for, but **the bytes stay on the device**.

## Ordinary running

1. Ask `amenbo sync version`. Same number as the one you hold, and there is nothing to do
2. Take the unread with `amenbo sync changes --since <the cursor you saved>`
3. **Read back** what came up `insert` or `update`, with `amenbo sync records`
4. Send it outward
5. Save the `cursor` the answer handed you

The ledger says which record moved and **never what it now holds**.

```json
{
  "v": 1,
  "project_id": 3,
  "cursor": 4821,
  "more": false,
  "changes": [
    { "dataset": "task", "op": "update", "record_id": 12 },
    { "dataset": "task", "op": "delete", "record_id": 15 }
  ]
}
```

**Deletions arrive too.** A `delete` has nothing left to read back — drop it from the copy outside. Forget
to, and what you deleted in Amenbo lives on out there.

A page is bounded. When one was cut short `more` is set, so come straight back with the cursor you were
handed.

Reading back takes the `dataset` and the `record_id`s exactly as the changes named them.

```sh
amenbo sync records --dataset task --ids 12,15,31
```

What comes back is the snapshot's document with one table in it, so **whatever reads a snapshot reads this**.
One read answers at most a page of changes' worth of ids (500); past that it is refused rather than cut
short, so ask in pages.

An id the window does not reach is not missing — it simply is not there. Neither is a deleted one, and since
the `delete` already said which is which, a gap in the answer is never a surprise.

## Do not take the whole window every time

What you carry grows with the project. Reading all of it on every change is a shape that eventually breaks.
Take only the unread, and what rides is only what moved.

The whole window is for **the first run, a reset, and a gap**.

## A gap drops you back to the whole

Stay away long enough and your cursor falls out of the stretch the ledger still speaks for. Amenbo says
**missing** rather than handing you an empty page that would read as "nothing changed".

```json
{
  "error": {
    "code": "sync_gap",
    "message": "the ledger cannot say what changed since 1200 — that cursor is outside the stretch it still speaks for",
    "hint": "Take the window again with `amenbo sync snapshot` and read on from the cursor its header names."
  }
}
```

It exits non-zero. Do not pass over it in silence. Take a fresh `sync snapshot` and read on from the cursor
its header names.

Where the history itself is the point — an audit trail — this is where you record that something was lost.
**Never leave a hole nobody was told about**: that is what the gap is for.

## Carry a command that takes the whole again

"Throw away where I had read to, and take the whole thing again" — a plugin that carries data outward
publishes this as a command.

**It makes recovery one move.** The version drifted, the key changed, the data at the far end is broken,
nobody knows why — all of it is fixed the same way. Build a different procedure per cause, and your users
have to learn which is which.

## Do not make the signal responsible for correctness

Amenbo fires a hook when something changes. It is **fire-and-forget, so it can be missed**.

**Carry three triggers.**

- the hook arriving
- your own startup
- an interval

Whichever one fails, you still catch up in the end. What guarantees correctness is the version and the
cursor, never the hook.

**Batching is yours to do.** Do not send a hundred times for a hundred changes —
`AMENBO_PLUGIN_REACH_QUEUE_REMAINING` tells you how many are still behind this launch.

## Encryption is the carrier's job

Amenbo holds no key, and these doors answer in the clear. If it leaves the device, **the plugin encrypts it**.

The local store stays in the clear, and that is fine. The trust boundary closes at the device, and protection
on it is the OS's full-disk encryption. What moves is only what goes outside, so that is the only place the
encryption goes.

Do not hand the key to the place you store it. The moment you do, encrypting it meant nothing.
