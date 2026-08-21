# Writing a plugin

English · [日本語](writing-a-plugin.ja.md)

An Amenbo plugin is **just an executable**. Any language will do. Amenbo starts it as a child process,
hands it JSON on stdin, and reads what it wrote to stdout and stderr along with how it exited.

This document is that contract, written for authors. These are the rules Amenbo itself enforces at its door,
and the same ones `amenbo plugin validate` checks.

> Plugins are available from Amenbo 2.0.0. Check whether `amenbo plugin --help` answers on your machine.

## Two faces — hooks and commands

A plugin has two faces. Implementing one of them is fine.

| Face | Who starts it | Return value | When it fails |
| --- | --- | --- | --- |
| **Observation hook** | Amenbo, automatically and asynchronously, when an event fires | not used | a warning, nothing more — Amenbo's own work is unaffected, and that one event is dropped (see "What delivery promises") |
| **Command** | a person or their AI, explicitly, via `amenbo plugin run <name> …` | **used** — stdout *is* the return value | the call is reported as failed |

A hook is an observer that runs **after the write is committed**. It cannot change Amenbo's state and it
cannot veto anything. Actually *doing* something is the command face's job.

## What you receive

### A hook's stdin

When an event fires, its JSON arrives on stdin.

```json
{
  "v": 1,
  "event": "task.status_changed",
  "id": 42,
  "actor": "ai",
  "at": "2026-07-22T09:00:00Z",
  "new": "in_progress",
  "config": { "base": "main" }
}
```

| Field | Meaning |
| --- | --- |
| `v` | the payload contract version, `1` today |
| `event` | the event's name — one of the eleven below |
| `id` | the affected record's number (the one you talk about it by) |
| `actor` | who drove the write: `human` or `ai` |
| `at` | when it fired, as `2026-07-22T09:00:00Z` |
| `new` | the state after the change, on the events whose name does not already say it |
| `record` | the vanished record itself, on the deletion events alone |
| `parent` | the task a comment belongs to, by number — on `comment.added` and `comment.removed` |
| `config` | your own non-secret settings. Absent entirely when you have none |

The v1 catalog is eleven events.

| Event | `new` | What happened |
| --- | --- | --- |
| `task.created` | — | a task was created |
| `task.status_changed` | the new status | a task's status changed (the two terminals are the next rows) |
| `task.done` | — | a task was completed |
| `task.rejected` | — | a task was decided against — the other terminal, `task.done`'s sibling |
| `task.assigned` | the new assignee | a task was assigned or reassigned |
| `task.moved` | the destination slug | a task moved to another project |
| `task.deleted` | — | a task was deleted |
| `decision.accepted` | — | a decision was accepted |
| `decision.rejected` | — | a decision was rejected |
| `comment.added` | — | a comment was added (`id` is the comment's, `parent` its task) |
| `comment.removed` | — | a comment was taken back (`id` is the comment's, `parent` its task) |

No *before* value is carried: a record that still exists you read back by its number, so v1 loads the new
state only. Deletion is the exception — there is nothing left to read back — so the vanished record travels
in `record`. A comment is the other one: you read it as part of a task's timeline, never by its own number,
so both comment events name that task in `parent`.

`v` rises only when an existing field's meaning changes. Adding a field never bumps it, so write your
plugin to **ignore keys it does not know**.

### A command's stdin and arguments

Called as a command, no event has fired, so the smallest possible document arrives:

```json
{ "v": 1, "config": { "base": "main" } }
```

In `amenbo plugin run worktree start 123`, the words `start 123` reach you **verbatim on argv**. Amenbo
neither parses nor rewrites them — what they mean is yours to decide.

## What you return

You answer on three channels. This is the shape `devtool` proved in the field, lifted into the contract.

- **stdout is the machine return value**, handed back to whoever invoked the command.
- **stderr is human diagnostics** — a summary, an error, context. Never the return value.
- **the exit code is success or failure.**

What that means depends on the face.

| Face | stdout | On failure |
| --- | --- | --- |
| Command | with exit code 0, relayed verbatim as the caller's stdout | a non-zero (or signalled) exit **discards the return value** and the call is reported failed |
| Observation hook | not used as a return value | warned about, and nothing else |

The typical way to hand a shell a return value is one line to evaluate. Amenbo relays that line
verbatim and judges no dialect, so the shell it has to survive is the caller's, not yours:

```sh
eval "$(amenbo plugin run worktree start 123)"   # POSIX shell
```

```powershell
iex (amenbo plugin run worktree start 123)       # PowerShell
```

If you take that shape, **keep it to one line that both dialects take as it stands**, and put both
launches in your plugin's README. A line like `cd '<path>'` passes either way; escaping is where they
part, and getting a value through both is the condition you take on — Amenbo has no layer that guesses
the caller's shell, and the only one who knows which dialect the line is in is you. Meet that condition
and whether your `os` can name `windows` is decided by how the launch is written, not by anything in
your implementation.

### Time limits

| Face | Limit | What happens past it |
| --- | --- | --- |
| Observation hook | none | you are waited out, however long you take |
| A replying hook (`reply: true`) | 2 seconds | the reply is given up on; the command it rode in on is never stalled |

There is no reason to hurry an observation hook. Nothing is behind it but the rest of your own queue, and
Amenbo itself moved on long ago. Being cut off mid-work is the worse outcome by far — it leaves something
half-done out in the world.

Only a hook declaring `reply: true` runs **synchronously**, and it is its **stderr** that is carried back
to the caller as advice. It is possible on the CLI face alone — the GUI has nobody holding out a hand for
the answer.

## What delivery promises

Delivery happens in two layers. An event lands in the **record of what happened**, is fanned out onto a
**queue** per subscribed plugin, and a **runner** works that queue from the head, one event at a time.
There is at most one runner per plugin, and none of them is a daemon — a runner starts when Amenbo runs,
and ends when its own queue is empty.

What this shape promises, and what it does not, is what shapes how you write a plugin.

- **The same event can arrive twice.** If a runner dies right after you finish an event but before Amenbo
  takes that row off the queue, the next runner replays it. Amenbo cannot see what you did on the other
  side, so it cannot prevent this. **Make the second run a no-op** — otherwise the same message gets posted
  twice.
- **A failed event is dropped.** Amenbo records it in the execution log and never retries. Whether to retry
  is yours to decide. A half-hearted retry in Amenbo would compound with yours, and nobody would be able to
  say how many times a thing gets sent.
- **One failure does not stop the run.** The runner moves on to the next event. A single failure never
  clogs everything behind it.
- **Order holds within one plugin only.** Your own queue arrives in the order it was stacked. **Order
  across plugins is not promised** — the queues are separate. Even within one plugin it is what normally
  happens rather than a guarantee: waking from sleep, or a clock that moved, can have a runner wrongly
  judged gone, and then two run at once. Taking a long time does not do it on its own — a runner keeps
  saying it is alive for as long as it is working. When order does break, the only harm is the double
  delivery above.
- **Nothing arrives while you are disabled.** `amenbo plugin disable` throws away whatever was queued at
  that moment, and re-enabling starts **from now** — what happened while you were off does not come through.
  Creations and updates you can catch up on by re-reading the current state; deletions you cannot. If that
  matters to you, stay enabled and do nothing instead of being disabled.
- **Nothing is promised about how soon.** If a runner is killed part-way, the rest waits until somebody
  touches Amenbo again. That is what carrying no daemon costs.

There is no "acknowledged" call back into Amenbo, either. **The reply is your process returning**, and the
row leaves the queue whether you exited clean or failing. There is nothing here for you to implement.

### How much is behind you

You are launched once per event, so you cannot see your own queue — and deleting a project can put fifty
events on it at once. The runner tells you how many there are:

| | |
| --- | --- |
| `AMENBO_PLUGIN_REACH_QUEUE_REMAINING` | how many events are still queued for you **after this one, in the project this run fires for** |

**The count is your window's, which is what `REACH` in the name says.** It is the same scope as
`AMENBO_PLUGIN_REACH` below: the project you fired for, and no other. Enabled in two projects, you are run
for each with its own count, and neither number says anything about the other. Events on records belonging
to no project are one group of their own, counted like any other. There is always a number.

It counts down to `0` and never rises while a batch is being worked through: five queued events for one
project are run with `4`, `3`, `2`, `1`, `0`. Anything queued while that is going on is not added to the
count in flight — it arrives right after, as its own run of numbers.

That makes batching yours to do, and cheap: hold what you were given **per project**, and send that
project's batch when you see `0`. What you hold for another project is not ready to go — its own runs will
say so.

**`0` means your project's queue is empty as of this launch — it does not promise nothing more is coming.**
An event written a moment later is delivered like any other, so a batch you flushed on `0` may be followed
by a second one. That is one message becoming two, never a message lost. Amenbo itself never holds delivery
back: what it sends, it sends in order, as fast as it can.

## Settings and secrets

You declare your settings in the manifest. The user fills them in and Amenbo delivers them.
**A plugin never reads a secret file of its own.**

| Declared | Where it is kept | How it reaches you |
| --- | --- | --- |
| `secret: true` | the store, as this project's own row — carried by a backup, left out of an export | the environment variable `AMENBO_CONFIG_<KEY>` |
| not marked secret | the store, as this project's own row | the `config` object on stdin |

The variable's name follows from the key mechanically: upper-case it, and map anything that is not a
letter or a digit to `_` (`webhook_url` → `AMENBO_CONFIG_WEBHOOK_URL`).

**A setting belongs to a project, and there is one value under it.** A plugin is switched on per project,
so it is answered per project: enabled in two, it has two sets of values and reaches each run with the one
belonging to where the event happened. There is no machine-wide default beneath them to fall back to.

A field with no value set contributes nothing — no variable, no `config` key. A field marked
`required: true` keeps the plugin from being enabled until it holds a value (Amenbo checks **presence**
only; whether a value is *valid* is yours to judge).

You receive **your own settings and no one else's.**

### What kind of field it is

A field is a line of text unless you say otherwise. Where the answers are yours to know in advance, declare
them and the user picks instead of spelling:

| `type` | The form shows | You receive |
| --- | --- | --- |
| absent (the default) | a single-line box | what the user typed |
| absent, with `secret: true` | a single-line box, masked | what the user typed, as an environment variable |
| `multi` | a checkbox per option you declared | the chosen values, joined by `,` |

```yaml
config:
  - key: events
    label: Events to report
    type: multi
    default: task.done                  # in force until the user answers
    options:
      - value: task.done                # what you receive
        label: Finished                 # what the user reads
      - value: task.rejected
        label: Decided against
```

`default` works on a text field too: it is simply the value in force while the field is unset. A field
with a default is never unanswered, so it does not block `enable` however `required` is marked.

An option's `value` may not contain `,` (they are joined by one) and may not be `none` (reserved, see
below). Every value must be distinct, and a `default` must name options you actually offer — the validator
refuses a manifest that breaks any of this, so you find out before you ship.

**A `multi` field has three states, and you are handed the answer, never the bookkeeping:**

| The user | You receive |
| --- | --- |
| has not answered | your `default` |
| chose some | those values, joined by `,` |
| chose none, deliberately | empty — no values at all, and not your `default` |

The last row is why `none` is reserved: Amenbo stores that deliberate empty answer under that word so it
stays distinguishable from *not answered yet*, and resolves it away before you see it. You never read
`none`, and you cannot offer it.

### Saying more than a label can

A `label` is one line, and some fields need more: what the value is for, and an example of what to type. Two
keys carry that, and a third says the value is not the user's to type at all.

```yaml
config:
  - key: webhook_url
    label: Webhook URL
    help: |
      Create one under Incoming Webhooks in your Slack app.
      One URL per channel.
    placeholder: https://hooks.slack.com/services/T000/B000
    secret: true
  - key: worker_url
    label: Worker URL
    help: setup writes this. There is nothing to type.
    readonly: true
```

| Key | What it is | Cap |
| --- | --- | --- |
| `help` | what the field is for, drawn under the box. A newline is text here | 1KB of UTF-8, per language |
| `placeholder` | one example, shown greyed inside the box while it is empty | 80 bytes, per language |
| `readonly` | the value is written by your plugin, not typed by the user | — |

**Both texts are plain, and drawn plain.** No Markdown and no link: this is the screen a user types a secret
into, and a destination you chose does not belong on it. The validator refuses a control character in either
— a newline aside in `help`, which is a body rather than a line — because `plugin config get` prints these
to a terminal, where an escape sequence can write over what Amenbo said. Both also count toward the byte cap
the schema as a whole obeys, so a form of many fields spends its budget on them.

**A `placeholder` is not a `default`.** A default is a value your plugin really receives, so an example
written there is one a user who enables without touching the field actually sends to. An example written
here is only ever read.

**`readonly` binds the screen, not the write.** The form shows the value with no input and no clear button,
while `amenbo plugin config set` still writes — that is the road your own value arrives by, a `setup` that
generates it writing back with the same command. Two rules follow from what a generated value is, and the
validator holds both: such a field may not declare a `default` (a value with an answer before anyone
generates one is not generated), and may not be `type: multi` (there is no user to offer the candidates to).
It is orthogonal to `required`, and declaring both keeps `enable` shut until your `setup` has run.

**Neither text reaches an AI.** They are shown to a person and nowhere else — the settings form draws both,
`plugin config get` prints the `help` and says which fields are readonly, and `amenbo agent --json` carries
none of it. Author prose landing where an AI reads is read as instruction.

### Saying whether the values are usable

`required` asks whether a box holds *something*. Whether what it holds is a webhook that exists, a password
that goes with its user, or two fields that contradict each other, nobody but you can say — so name one
call for it and Amenbo raises it:

```yaml
settings:
  check: config check          # your own command face, written as `agent.commands` writes one
```

It runs at the two moments the answer can still be acted on: **when the plugin is enabled**, and **after a
save while it is enabled**. Write the verdict on stdout:

```json
{ "v": 1, "ok": false, "fields": { "smtp_password": "there is a space in it" }, "message": "…" }
```

| Key | What it says |
| --- | --- |
| `ok` | whether the values are usable. The gate turns on this alone |
| `message` | one sentence about the settings as a whole. Optional |
| `fields` | one sentence per setting, keyed by the setting's own key. A key you did not declare is dropped, and the rest of the verdict stands |

**A check that does not say yes leaves the plugin disabled — and so does one that says nothing.** Failing
to start, exiting non-zero, overrunning **two seconds**, or writing something that is not a verdict all
count as *not checked*, never as *checked and fine*: a sentence past **200 bytes** or carrying a control
character makes the whole answer unreadable, which is a silence like any other. Enabling on the strength of
a plugin that crashed is the one reading this door exists to prevent.

**A check never undoes anything.** The save it follows is not stopped, and a plugin already enabled is
never switched off behind the user's back. There, what the verdict is for is the sentence on the screen.

**Your sentences are the settings form's.** `message` and each line under `fields` are drawn there and
nowhere else — the refusal the CLI prints names the keys your check spoke about and none of your text, and
`amenbo agent --json` carries no `settings` at all. For anything longer than a line, the execution log is
where your `stderr` is read (`amenbo plugin log <name>`).

### What a user may press

A settings form is boxes and a save button until you say otherwise. `actions` puts calls you already answer
on it as buttons — a connectivity test, a `setup` whose result is written back with `Amenbo plugin config
set`:

```yaml
settings:
  actions:                              # four at most
    - cmd: config test
      label: Send a test message        # 40 bytes at most — a button is short
      ask:                              # handed to this one run, and kept nowhere
        - key: otp
          label: One-time code
          secret: true
```

A `cmd` here is your own command face under the same grammar `agent.commands` holds — a subcommand and its
arguments, never a sentence — and no two actions may raise the same one. **A press runs on an enabled
plugin**, through the road every other run takes: the same injected settings, the same read-back door, the
same execution log. The check at the moment of enabling is the one call that runs before the gate, because
the hand pressing *enable* is the consent.

**Nothing reads what an action returns.** Its exit code says whether it worked, the one line it wrote to
`stderr` is what the screen shows, and nothing is undone by a press that fails. Nor is it held to the
check's two seconds — a `setup` that stands something up is allowed to take as long as it takes.

An `ask` is a config field's opposite: a value Amenbo never has. It reaches your process as
`AMENBO_ASK_<KEY>` — the key upper-cased, anything that is not a letter or a digit mapped to `_` — for that
one run, and is gone when it exits.

| An ask carries | An ask must not carry |
| --- | --- |
| `key`, `label`, `secret` | `default`, `required` — **refused**, not quietly dropped |

Those two are what an author carries over when they copy a config field, and both belong to a value with a
life after the press: a `default` is a stored answer to a question that is asked every time, and `required`
gates enabling, which no press is on either side of. A field carrying one is asking for something that
would never happen.

- **Three per press**, each key a lowercase identifier like a config key's, since it becomes an environment
  variable's stem all the same.
- **The key may not be one your `config` stores.** One name cannot mean both a value that is kept and a
  value that is never written down — which is also why the two arrive under prefixes of their own.
- **`secret` decides masking and nothing else.** Where the value is stored is not a question here.
- **A box left blank is handed over empty.** Every declared key becomes a variable, so read one per key.

**All of this is the settings form's.** The CLI calls you the way it always has, with `amenbo plugin run` —
which takes arguments a form cannot, and is not limited to what the manifest named in advance.

## Reading a record back

A payload carries an id and a kind — never the record itself. So to do anything with `id: 42`, you read it,
and the way to read is the one you already have: **run `amenbo` and ask for `--json`.** There is no second
protocol and no library to link, because a plugin is any executable in any language.

Two more variables are set on your process before it starts, and they say the things you cannot work out
from where you are standing:

| Variable | What it says |
| --- | --- |
| `AMENBO_HOME` | the store to read — the one the run happened in, not whichever one your directory would resolve to |
| `AMENBO_PLUGIN_REACH` | how far you may read: the project you fired for, as its `AMB-P-<n>` ref |

Leave them alone and `amenbo` answers correctly with nothing extra from you:

```sh
#!/bin/sh
id=$(jq -r .id)                       # the payload on stdin named a record

amenbo task show "$id" --json         # AMENBO_HOME picks the store, the window scopes the answer
amenbo task list --filter "done:false" --json
```

**Your window is the switch that let you fire.** You read the project you are observing, and anything
outside it is refused — `out_of_reach`, with a non-zero exit, never an empty result. What you can observe
is what you can read.

Do not go looking for a project directory of your own. You are started by Amenbo, not by a person standing
in a folder, so there is no `.amenbo` under you to find — which is exactly why the store is named to you
rather than left to be discovered.

This is not a sandbox, and Amenbo does not pretend otherwise: you have a shell, so nothing here is a cage.
The trust boundary is the user enabling you. What this door is for is that the content you need has a
supported way in, one that keeps working.

What you read here is the one record a hook named. Carrying the data itself off the device has doors of its
own — [Carrying data outward](carrying-data-outward.md).

## The manifest

One manifest is the unit of distribution. To be listed in the official catalog, open a pull request
against this repository adding a single [`plugins/<name>.yaml`](../plugins/).

### Required

| Field | Meaning |
| --- | --- |
| `name` | the plugin's identity — also its file name, and its directory name once installed |
| `desc` | the one-line description shown in the list |
| `author` | who wrote it (display text; it does not grant the official badge) |
| `repo` | the source repository, as `owner/name` |
| `os` | the operating systems it runs on: one or more of `macos`, `windows`, `linux` |
| `category` | a label for filtering (e.g. `workflow`) |

…plus the distributable, in **one** of two forms:

- one file everywhere (a script): `url` and `checksum`
- a separate build per platform: `assets`, each entry carrying its own `url` and `checksum`

An `assets` key is either `<os>` (every arch of that OS) or `<os>-<arch>` (`arm64` / `x64`). At install
time the running platform's `<os>-<arch>` is tried first, then its `<os>`.

### Optional

| Field | Default | Meaning |
| --- | --- | --- |
| `about` | none | a long description for your plugin's detail view, as Markdown. Without one, that view falls back to the README in your `repo`. How to write it, and in how many languages, is below |
| `official` | `false` | the official badge — decided by catalog curation, never self-declared |
| `payload_v` | `1` | the payload contract version you read |
| `min_amenbo` | none | the minimum Amenbo version you need, as semver |
| `config` | none | your settings schema: `key` / `label` / `help` / `placeholder` / `secret` / `required` / `readonly` / `type` / `options` / `default` |
| `settings` | none | the calls the settings form raises: `check`, run when the plugin is enabled, and `actions`, the buttons a user presses. Written above |
| `events` | none | the events your hook fires on. Absent means a command-only plugin |
| `agent` | none | how your plugin is driven, where an AI reads how to work here: `when` / `commands`. How much of it reaches the AI depends on the badge — see below |

An `events` entry is either the event's name or an object narrowing where it fires.

```yaml
events:
  - task.done                  # both faces, no reply
  - event: task.status_changed
    faces: [cli]               # cli / gui; cannot be empty
    reply: true                # relay the hook's advice to the caller; only with faces: [cli]
```

Unknown keys are ignored rather than rejected, so a manifest written for a newer Amenbo still parses on
an older one.

### The one thing none of your sentences may hold

Every string you write for a reader is refused if it cites an Amenbo record — your `desc` and `about`, a
config field's `label`, `help` and `placeholder`, a settings button's `label` and the boxes a press asks
for, `agent.when` and each `does`. A citation is `AMB-D-<n>`, `AMB-T-<n>` — any `AMB-`, a kind letter and a
number, standing on its own as a word — whichever case you write it in.

A number like that means something only inside the store it was issued in, and in your prose it reads as
that store's own record: *AMB-D-<n> makes this required* borrows the user's authority for a sentence Amenbo
never wrote. A number that exists nowhere does it just as well, which is why nothing is looked up — the
spelling is the whole test, and a translation is held to it exactly as the manifest is.

A `#42` or a `T-42` is left alone. Those belong to GitHub and to other trackers, and claiming them would
hijack a reference that was never Amenbo's — so your own issue number is yours to cite.

### Saying what you are for

An AI working in a folder reads one document to learn how to work there: `amenbo agent --json`. A plugin
the user has installed and enabled is part of what that document owes, so yours is named in it — and an
optional `agent` block is where you say how it is driven:

```yaml
agent:
  when: when to reach for this plugin (one line)
  commands:
    - cmd: <subcommand and arguments>
      does: what it does, and what it returns (one line)
      steps: [<the ids of Amenbo's own steps this call is a tool for>]
```

| Field | Meaning |
| --- | --- |
| `when` | the occasion to reach for you. Required once you write the block — a block naming no occasion gives a reader nothing to act on |
| `commands` | one entry per call your command face answers. Absent means none |
| `steps` | on one call: where in Amenbo's own working cycle it is a tool. Absent means nowhere in particular — see below |

**Write only your own command face.** Amenbo puts `amenbo plugin run <name> ` in front of it, from the
name it just read, so the reader receives a line they can type. Writing the whole line yourself would be
writing your own name into it, which is the one thing this shape keeps out.

**A plugin that is all observation hooks names its occasion and stops there** — no `commands`. There is
nothing for a reader to call, and saying *when this plugin matters* is still worth saying.

#### Where your call is a tool

Most of `amenbo agent --json` is Amenbo's own working practice, written as runs of steps, and each step
carries an `id`. A step can say *cut a worktree per task* while naming no command, because Amenbo's source
holds no plugin's name — so an AI told to cut has no hand until it finds yours on its own.

`steps` closes that. Name the step your call serves, and Amenbo hangs the line to type there, under
`tools`:

```yaml
commands:
  - cmd: start <task-id>
    does: Cuts a worktree for the task outside the repository, and returns the line to cd into it
    steps: [worktree.cut-per-task, worktree.run-the-line]
  - cmd: finish <task-id>
    does: Removes that worktree and its branch, once the work has been merged
    steps: [worktree.fold-it]
```

A ref is `<run>.<step>`, two names joined by one dot:

- **the run** — `agentCycle` for the backbone, or a cycle's key otherwise (`cycles.worktree` is written
  `worktree`);
- **the step** — its `id` within that run.

Read both off the document itself: `amenbo agent --json` shows every run and the `id` of every step in it.
One call may name up to four.

**Only the calling form travels.** Your `when` and each `does` stay in your own entry, where a reader meets
them as yours; a step's body is Amenbo's working practice, and Amenbo answers for every word of it. That is
why this one field is drawn the same for a third party as for an official plugin — a `cmd` is held to a
grammar, so it is the one thing that can cross without carrying a sentence with it.

**Naming a step that is not there is not an error.** The steps travel with Amenbo while your manifest stays
where it was installed, so one can be renamed or retired — and a whole cycle can be left out of the run a
reader is handed, the way `worktree` is off a git checkout. A ref that resolves to nothing hangs nowhere,
and takes nothing else with it.

#### What of it an AI actually reads

**Your sentences are relayed to the AI only if your plugin is official.** What arrives at the entry point
for a plugin that is not:

| | Reaches the AI |
| --- | --- |
| `name`, `events` | yes — Amenbo's own vocabulary, not your prose |
| each `cmd`, and the `steps` it is hung on | yes, as the line to type. Its grammar is fixed, so no sentence fits in it |
| `when`, each `does`, `desc` | **no** |

Your `desc` is not lost, it is addressed elsewhere: `plugin list` shows it whoever wrote it, because a
person reads that face. `when` and `does` reach nobody today unless the badge is yours.

**Why the line is drawn by author rather than by content.** Whether a sentence describes your plugin or
instructs the AI reading it is not something a machine can decide, and nothing you publish is read by a
reviewer before it ships — a catalog is a shelf, not a review queue. The badge is granted by catalog
curation and cannot be self-declared, so it is the one split a machine can make without ever being wrong
about which side you are on. Amenbo takes the safe side by giving the sentences no field to arrive in
rather than by filtering them: loosening this later is easy, and taking back something already relayed is
not.

**Write the block anyway.** `when` is required the moment you write one, and `cmd` is what carries your
plugin to the AI. If the rule is ever loosened, what you wrote is already in place.

Two more things worth knowing:

- **What is relayed is relayed in the language you wrote it in.** Amenbo's own entry point carries its
  wording in more than one; it holds no translation for yours.
- **Only an enabled plugin is listed.** A plugin that is not enabled would be refused if it were called,
  so it is not offered.

### Writing it in other languages

Three of the things you write are read by a **person**: your `desc`, your `about`, and the words on your
settings form — every label, beside a box or on a button, and the `help` and `placeholder` that go with one.
Those Amenbo shows in the reader's own language, when you have written one. Everything else stays in the
language you wrote it in — `agent.when` and each `does` are read by an AI, and the CLI answers in English by
contract, so neither has a translation to pick from.

**`about` is Markdown, and a YAML block scalar is what carries it.** `desc` is the one line a list draws;
`about` is the paragraphs on your plugin's detail view, and it is written the same way in the manifest and
in every translation of it:

```yaml
# plugins/mail.yaml
desc: Report what your AI did by email
about: |
  Every task your AI finishes reaches you as a mail — what it was, and how it ended.

  Bring any SMTP server you already have. For Gmail, an app password is all it takes.
```

Two rules hold it, and the manifest's copy and each translation obey both the same way:

- **2048 bytes of UTF-8, per language.** That is around a thousand Japanese characters, or two thousand
  English ones. It is a description and not your README: say what installing this does for the reader, and
  leave the rest to the repository.
- **Every link and image is an absolute `https://` URL.** A relative path is refused, and so is `http://`.
  What renders your `about` is Amenbo, out of a document the catalog serves — there is no page under which
  `./README.md` would mean anything.

A translation is **a file beside your manifest**, named for its language:

```
plugins/mail.yaml       # the manifest. This one is English
plugins/mail.ja.yaml    # Japanese
plugins/mail.de.yaml    # German
```

Write only what you are translating. Everything you leave out falls back to the manifest, so a translation
covering one field is a normal thing to publish, not a half-finished one.

```yaml
# plugins/mail.ja.yaml
desc: AI がやったことをメールで報告する
about: |
  AI がタスクを終えるたびに、何をどう終えたかがメールで届きます。

  SMTP サーバーは手持ちのもので構いません。Gmail ならアプリパスワードだけで足ります。
config:
  smtp_host:
    label: SMTP サーバー
    help: Gmail なら smtp.gmail.com です。
    placeholder: smtp.gmail.com
  events:
    label: 何を報告するか
    options:
      task.done: タスクが完了した
settings:
  actions:
    config test:                      # the base action's `cmd` is the key
      label: テスト送信
      ask:
        otp: ワンタイムコード          # the base ask's `key` is the key
```

**`config` and `settings.actions` are keyed here, not listed.** In the manifest each is a list in the order
your form is drawn in; here a field is looked up by its `key`, an option by its `value`, a button by the
`cmd` it raises, and a box a press asks for by the `key` it is handed over under. A translation carries no
order of its own, and lining the two up by position is what would break every language at once the day you
reorder the form.

| Translatable | Not translatable |
| --- | --- |
| `desc`, `about` | `name`, `author`, `repo`, `category`, and the rest of the manifest |
| a config field's `label`, `help` and `placeholder` | a config field's `key`, `type`, `default`, `readonly` — and an option's `value`, which is what travels to your plugin |
| a config option's `label` | `agent.when` and each `does` — an AI reads those, and they stay English |
| an action's `label`, and the `label` on what it asks for | `settings.check` and an action's `cmd` — calls, not text anyone is shown, so there is no key to write them in another language |

The languages are the 19 Amenbo itself is read in: `en`, `ja`, `zh-Hans`, `zh-Hant`, `ko`, `es`, `pt-BR`,
`fr`, `de`, `it`, `ru`, `hi`, `id`, `vi`, `th`, `tr`, `pl`, `nl`, `uk`.

Your translations are checked along with the manifest, by the same command — you name the manifest, and
whatever is beside it is read with it:

```sh
amenbo plugin validate plugins/mail.yaml
```

Four things are refused, all of them yours to fix while the file is still in your hands: a language from
outside that list, a field the manifest does not have, a `key`, an option `value` or an action `cmd` it
does not declare, and text past the cap its base field obeys. Nothing is quietly ignored — a label that
never appears because it was filed under a typo is the failure this door exists to prevent.

The catalog publishes the two halves the way they are read. The `desc` lines go into a
`catalog.<lang>.json` beside the listing, so a browser fetches one language and not nineteen; your `about`
and the form labels ride inside your `plugins/<name>.json` — the document fetched only for the plugin
someone opens or installs — all languages at once, so a detail view follows the reader's language, and a
settings form goes on doing so with no network at all once your plugin is installed. A long description in
nineteen languages has no business in a listing nobody has opened yet, which is why `about` is in the half
it is. Neither half is yours to assemble.

## What the asset may be

Whatever `url` serves is recognised by its leading bytes, not by the extension:

- **a `.tar.gz`** — the regular file whose **name is the plugin's own** is taken out of it
  (`<name>.exe` on Windows). A leading directory is fine.
- **the executable itself**
- **a `.zip`** — for a Windows asset only; refused on the other systems.

What comes out is laid down under Amenbo's app-data directory as `plugins/<name>/`, holding that
executable and a `manifest.json`. **A manifest cannot say what to run** — the name convention decides it.

## Signatures and verification

An install runs these in order, and writes nothing at all if either fails:

1. the **minisign signature** made with the catalog's key;
2. the **checksum** declared for this platform's distributable.

Both are over the exact bytes the URL served.

**Authors hold no keys and sign nothing.** The catalog's CI signs, and only on merge. The signature says
the bytes went through the catalog — reviewed, downloaded, digest-checked — not that the author
personally vouched for them.

*Which* key verifies it depends on **which catalog the plugin came from**: the key that ships inside
Amenbo for the official one, and **the key that catalog publishes** — pinned, fingerprint shown, when the
user ran `amenbo plugin catalog add <url>` — for a registered one. A catalog that publishes no key can be
browsed and installs nothing, and an asset on no catalog at all cannot be installed.

A pinned key stays pinned. If a catalog signs with a different key than the one you agreed to, Amenbo
does not quietly take it — it stops and says **the key changed**. Consent given to the old key does not
carry to a new one. To trust it anyway, `amenbo plugin catalog remove <url>` and `add` it again: that
round trip is what puts the new fingerprint back in front of you.

If you want to run a catalog of your own, [Running a catalog](running-a-catalog.md) is that side of it.

## Install is not enable

An install lays the binary down and runs nothing. What starts it is `amenbo plugin enable <name>`, and
doing that is itself the user's permission to run your code.

A plugin has exactly one switch and it is a project's: each project answers for itself, and a user is
never shown two switches for one plugin.

Enabling also checks compatibility:

- `payload_v` must **match** — it moves only on a breaking change, so a difference in either direction
  means the two sides do not share a contract;
- the running Amenbo must be at or above `min_amenbo`.

A `required` setting still empty refuses the enable, and so does your own `check` when it does not say yes.

## Check it before you ship it

The validation Amenbo runs at its door is available to you:

```sh
amenbo plugin validate plugins/<name>.yaml
```

It prints every problem it finds at once and exits non-zero if there are any. The catalog's pull-request
gate runs the very same check.

## When nothing happens

A hook is fire-and-forget, so its failure surfaces nowhere the caller was listening. The execution log is
what answers *why did nothing happen*:

```sh
amenbo plugin log          # the last runs of every plugin
amenbo plugin log <name>   # narrowed to one
```

One line per run: when, which plugin, on which event, how it ended, its exit code and how long it took. A
run that did not end cleanly is followed by what the plugin wrote to **stderr** — which is exactly why
your diagnostics belong there.

## Getting listed

Open a pull request adding your one manifest file to this repository. The full field reference, a
worked example, and the review checklist live in [CONTRIBUTING.md](../CONTRIBUTING.md).
