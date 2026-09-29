# Clapback

**Clap once in a room. Clapback tells you why it sounds the way it does and
what to change.**

Clapback is a room-acoustics app for a phone. You say what the room is for,
give its size, tap what it's made of, and measure it: with a hand clap for a
quick answer, or with a test sweep from a speaker for an accurate one. It
reports the reverberation time against the target from the standards, draws
the charts an acoustician would look at, shows the room in 3D (where early
reflections land, where to sit, how a bass note fills the volume, and a
replay of the clap), and plans a treatment that fits your budget, priced with
real products that Tavily finds in shops and the engine checks against each
shop's page.

**Live app:** https://clapback-alpha.vercel.app (installable on Android and
desktop; open it on a phone for the microphone and camera features).

Built for the [Nebius x NVIDIA Global AI Hackathon](https://nebiusglobalaihackathon.devpost.com/).
The language model is **NVIDIA Nemotron 3 Super** on **Nebius Token
Factory**, and it never produces an acoustic number (see [The rule](#the-rule)).

<p align="center">
  <img src="docs/images/result-verdict.png" width="270" alt="Verdict: RT60 against the target range">
  <img src="docs/images/chart-decay.png" width="270" alt="Decay curves per octave band">
  <img src="docs/images/3d-reflections-plan.png" width="270" alt="3D view: early reflections and the plan in place">
</p>

## Contents

- [What it does](#what-it-does)
- [The results, chart by chart](#the-results-chart-by-chart)
- [How it works](#how-it-works)
  - [The rule](#the-rule)
  - [Measuring: clap or sweep](#measuring-clap-or-sweep)
  - [From a recording to decay curves](#from-a-recording-to-decay-curves)
  - [ISO 3382-1 values](#iso-3382-1-values)
  - [Room model and calibration](#room-model-and-calibration)
  - [Room modes, maps and targets](#room-modes-maps-and-targets)
  - [Early reflections, placement and where to sit](#early-reflections-placement-and-where-to-sit)
  - [The clap replay](#the-clap-replay)
  - [Treatment plans](#treatment-plans)
  - [Real prices from shops (Tavily)](#real-prices-from-shops-tavily)
  - [Measuring the room with the camera](#measuring-the-room-with-the-camera)
- [NVIDIA Nemotron on Nebius Token Factory](#nvidia-nemotron-on-nebius-token-factory)
- [Accuracy and tests](#accuracy-and-tests)
- [Limits](#limits)
- [Using the live app](#using-the-live-app)
- [Running it yourself](#running-it-yourself)
- [API](#api)
- [Project layout](#project-layout)
- [References](#references)
- [License](#license)

## What it does

Five short steps, one task per screen:

1. **Use.** Podcast or calls, playing music, mixing, studying or teaching,
   movies, or just curious. This sets the target.
2. **Size.** Presets and steppers, measured with the phone camera (any
   phone), or an AR scan of the floor corners (phones with ARCore).
3. **Materials.** Floor, walls, ceiling, how furnished it is, windows, plus
   free text ("a double bed and a big bookshelf") that Nemotron turns into
   absorbers from the materials table.
4. **Measure.** A clap (just the phone) or a 6-second test sweep played by a
   speaker 2 m away.
5. **Results.** Verdict, charts, maps, ISO values, and a budgeted plan.

<p align="center">
  <img src="docs/images/screen-goal.png" width="200" alt="Choose the room's use">
  <img src="docs/images/screen-size.png" width="200" alt="Room size, with camera measuring">
  <img src="docs/images/screen-surfaces.png" width="200" alt="Materials">
  <img src="docs/images/screen-sweep.png" width="200" alt="Measure with a clap or a test sweep">
</p>

## The results, chart by chart

The screenshots in this section come from two real claps recorded with an
Android phone in a furnished living room, sized with the app's "Living room"
preset (5.5 × 4.5 × 2.6 m), and analysed for "Podcast or calls". The two
charts marked *synthetic* come from a sweep through the synthetic test room
in `tests/test_sweep.py`, because those charts need a sweep.

### Verdict and key figures

<img src="docs/images/result-verdict.png" width="360" align="right" alt="Verdict card">

The headline compares the **mid-frequency reverberation time** (RT60, the
mean of the 500 Hz and 1 kHz octave bands) with the target range for the
chosen use: *Within target*, *Too reverberant* or *Too dry*. The card names
the standard the target comes from and defines RT60 in one line: the time a
sound takes to fade by 60 dB once it stops.

Below it: C50 (speech clarity), D50 (definition), the room volume, the
Schroeder frequency (below it the room behaves as separate resonances) and,
with several measurements, how well they agree.

<br clear="right">

<img src="docs/images/result-stats.png" width="360" alt="Key figures">

### RT60 per octave band

<img src="docs/images/chart-rt60.png" width="360" align="right" alt="RT60 per band">

RT60 in each octave band from 125 Hz to 4 kHz, with the target range shaded.
Low bands from a single clap are drawn faded: a clap carries little energy
at 125 Hz, so one clap is a rough measurement there. A sweep, or more claps,
makes them solid.

<br clear="right">

### Decay curves

<img src="docs/images/chart-decay.png" width="360" align="right" alt="Decay curves">

The energy left in the room after the sound, per octave band, by Schroeder
backward integration, drawn over the raw broadband energy (grey). RT60 is
read from the slope. A straight line means one decay rate. A bend means two,
typically a flutter echo between parallel walls or a coupled space such as
an open door to a hallway.

<br clear="right">

### Spectrogram of the decay

<img src="docs/images/chart-spectrogram.png" width="360" align="right" alt="Spectrogram">

Each frequency dying away over time on a 1/6-octave axis from 50 Hz to
10 kHz, with 80 dB of range. Room modes show as long streaks at the bottom.
Anything that isn't the room shows too: in this real recording, a second
sound arrives at 0.7 s. In a sweep measurement, a knock during the sweep
shows as a descending streak, which is how to spot a spoiled measurement.

<br clear="right">

### Room modes

<img src="docs/images/chart-modes.png" width="360" align="right" alt="Room modes">

Every resonance of a rectangular room up to 300 Hz: axial (between two
opposite surfaces, the strongest), tangential and oblique, with the
Schroeder frequency marked. Below the chart are the axial modes under the
Schroeder frequency, grouped when they fall within 5 Hz of each other, with
their musical note. These are the notes that boom.

With a sweep, the measured response is drawn over the modes (*synthetic
room*, below), so peaks and dips can be matched to the resonances that cause
them.

<br clear="right">

<p>
  <img src="docs/images/chart-modes-measured.png" width="360" alt="Modes with the measured response (synthetic room)">
  <img src="docs/images/chart-response.png" width="360" alt="Frequency response (synthetic room)">
</p>

### Frequency response (sweep only)

The level at the microphone per frequency, from the first 0.5 s of the
impulse response, smoothed to 1/6 octave, with 0 dB at the 500 Hz–2 kHz mean
(*synthetic room*, above right). It includes the speaker and the phone's
microphone, so the useful reading is the shape in the shaded modal region,
not the absolute level.

### The room in 3D

A 3D model of the room, with the walls lettered A, B, C… (the plan's
positions refer to them), and four layers. After a plan, a switch shows each
layer **now** or **with the plan**, with its pieces placed in the room.

<p>
  <img src="docs/images/3d-reflections.png" width="360" alt="Early reflections on the surfaces">
  <img src="docs/images/3d-reflections-plan.png" width="360" alt="The same with the plan's pieces in place">
</p>

- **Reflections.** Where the sound bounces from the source (orange) to the
  listener (blue) in the first 20 ms, painted on the walls, floor and ceiling,
  with the strongest paths drawn and listed with their position, delay and
  level. For a podcast the listener is the mic, 25 cm in front of the talker,
  who faces the nearest wall (a desk against the wall); otherwise it is the
  best seat. With the plan, the pieces sit on the hot spots and the list says
  which reflections they cover and by how much.
- **Speech clarity.** An STI estimate on a plane at ear height for someone
  talking from the orange dot, now or with the plan's RT.
- **Bass.** How loud one low note is, either on a horizontal slice at any
  height or in the whole volume: red within 3 dB of the loudest point, blue
  15 dB or more below it, so the lobes and the nodal planes show. The slider
  or the play button sweeps the note.
- **Where to sit.** How even the bass is at every spot at ear height, from
  30 Hz to the Schroeder frequency, with the most even spot at least 0.5 m
  from the walls marked, and how it compares with a typical spot. It costs
  nothing and helps rooms that are too dry for a plan too.

<p>
  <img src="docs/images/3d-bass-volume.png" width="360" alt="One bass note in the whole volume">
  <img src="docs/images/3d-seat.png" width="360" alt="Where to sit">
</p>

**Replay the clap** runs sound particles from the source, bouncing and
fading at every surface, ten times slower than real, with the level shown
as they go: now, or with the plan's pieces absorbing with their own
coefficients ([how](#the-clap-replay)).

<img src="docs/images/3d-replay.png" width="360" alt="Clap replay with the plan's pieces">

### All values (ISO 3382-1)

<img src="docs/images/table-iso.png" width="360" align="right" alt="ISO 3382-1 table">

EDT, T20 and T30 (reverberation times from different parts of the decay),
C50 and C80 (early-to-late energy ratios, higher is clearer) and D50 (the
share of energy in the first 50 ms), per octave band, averaged over all
measurements. After a sweep there is also a button to download the impulse
response as a WAV file, to open in Room EQ Wizard or use in a convolution
reverb.

<br clear="right">

### Treatment plan

<img src="docs/images/plan.png" width="360" align="right" alt="Treatment plan">

Pick a budget and Nemotron tries plans with tool calls, while the acoustics
engine validates and scores every one. The prices are real: while you read
the results, Tavily finds products in Spanish shops, Nemotron reads their
pages, and the engine keeps only the ones whose price and size it can find
on the page ([how](#real-prices-from-shops-tavily)). The plan then comes in
whole products, "16 × €10.00 curtains", with a link to each and the passage
from the shop's page that shows its price and size.

The result shows the RT60 per band before and after against the target, the
products and their cost, a short explanation, and "How it decided": every
plan Nemotron tried and what the engine said about it. In this example the
real prices made rugs and curtains cheaper than panels, so the plan reaches
the target for €219. A room that is already too dry gets no plan, since
everything on the list absorbs sound.

<br clear="right">

## How it works

```mermaid
flowchart LR
  subgraph Phone["Phone (installable web app)"]
    S[Camera + tilt,<br>or AR scan] --> A[Use, size, materials, notes]
    A --> B{Measure}
    B -->|clap| C[Raw PCM,<br>voice processing off]
    B -->|sweep| D[Sweep from a speaker,<br>recorded by the phone]
  end
  subgraph Server["Server (Python, FastAPI)"]
    E[sweep.py<br>deconvolution to an impulse response]
    F[decay.py<br>bands, Schroeder, EDT/T20/T30,<br>C50/C80/D50, chart data]
    G[reverb.py, modes.py, maps.py,<br>targets.py, treat.py]
    H[Nemotron 3 Super on Nebius<br>intake, planner, optimizer]
    T[Tavily Search + Extract<br>shop pages]
    P[shopper: Nemotron reads the pages<br>shop.py: checks every number<br>against the page]
  end
  C --> F
  D --> E --> F
  F --> G
  A -. notes .-> H
  H -- material ids, tool calls --> G
  G -- scores, predictions --> H
  T --> P -- real €/m² --> H
  G --> R[Results: verdict, charts, 3D maps, plan]
```

The server is stateless. `/api/clap` and `/api/sweep` return the per-band
results, and the app sends them back with every `/api/analyze` and
`/api/plan` request, which keeps it within a free serverless tier.

### The rule

**The models never produce an acoustic number.** Nemotron picks from the
materials table, decides whether another measurement is worth it, and calls
the engine with candidate plans. The engine computes every RT, clarity value
and prediction, and the measurements check the engine. Every agent has a
deterministic fallback, so the app still works if a model call fails.

### Measuring: clap or sweep

**Clap.** The app records 5 s from the microphone as raw PCM through an
AudioWorklet (no lossy codec), with the browser's echo cancellation, noise
suppression and gain control switched off, since they eat the reverberant
tail. It stores the settings the phone actually applied with every clap. A
quick on-device check says right away whether the clap was clear enough; the
analysis happens on the server.

**Test sweep.** An exponential sine sweep (Farina 2000), 6 s from 40 Hz to
16 kHz at −6 dBFS:

$$x(t) = \sin\left(2\pi f_1 L \left(e^{t/L} - 1\right)\right), \qquad L = \frac{T}{\ln(f_2/f_1)}$$

The recording is convolved with the inverse filter: the time-reversed sweep
with a 6 dB/octave tilt ($e^{-t/L}$) that undoes the sweep's pink spectrum.
The result is the room's impulse response. Harmonic distortion from a small
speaker lands before the linear response and is cut away, and the
deconvolution gains tens of dB of signal-to-noise over a clap.

The sweep is defined in continuous time, so the server rebuilds exactly the
signal the player produced at the recorder's sample rate, even when a laptop
plays at 44.1 kHz and the phone records at 48 kHz. Where the sweep starts in
the recording doesn't matter, because the deconvolution finds it. A recording
is rejected, with a message saying why, if the deconvolved peak isn't 30 dB
above the median (no sweep), if the sweep started before the recording, or
if less than 0.8 s of decay follows it.

The sweep has to come from a speaker away from the phone: a Bluetooth
speaker connected to the phone, or another device with
[`/speaker.html`](https://clapback-alpha.vercel.app/speaker.html) open. The
phone's own speaker sits next to its microphone, and at 1–2 cm the direct
sound is about 30 dB above the reverberant field, which hides the decay.

### From a recording to decay curves

`clapback/acoustics/decay.py` runs the same pipeline on a clap and on an
impulse response:

1. **Onset:** the rise into the loudest 10 ms frame. Taking the loudest
   event rather than the first loud one keeps talking or a knock before the
   clap from being analysed as the clap.
2. **Octave bands** from 125 Hz to 4 kHz: a 3rd-order Butterworth band-pass,
   applied forwards and backwards (zero phase).
3. **Noise floor:** where the decay meets the background, found by a
   simplified Lundeby iteration (fit the decay down to 10 dB above the noise,
   extrapolate to the noise level, re-estimate the noise after the
   crosspoint). The energy after the crosspoint is cut, and the energy the
   exponential tail would have carried is added back.
4. **Schroeder backward integration:**
   $E(t) = \int_t^{\infty} h^2(\tau)\, d\tau$, in dB relative to $E(0)$.
5. **Fits:** a straight line over part of the curve, extrapolated to −60 dB.
   Each fit is used only if the band has the dynamic range for it (the fit
   range plus a 10 dB margin, as ISO 3382-2 recommends), the line fits well
   ($r^2 \ge 0.95$) and the result is plausible for a room (0.05–5 s):

| Value | Fit range | Needs a peak-to-noise range of |
|---|---|---|
| EDT | 0 to −10 dB | 20 dB |
| T20 | −5 to −25 dB | 35 dB |
| T30 | −5 to −35 dB | 45 dB |

The RT reported per band is T30 if available, then T20, then EDT. With
several measurements, each value is averaged per band over the valid ones.

For the charts the same step returns the decay curve per band in 5 ms
steps, the broadband energy-time curve in 2 ms frames, and a spectrogram
(a Hann window of 2048 samples at 48 kHz, a 10 ms hop, averaged into
1/6-octave bands and sent as 0–255 levels over 80 dB).

### ISO 3382-1 values

With $t_0$ at the direct sound (the first sample within 20 dB of the peak,
as ISO 3382-1 defines it) and the decay curve normalised to the total
energy, the early/late ratios come straight from the curve:

$$C_{50} = 10 \lg \frac{\int_0^{50\,\mathrm{ms}} h^2\,dt}{\int_{50\,\mathrm{ms}}^{\infty} h^2\,dt}, \qquad
D_{50} = \frac{\int_0^{50\,\mathrm{ms}} h^2\,dt}{\int_0^{\infty} h^2\,dt}$$

C80 is C50 with 80 ms. They need 20 dB of range, and values beyond ±30 dB
(no tail, or no direct sound) are dropped.

### Room model and calibration

`reverb.py` predicts RT per band from the room: Sabine, or Eyring when the
mean absorption is high. It adds air absorption $m$ per band (from
ISO 9613-1, at about 20 °C and 50 % relative humidity) and a furnishing term
for the furniture, beds and clothes that the surfaces don't describe:

$$T_{\mathrm{Sabine}} = \frac{0.161\,V}{A + 4mV}, \quad A = \sum S_i\,\alpha_i \qquad\qquad
T_{\mathrm{Eyring}} = \frac{0.161\,V}{-S\ln(1-\bar\alpha) + 4mV}$$

Absorption coefficients come from `data/materials.json`: 21 materials with
typical published values from standard tables (the file names its sources
and says they are starting points). Free-text notes add patches of matching
materials through the intake agent. `calibrate` then compares the prediction
with the measurement per band and returns the factor the absorption must be
scaled by to match. The measurement always wins: plans start from the
measured absorption, not from the model.

### Room modes, maps and targets

**Modes** of a rectangular room, every combination up to 300 Hz, and the
**Schroeder frequency**, above which modes overlap into a diffuse field:

$$f_{n_x n_y n_z} = \frac{c}{2}\sqrt{\left(\frac{n_x}{L_x}\right)^2 + \left(\frac{n_y}{L_y}\right)^2 + \left(\frac{n_z}{L_z}\right)^2}, \qquad
f_S = 2000\sqrt{T/V}$$

**Maps** (`maps.py`), on a 0.25 m grid at 1.2 m:

- STI estimate: the modulation transfer of an exponential decay (Schroeder
  1981), mixed with the direct sound by the direct-to-reverberant ratio,
  then the IEC 60268-16 male weighting. It assumes no background noise, so
  it is an upper bound, and the app calls it an estimate.
- Bass: a modal sum for a rectangular room with a point source. The app runs
  the same formula in JavaScript so the frequency sweep can animate; the
  Python version is the tested reference.
- C50 from Barron's revised theory (Barron & Lee 1988), from the direct,
  early and late energy at distance $r$ for volume $V$ and RT $T$. It is in
  the API response but not drawn yet.

**Targets** for the mid-frequency RT, ±20 % (`targets.py`):

| Use | Target | Source |
|---|---|---|
| Studying or teaching | $\max(0.3,\ 0.32 \lg V - 0.17)$ s | DIN 18041, group A3 |
| Playing music | $0.45 \lg V + 0.07$ s | DIN 18041, group A1 |
| Mixing / studio | $0.25\,(V/100)^{1/3}$ s | EBU Tech 3276 |
| Podcast or calls | 0.30 s | common practice for voice rooms |
| Movies and TV | 0.35 s | common practice for home cinema |
| Just curious | 0.50 s | a comfortable furnished room |

### Early reflections, placement and where to sit

`clapback/acoustics/geometry.py`.

**Early reflections** by image sources (Allen & Berkley 1979 for boxes,
Borish 1984 for any polyhedron). The surfaces are the walls of the floor
polygon, extruded to the ceiling, plus the floor and the ceiling. The
source mirrored in one surface, or in two in turn, gives a specular path,
which is real only if every reflection point lies on its surface. Each path
gets its delay after the direct sound and its level relative to it, with each
surface's mid-band absorption (patches included, by area):

$$L = 20 \lg \frac{r_{\mathrm{direct}}}{r_{\mathrm{path}}} + 10 \lg \prod_i (1 - \alpha_i)$$

Orders 1 and 2 are kept, down to 20 dB below the strongest. The app paints
each surface with the power sum of the paths landing on it, spread over
about a panel's size (σ = 0.3 m).

**Placement.** `place()` turns every item of the plan into pieces of the
real product's size (or a typical size) and puts them one at a time where
they cover the most reflection energy, without overlapping: panels on walls
or ceiling (then around ear height; thick panels also favour corners),
curtains hanging from a rail, bookshelves standing on the floor, rugs on the
floor. `reflections_after()` gives each path the absorption of the piece it
lands on. The plan lists the positions from the lettered walls.

**Where to sit.** For every point of a 0.25 m grid at ear height, the modal
response of a rectangular room (the same modal sum as the bass map) at 48
frequencies from 30 Hz to the Schroeder frequency; its standard deviation in
dB says how uneven the bass is there. The most even point at least 0.5 m
from every wall is the recommended seat.

### The clap replay

`web/acoustics3d.js`, tested with Node. 1,500 particles leave the source in
random directions at 343 m/s, reflect specularly off the room's surfaces,
and keep (1 − α) of their energy at every hit. The surfaces' absorption is
scaled so the particles decay with the **measured** RT60, which spreads
furniture and anything else the model misses over the surfaces: first from
Eyring, then corrected with a quick run of 500 particles, because a box with
specular reflections decays about 12 % slower than Eyring assumes (the field
isn't fully diffuse). With the plan, a particle that hits a piece loses that
piece's absorption instead. Specular particles describe sound above the
Schroeder frequency; the bass is modal, which the Bass layer shows.

### Treatment plans

`treat.py` decides whether a plan is allowed and what it would do. The
baseline is the **measured** absorption, so furniture the model doesn't know
about is already included:

$$A_{\mathrm{now}} = \frac{0.161\,V}{T_{\mathrm{measured}}} - 4mV, \qquad
\Delta A = \sum S_i\,(\alpha_{\mathrm{treatment}} - \alpha_{\mathrm{covered}}), \qquad
T_{\mathrm{new}} = \frac{0.161\,V}{A_{\mathrm{now}} + \Delta A + 4mV}$$

Validation checks each item's placement (a rug goes on the floor, curtains
over glass or on a wall), its area against what the room has (each item can
cover at most a set fraction of its surfaces, and curtains no more glass
than there is), and the total against the budget. Prices per m² come from
real products (next section); the catalogue (`data/treatments.json`) keeps
typical prices for any type without one: 5 cm panels at €30/m², 10 cm
panels at €50/m², heavy curtains at €25/m², a thick rug with underlay at
€30/m², and a filled bookshelf at €60/m².

After Nemotron finishes, `shop.to_units` rounds each item to whole
purchases of the real product, removes purchases while the plan is over
budget or over the space, and the engine predicts the result again from the
final areas.

### Real prices from shops (Tavily)

`clapback/shop.py` and `clapback/agents/shopper.py`. The app calls
`/api/prices` as soon as the results show, and it takes about 10–30 s, so
the prices are usually ready before you press *Make my plan*. For each of
the five treatment types:

1. **Tavily Search**, twice in parallel, both returning the page text: an
   advanced search limited to shops whose product pages carry a fixed price
   and a size (IKEA, JYSK, Kave Home, Conforama, Zara Home for rugs,
   curtains and shelves; acoustic shops for panels), and an open search
   biased to Spain. Marketplaces, sites that block extraction, and country
   domains outside the euro area are dropped. For 5 cm panels two shop
   pages with fixed prices per size are always read too, since searches for
   panels mostly find "from €X" configurators.
2. **Tavily Extract** fetches the text of the results that came back
   without it. Only pages that show a price in euros and a size are kept,
   up to six.
3. **Nemotron reads each page separately** (one call per page, in parallel;
   with several pages at once it tended to return nothing). It copies, it
   doesn't compute: the name, the price exactly as written, the size numbers
   and their unit as written, the pieces per pack, and one to three passages
   copied from the page that show them.
4. **The engine checks every product** (`shop.verify`):
   - every passage must be on the page, character for character (after
     collapsing whitespace);
   - the price must be on the page and in a passage, and every size, pack
     and thickness number must be in a passage;
   - panels must have the treatment's thickness (3.5–7 cm for "5 cm",
     8–15 cm for "10 cm");
   - the engine converts mm and m to cm and works out the price per m² of
     treated surface, which must be plausible for the kind of product.
     Curtains count half their fabric, because the absorption data for heavy
     curtains assumes them hung at double fullness.
5. The cheapest checked product of each type prices the plan. Results are
   cached for six hours per server instance.

Without a Tavily key, or when no product of a type passes, that type uses
the catalogue's typical price and the plan says so next to the item. A
discovery for all five types uses about 25 Tavily credits and roughly 30
short Nemotron calls.

### Measuring the room with the camera

<img src="docs/images/camera-geometry.svg" width="520" alt="Camera measuring geometry">

**Any phone** (`web/measure.js`): hold the phone in front of your eyes and
put the cross in the middle of the camera view on the line where a wall
meets the floor. The accelerometer gives the camera's angle below the
horizon, θ. With the phone's height $h$ (your height minus about 15 cm),
that wall is $d = h/\tan\theta$ away, and the ceiling line of the same wall
gives the height. Five taps (the front wall's floor and ceiling lines, then
the back, left and right walls) give length, width and height. The cross
turns green when the phone is steady, and if furniture hides a wall's floor
line, its ceiling line works too. Three centimetres of error in $h$ is 2 %
on every distance, and facing a wall 10° off square adds 1.5 %.

**AR scan** (`web/scan.js`, Chrome on ARCore phones): WebXR hit-testing
finds the floor. You tap each corner, and any room shape works; a nearly
rectangular outline snaps to a rectangle so modes and maps apply. For the
height, you aim at the ceiling right above a marked corner. Hit-testing
can't find ceilings, but the corner's vertical line is known, so the height
is where the view ray passes over it.

## NVIDIA Nemotron on Nebius Token Factory

All model calls go through Nebius Token Factory's OpenAI-compatible API
(`clapback/llm/nemotron.py`), using **NVIDIA Nemotron 3 Super**
(`nvidia/nemotron-3-super-120b-a12b`).

| Agent | What Nemotron does | How it's kept honest | Code |
|---|---|---|---|
| Intake | Turns the user's own words into material ids and areas | Only ids from `data/materials.json`; unknown ids dropped and shown back as "not counted"; areas clamped to the room | `agents/intake.py` |
| Planner | After each measurement, decides whether another is worth it and says where to stand | Hard limits in code: at least 2 claps, at most 4; a sweep ends it | `agents/planner.py` |
| Optimizer | Tool-calling loop with `try_plan` and `finish`, against a priced catalogue and a budget | Every plan validated and scored by `acoustics/treat.py`; forced `finish` on the last turn; greedy fallback; no call at all when the room is already too dry | `agents/optimizer.py` |
| Shopper | Reads shop pages found by Tavily: product name, price as written, size and unit as written, pieces per pack, and passages copied from the page | Every passage checked against the page and every number against the passages; the engine converts units and computes the price per m²; thickness and price per m² must fit the product type | `agents/shopper.py`, `shop.py` |

What shaped the design:

- Reasoning is switched off for these calls
  (`chat_template_kwargs: {enable_thinking: false}`), which brings each call
  under about 2 s. With reasoning on, a small `max_tokens` can be spent
  before any answer arrives.
- Nemotron 3 Nano was tried first for intake. It mapped "a closed wardrobe"
  to 6 m² of carpet, while Super flags it as unknown, so every agent uses
  Super.
- Sending one shop page per call made the shopper reliable. With every page
  in one prompt it often returned an empty list, even for a page that plainly
  said "MORUM alfombra 200x300 cm 79,99€".
- Two system messages confuse it: it follows the first. `chat_json` puts the
  JSON schema and the instructions in one system message.
- A full session (3 claps with notes, then a plan) measured **9 Super calls,
  about 10.4k input and 1k output tokens, about 15 s in total**. At Token
  Factory's per-token prices that is well under a cent per room.
- A public demo means anyone can spend the credits, so each server instance
  allows 40 model-backed requests per client IP per hour
  (`CLAPBACK_LLM_PER_HOUR`).

## Accuracy and tests

`pytest` runs 86 tests: the engine on synthetic signals with known answers,
the geometry against exact image-source cases, the agents with the model
faked, the price checks, and the API. One of them runs the JavaScript tests
of the 3D acoustics with Node (`tests/js/`).

| What | Result |
|---|---|
| T20 from a synthetic decay, RT 0.3 / 0.6 / 1.2 s, bands from 1 kHz up | within 10 % |
| Noise floor at −40 dB | T30 dropped, T20 within 10 % |
| C50 and C80 against the exact values for an exponential decay | within 1 dB (the JND for C80) |
| D50 | within 0.05 |
| Sweep through a synthetic room, RT 0.4 / 0.9 s, 500 Hz–2 kHz | T30 within 10 % |
| Sweep played at 44.1 kHz, recorded at 48 kHz | RT within 10 % |
| Frequency response of a bare delta | flat within ±1 dB, 100 Hz–10 kHz |
| Loud talking one second before the clap | onset still on the clap, RT within 10 % |
| No sweep in the recording, or a sweep cut off | rejected with a message |
| First- and second-order reflection paths in a box | same points, lengths and delays as the image-source construction by hand |
| Particles in a box, α = 0.1 / 0.2 / 0.4 | decay 12 % slower than Eyring (1.14 / 0.54 / 0.24 s against 1.02 / 0.48 / 0.21 s) |
| Particles calibrated to a measured RT of 0.6 s | within 8 % |
| A shop price or size that isn't in the page's text | rejected |
| A 5 cm panel offered as a 10 cm one, or €5,400 for a pack of panels | rejected |
| Prices written as `1.234,56 €`, `€70,95`, `4,490.00`, `1 299 €` | read correctly |

On a real phone, two claps in the same room give mid-frequency RTs of 0.67
and 0.69 s (3 % apart), with the phone applying no voice processing. The
whole app, driven with a fake microphone playing a sweep through a
synthetic 0.70 s room, measures 0.75 s.

Not done yet: a comparison against a reference instrument (a measurement
microphone with Room EQ Wizard, or a room with a certified RT). The impulse
response download exists partly for that cross-check.

## Limits

- One clap is a rough measurement below 250 Hz. The app asks for more
  claps and draws low bands faded; the sweep fixes it.
- Statistical acoustics assumes a diffuse field. Bass maps use the modal
  model instead, and only for rectangular rooms.
- The STI map is an estimate from theory for a quiet room, not an
  IEC 60268-16 measurement. The C50 in the figures and the ISO table is
  measured.
- Absorption coefficients and treatment prices are typical values for
  planning, listed in `data/`.
- Phone microphones differ, and their low end rolls off. The frequency
  response includes the speaker and the microphone.
- Android may switch a Bluetooth speaker connected to the phone to call mode
  while the microphone is open (low sample rate). The app detects it and
  suggests using another device as the speaker.

## Using the live app

Open https://clapback-alpha.vercel.app on a phone. The microphone and the
camera need HTTPS, which the live app has. In Chrome, "Install app" puts it
on the home screen, full screen.

- **Clap:** stand near the middle of the room, phone at chest height and an
  arm's length away, everyone quiet for 5 seconds. Two or more claps from
  different spots are better than one.
- **Sweep:** put a speaker at least 2 m away at ear height, volume at about
  three quarters. Either connect it to the phone by Bluetooth, or open
  `https://clapback-alpha.vercel.app/speaker.html` on a laptop or second
  phone, tap *Tap to measure* on the phone, then press *Play* on the other
  device within 4 seconds.
- **Camera measuring:** tap *Measure it with the camera*, enter your height
  once, and follow the five steps.

## Running it yourself

Requires Python 3.11 or newer.

```bash
git clone https://github.com/lluisestape-upc/Clapback.git
cd Clapback
python -m venv .venv
.venv\Scripts\activate          # Windows; on macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env          # macOS/Linux: cp .env.example .env
python scripts/check_nebius.py  # lists the NVIDIA models the key can use, makes one short call
uvicorn clapback.server:app --port 8766 --reload
pytest
```

Then open http://localhost:8766. The microphone works on `localhost`. To use
a phone, forward the port over USB (Chrome → `chrome://inspect` → Port
forwarding) and open `http://localhost:8766` on the phone, or put the server
behind HTTPS.

Environment variables (`.env`):

| Variable | Needed | What for |
|---|---|---|
| `NEBIUS_API_KEY` | for the agents | Nemotron on Nebius Token Factory; without it every agent uses its fallback |
| `NEBIUS_BASE_URL` | no | defaults to `https://api.tokenfactory.nebius.com/v1` |
| `TAVILY_API_KEY` | no | real product prices in the plan; without it the plan uses typical prices |
| `CLAPBACK_LLM_PER_HOUR` | no | model-backed requests per IP per hour, default 40 |
| `CLAPBACK_RECORDINGS` | no | where recordings are saved with their context (default `recordings/`, `/tmp/recordings` on Vercel) |

**Deploying for free on Vercel.** `pyproject.toml` declares the FastAPI
entrypoint (`[tool.vercel]`), and the web app is served as static files from
the CDN. With the [Vercel CLI](https://vercel.com/docs/cli):

```bash
vercel link
vercel env add NEBIUS_API_KEY production
vercel env add TAVILY_API_KEY production
vercel deploy --prod
```

## API

| Endpoint | Input | Output |
|---|---|---|
| `POST /api/clap` | multipart: `audio` (WAV), `room` (JSON), `goal`, `notes`, `mic` (applied settings) | per-band EDT/T20/T30/C50/C80/D50, decay curves, energy-time curve, spectrogram, and the report for this clap |
| `POST /api/sweep` | as above, plus `f1`, `f2`, `seconds` | as above, plus the frequency response, the impulse response as a base64 WAV, and where the sweep was found; 422 with a reason if there's no whole sweep |
| `POST /api/analyze` | JSON: `room`, `goal`, `notes`, `claps` (per-band results of each measurement), `kinds` | averaged bands, verdict and target, modes, maps, what the notes added (Nemotron), and whether to measure again (Nemotron) |
| `GET /api/prices` | | per treatment type: pages read, products proposed, verified and rejected (with the reasons), and the three cheapest verified products with their passages |
| `POST /api/plan` | as `/api/analyze`, plus `budget_eur` and `offers` (the chosen product per treatment type, from `/api/prices`) | treatments in whole products with cost and the product's link and passages, RT per band before and after, summary, and the trace of tried plans |
| `POST /api/room` | a room | volume and areas, or 422 for an unknown material |
| `GET /api/materials` | | the materials table |
| `GET /api/health` | | `{"ok": true}` |

A room is a floor polygon in metres, a height, and surfaces (floor, ceiling,
one per wall), each with a material id and optional patches; see
`clapback/room.py`.

## Project layout

```
clapback/
  server.py      FastAPI app: the API, plus the web app as static files
  room.py        room model (floor polygon, height, surfaces, patches)
  materials.py   absorption table loader
  targets.py     target RT per use and the verdict
  shop.py        real prices: Tavily search and extract, checks, whole products
  acoustics/
    decay.py     onset, bands, noise floor, Schroeder, EDT/T20/T30, C50/C80/D50, chart data
    sweep.py     exponential sine sweep, deconvolution, frequency response, IR export
    reverb.py    Sabine/Eyring, air, furnishing, calibration
    modes.py     room modes, Schroeder frequency, boomy notes
    maps.py      STI estimate, modal pressure, C50 (Barron)
    geometry.py  early reflections (image sources), placement, where to sit
    treat.py     treatment validation, cost and prediction, greedy plan
  agents/        intake, planner, optimizer, shopper (Nemotron)
  llm/           Nebius Token Factory client
web/             the app, no build step
  app.js         flow and results
  capture.js     microphone to WAV, quick quality check
  sweep.js       the test sweep (the same signal as sweep.py)
  charts.js      SVG and canvas charts
  measure.js     camera + tilt room measuring
  scan.js        WebXR AR scan
  room3d.js      the 3D view and its layers (three.js)
  acoustics3d.js surfaces, heat, modal field in the volume, particles (no drawing; node-tested)
  speaker.html   plays the sweep on a second device
data/            materials.json, treatments.json
tests/           pytest: engine, sweep, geometry, agents with the model faked, prices, API;
                 js/ runs with node --test
docs/            PLAN.md, images/
scripts/         check_nebius.py
```

## References

- M. R. Schroeder, "New method of measuring reverberation time", *JASA* 37, 1965.
- A. Lundeby, T. E. Vigran, H. Bietz, M. Vorländer, "Uncertainties of measurements in room acoustics", *Acustica* 81, 1995.
- A. Farina, "Simultaneous measurement of impulse response and distortion with a swept-sine technique", AES 108th Convention, 2000.
- M. Barron, L.-J. Lee, "Energy relations in concert auditoriums, I", *JASA* 84, 1988.
- M. R. Schroeder, "Modulation transfer functions: definition and measurement", *Acustica* 49, 1981.
- ISO 3382-1:2009 and ISO 3382-2:2008, measurement of room acoustic parameters.
- IEC 60268-16, objective rating of speech intelligibility by speech transmission index.
- ISO 9613-1:1993, attenuation of sound during propagation outdoors, part 1: absorption by the atmosphere.
- DIN 18041:2016, acoustic quality in rooms.
- EBU Tech 3276, listening conditions for the assessment of sound programme material.

## License

MIT, see [LICENSE](LICENSE).
