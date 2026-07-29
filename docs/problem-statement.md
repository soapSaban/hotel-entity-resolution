# AI Engineering Intern: Take-Home Assignment

## Build a Mini Hotels Layer

### Context

Away is an AI-powered travel concierge. We build our hotels product on top of
multiple suppliers. Each supplier has its own hotel database: the same
physical hotel appears in each with a different ID, a differently-written
name, a slightly different address and coordinates, different photos, and a
different amenity vocabulary. Before we can compare prices or show one clean
page per hotel, we must merge these feeds into a single **canonical** layer:
one authoritative record per real-world hotel, stitched together from all
its supplier versions. (That's what "canonical" means everywhere below.)

That is this assignment, in miniature, on real data.

The internship is paid: **₹50,000/month stipend**.

### What you get

Download the dataset:
<https://storage.googleapis.com/hotels-assignment-assets-2c4f/assignment/hotels-assignment.zip>

Two real supplier exports for Bangalore, call them Supplier A and
Supplier B, with the same schema:

| File | Rows | Schema |
|------|------|--------|
| `supplier_a.csv` | ~3,400 | `id,name,address,lat,lon,stars,amenities,image_urls` |
| `supplier_b.csv` | ~3,800 | same |
| `rooms_a.csv` | ~3,900 | `hotel_id,room_id,name,amenities` |
| `rooms_b.csv` | ~17,300 | same |

Both files are near-full-market feeds for the same city, so brute-forcing
every A×B pair (~13M) through anything expensive is off the table. How you
generate match candidates is a core part of the problem.

The rooms files list each hotel's room offerings (`hotel_id` links to the
hotel files). Room naming is where supplier chaos peaks ("Deluxe, Twin" vs
"Twin Deluxe Room w/ Breakfast"), and the two suppliers disagree about
rooms in deeper ways too: coverage (one lists rooms for only part of its
hotels), granularity (the same hotel can have 2 room entries on one side
and 100+ on the other), and what a "room" even is. That's real supplier
data; work with it honestly. Fields can be empty; real feeds are like
that. `amenities` and `image_urls` are pipe-separated; each supplier uses
its own wording (that's part of the problem). Image URLs point to a public
CDN; hotlink them, don't rehost.

### Your job

1. **Resolve & merge.** Build a pipeline that merges the two hotel files into
   one canonical hotel list: each physical hotel appears once, with merged
   content, links back to its source row(s), and a match confidence. Any
   approach: rules, fuzzy matching, embeddings, LLMs, image signals, or a
   combination. Keep an eye on cost: don't push every A×B pair through
   an LLM.
2. **Map the rooms.** For hotels you've matched, align their rooms across
   the two suppliers and normalize what the messy names encode (bed type,
   occupancy, meal plan, view) into structured attributes. Room names are
   harder than hotel names; that's the point. If a room exists on only one
   side, leave it unmatched.
3. **Ship the API.** Wrap the merged layer in a small web service (any
   language/framework). Required endpoints, at minimum:
   - `GET /hotels?search=...` returns a search/list of canonical hotels
   - `GET /hotels/{id}` returns one canonical hotel: merged content, both
     source records, matched rooms with their normalized attributes and
     per-match confidence, and near-miss candidates where you weren't sure
   Your README must have **clear instructions to run it**, plus a couple
   of example requests. One command (`docker compose up`, `uv run ...`) is
   the gold standard. Document the contract (README examples or an OpenAPI
   sketch). Think from the traveler's side: this is the data a hotel page
   gets built from. A good test: could someone pick a hotel using your
   `/hotels/{id}` response alone? Deploying it to a free host (Render,
   Railway, Fly, etc.) and a UI on top are both **good to have**, not
   required.
4. **Write-up (1 page).** Your approach and what you discarded; how you
   convinced yourself the matching works (whatever form that took); total
   API spend in dollars; what breaks first at 200,000 hotels across 3
   suppliers.

### External data (optional, encouraged)

You may enrich with open data (OpenStreetMap, Wikidata) or official APIs
(e.g. Google Places). Targeted use on hard cases reads as judgment; bulk
resolution of the whole file misses the point. Only legitimate sources; cache
and commit what you fetch so your pipeline reproduces without your keys.

### Scope is fixed

The only optional piece is the UI above. If you finish early, polish the
core: a better API contract, more honest confidence. We'd rather get a
small thing that fully works than a big thing that half-works.

### Constraints

- **Time-box:** roughly 8-10 focused hours.
- **AI assistants:** allowed and expected. You must understand and be able to
  defend every line you submit.
- **Cost:** no fixed budget, but report your total API spend, even if
  it's $0. We judge how well you spent, not how much.

### Submission

A **private** git repo shared with us.
(Private for one honest reason: we reuse this assignment, and a public
solution would spoil it for the next candidate, so please keep the repo,
the dataset, and your write-up off the public internet.) The repo contains:

- your code;
- a `README.md` with exact, tested steps to run the API (one command is
  the gold standard), plus example requests;
- your canonical output artifact, as JSON or CSV, with source-row links
  (provenance) and confidence at both hotel and room level;
- your write-up;
- your deployed URL, if you went for the good-to-have.

Send your repo link (and deployed URL, if any) to **careers@heyaway.ai**
and we'll reply with the account to invite to your private repo. The first
thing we do is run your API from your README, so make that painless.

### How we evaluate

If we can't get your API running by following your README, the rest
doesn't get graded. Beyond that:

| Weight | Criterion |
|--------|-----------|
| 40% | Working API: runs from the README, endpoints answer, merged hotels and matched rooms are queryable, provenance and confidence truthful |
| 35% | Matching quality & judgment: hotel and room level; signal choice; candidate generation before expensive comparison; honest confidence; sane spend |
| 25% | Write-up, cost/scaling thinking, code hygiene & reproducibility |

In the debrief we'll curl your API together (and click your UI, if you built
one), pick a handful of your hotel merges and room matches for you to defend
(including the ones you got wrong), and ask what you cut to finish in time.

### Questions

If something is ambiguous, make a reasonable assumption and state it in
your write-up; handling ambiguity is part of the job. If something looks
genuinely broken (a file won't parse, an image link is dead), email
careers@heyaway.ai; that's a bug, not an ambiguity.

We know this is a real chunk of work. It's also a faithful slice of what
this internship actually is. If you enjoy building it, that's the strongest
signal there is. Looking forward to what you build.
