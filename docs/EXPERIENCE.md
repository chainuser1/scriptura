# One app for every kind of reader (desktop experience plan)

The same app serves five kinds of people. It never asks who you are: the Home screen, the search results and the
reading view each expose the simple path first and the deeper tools one step away.

| Reader | What they need | How the app serves them |
|---|---|---|
| **New to scriptures**, wants answers | plain-language answers, no jargon, no dead ends, orientation | "Ask" box with starter questions, results explained in words ("showing passages about..."), a short "Start here" guide that explains each volume neutrally, verse context one click away, nothing assumes prior knowledge |
| **Enthusiast reader** | a beautiful, calm reading view; continuity | printed-book reading column, light/sepia/dark, size and width controls, continue where you left off, daily verse, bookmarks and highlights |
| **Hobbyist** | explore, collect, follow threads | similar verses, topic starters, highlights in colours, notes, collections of bookmarks, export to Markdown |
| **Scholar** | exactness, comparison, citation | exact-phrase search with totals, scope by volume, parallel reading (second language, including Greek), precise references, range copy with citation, notes with export, keyboard-first (Ctrl+K), reference jump in any served language |
| **Just trying out** | instant payoff, no commitment | Home shows value immediately, one-folder install that auto-detects every pack, starter questions, no account, no network, nothing to configure |

## Principles

1. **Offline and private.** No account, no network after install, notes and bookmarks stay on the device (`user.db`).
2. **Say what the app understood.** A reference jump, a person question, an exact phrase and a meaning search are
   announced as such, and can be changed.
3. **Never block on setup.** Reading works with the content release alone; search needs the search data; the
   word-level index is optional. Each missing piece is explained with the one action that fixes it.
4. **Desktop first, but adaptive.** A sidebar and two panes at 900 px and wider, one pane below that, no content
   wider than a comfortable line.
5. **Keyboard complete.** Everything reachable by keyboard; shortcuts listed in Settings.
6. **Neutral about tradition.** Descriptions of the volumes state what each is and who holds it; they do not argue.

## Structure

- **Home**: Ask box and starter questions, continue reading, verse of the day, recent searches, "Start here".
- **Read**: book and chapter browser beside the reading column; verse actions; parallel language; themes.
- **Search**: Meaning / Exact phrase, scope, interpretation chips, results beside a live passage preview.
- **Trails**: a calm, endless stream of related verses (see below); started from Home, a verse's menu, or a search result.
- **Study**: Bookmarks, Highlights, Notes, History, Trails; export and backup.
- **Settings**: Look and feel (see below), language, shortcuts, data packs, about and licences.
- **Aa** (reader header): the same looks and the quick controls without leaving the page.
- **Ctrl+K**: command bar: jump to a reference, or ask a question.

## Looks

People arrive with different habits (a book, an e-reader, a web page, an app), so the reading surface is a set of independent
controls plus seven named bundles of them. Controls: page colour (nine, all at least 7:1 contrast), typeface (Source Serif,
Literata, Inter, Atkinson Hyperlegible), text size, line spacing, line width, verse numbers (inline, in the margin, hidden),
layout (flowing text or one card per verse), and "dim the page after dark" (the Night colours from 7 pm to 6 am, by the
clock; no location is read). Looks: Book (default), E-reader, Web, App, Study desk, Night, Large print. Picking a look sets
every control; changing any control afterwards shows "Custom". Nothing here changes what a verse says.

## Trails

A trail is one verse at a time, in the reading face, with two buttons (Skip, Like) and two quiet text actions ("Less like this",
"Why this verse"). The stream learns from the reader's feedback on that trail only, deterministically: reopening a trail
reproduces it. Tune sets up to two moods (Comfort, Hope, Courage, Gratitude and joy, Repentance, Peace, Wisdom, Awe, Warning,
Service), the volume, and how far to wander. "Why this verse" lists the strongest real reasons (shared themes with the family and
gene breakdown, mood match, shared words, shared people and places, shared study questions, fit with likes, variety) and never
invents one. A thin return bar brings the reader back to the trail from any screen; "Your reading taste" (Study > Trails) says
what the likes lean toward, computed on the device, with Reset and Undo. Keyboard (desktop and tablet only): L like, S skip,
D less like this, W why, T tune. No text-to-speech, no account, nothing sent anywhere.

## Fair across volumes

Across the canon, Similar verses, meaning search and Trails give every volume a fair chance: a volume no longer fills the list
only because it sounds like the verse or question (its style, language or era). The closest matches still lead. Nothing to
switch on; one volume, one book or one chapter works exactly as before. (Volume balance, docs/DEVLOG.md 2026-10-14.)

## Out of scope for now (and why)

Cross-references, topical guide, AI summaries and other study aids were in the retired legacy databases; their rights and
quality were never reviewed, so they are not offered. They can return as separately labelled optional packs.
