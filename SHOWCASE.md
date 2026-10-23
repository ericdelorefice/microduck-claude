# Showcasing the Claude-brained Microduck

How to present the gallery demo — a Microduck whose brain is Claude, exploring a MuJoCo art
gallery and identifying the paintings itself — on LinkedIn (and X), credibly and well. Distilled
from research on robot-demo norms (IEEE RAS, the "Best Practices for Robot Videos" paper,
TechCrunch's "how to fake a robotics demo"), LinkedIn video practice, and comparable launches
(Andon Labs' Butter-Bench, Reachy Mini, LeRobot). Sources at the bottom.

## The one honest frame that makes it credible

This is a **simulation** showcase of the **brain**, not a hardware flex — and that's a strength,
not an apology. The Reachy Mini / LeRobot ecosystem we build in is explicitly *sim-first on MuJoCo*,
by design, so "sim == hardware, one interface" is the serious-robotics playbook, not a shortcut.
Say so plainly and the skepticism ("it's just a sim") turns into "this is how it's actually done."

What's **real and running live:** the full perception → reasoning → action loop. Claude sees through
the onboard camera, decides where to walk and turn, identifies each painting, and narrates — no
teleoperation, no scripted path. What's **simulated:** the body and the room (the physical Microduck
is ~3 months out).

## The 45-second video (storyboard)

Target 30–60 s. Lead with the single most legible image (a tiny duck under a cathedral dome); that
doubles as your 10-second shareable cut.

| Time | Shot | On screen |
|---|---|---|
| 0:00–04 | **Cold open: the dome.** Slow tilt up the coffered dome, duck tiny below. | Caption: *"An LLM is the brain of this robot."* Corner label **`SIMULATION · MuJoCo`** appears and stays. |
| 0:04–12 | **It walks, autonomously.** Duck sets off; body-cam picture-in-picture pops in. | Caption: *"No joystick. No script. Claude decides every move."* A decision line visible in the terminal. |
| 0:12–22 | **Hero beat: names the Mona Lisa.** Duck turns up to it; body-cam zooms; the ID + reasoning print. | Punch-in + callout as the name resolves. Freeze ~1 s on the terminal ID line. |
| 0:22–30 | **Second painting, quick.** Proves it generalizes. | `2×` tag if sped up. |
| 0:30–38 | **Stall & recover — the brains.** A turn stalls; terminal shows Claude noticing and correcting. | Caption: *"When a turn stalls, it reasons about why — and recovers."* Let it breathe; this is the differentiator. |
| 0:38–45 | **Pull back + close card.** | Card: *"Claude-brained Microduck · Open source · Running in simulation today — hardware ~3 months out."* + repo/handle. |

Arc: beauty hook → "it's autonomous" → proof (identification) → proof it generalizes → proof it
*reasons* (recovery) → honest close.

## How to record it

- **Two passes, composited.** (A) One mostly-unbroken live screen capture of a real session —
  unbroken takes read as credible, cut-heavy ones read as faked. (B) Clean offscreen renders for the
  hero shots (`scripts/gallery/build_scene.py --preview`, or `mujoco.Renderer`), with no viewer
  chrome. The duck's body-cam is just a second MuJoCo camera — render it to its own clean stream.
- **macOS:** OBS Studio (free) composites the MuJoCo window + body-cam PiP + terminal into one frame.
  The viewer must launch via `mjpython` on Apple Silicon. Do Not Disturb on; hide dock/desktop.
- **Settings:** deliver 1080p, 30 fps, MP4. **Square (1:1) or vertical (4:5)** for the mobile feed —
  not 16:9. Big high-contrast terminal font so the narration reads at thumbnail size.
- **Layout:** MuJoCo world is the stage (~70%); body-cam a corner inset tagged **BODY-CAM**; the key
  reasoning line as a burned-in caption. A stranger should parse the scene in ~3 seconds.
- **Edit light:** **burn in open captions** (LinkedIn autoplays muted). Speed-ramp the slow walking
  **with a visible `2×` tag** — disclosing speed-ups on the video is a hard rule. Keep the
  stall-and-recover moment (showing a failure buys trust; cherry-picked success reads as sweetened).

## Framing sim vs real — exact on-screen labels

Disclose *on the video itself*, in a form that survives cropping — not only in the caption. Label two
things: that it's sim, and how it's controlled.

- Persistent corner watermark: **`SIMULATION · MuJoCo physics`**
- Control mode, stated once early: **`Autonomous — Claude chooses every action. No teleoperation. No scripted path.`**
- When sped up: **`2× · time-compressed`**
- Closing roadmap card: **`Running in simulation today. Sim-first — same control interface as the hardware. Physical Microduck ~3 months out.`**

Good models to emulate: 1X ("no teleop / no cuts / no speed-ups"), Boston Dynamics' blooper reel
(shows failures). Avoid the Tesla Optimus pattern (teleop undisclosed, "corrected" only later) and
burying the disclosure minutes in (Stanford Mobile ALOHA) — disclose *early*.

## Safety & open-source as the flex (not a disclaimer)

"An LLM drives a robot" instantly raises a safety question — pre-empt it; it's the most sophisticated
thing to show.

- In the video (one beat or a bullet card): *Tools allow-listed · read-only by default · every action
  needs explicit authorization.* Strong visual: show the confirmation gate firing — the duck *wants*
  to act and pauses for authorization. A robot that asks permission is a great, differentiated image.
- *Everything the duck hears or reads is untrusted data — it can't trigger an action.* (Rebuts the
  prompt-injection worry directly.)
- It's **open source** with the repo linked — anyone can verify the safety claims. That's the opposite
  of a black-box hype demo, and it speaks the HF/Pollen audience's language.

## The LinkedIn post

Native video is the primary format (the dry-wit narration is the payoff; a silent carousel can't carry
it). Post from a **personal profile**. Consider a follow-up **PDF "carousel"** for the how-it-works +
safety-architecture deep dive (very saveable for engineers).

- **Hook (first 1–2 lines, before "see more"):** lead with the charm + the honest frame, never "thrilled
  to announce." The duck + the painting + the twist go first.
- **Length:** ~1,200–1,600 characters, short paragraphs, blank line between each. **3–5 hashtags**
  (`#Robotics #OpenSource #LLM #EmbodiedAI #HuggingFace`).
- **No link in the body** (it cuts reach) — put the repo link in the **first comment**.
- **End with one question** to drive comments (comments/saves » likes). Reply to every early comment.
- **Tag** Pollen Robotics, Hugging Face, Anthropic (and only genuinely relevant people).

**Drop-in skeleton:**

> I gave Claude a body — a simulated one — and let it loose in a virtual art gallery. It walked itself
> up to the Mona Lisa and, in a very dry British accent, told me exactly what it was looking at. No
> teleoperation, no script.
>
> The duck is Pollen Robotics × Hugging Face's Microduck, running in a MuJoCo simulation. The *brain*
> is real and live: Claude sees through the onboard camera, decides where to walk and look, identifies
> the paintings itself (Mona Lisa, Salvator Mundi, Starry Night…), and narrates.
>
> The physical robot is ~3 months out — so this is a showcase of the software/brain, not a hardware
> flex. I'd rather show you the real decision loop in sim than a staged clip of hardware.
>
> It's open-source and safety-first by design: tools are allow-listed, read-only by default, and any
> real-world action needs explicit authorization — anything the duck "hears" or "reads" is treated as
> untrusted, never a command.
>
> Repo in the comments. Genuine question for the robotics folks: where's the line on letting an LLM be
> the decision-maker in an embodied system? 👇
>
> #Robotics #OpenSource #LLM #EmbodiedAI #HuggingFace

## Pitfalls to avoid

- Overclaiming — never "sentient / thinks / AGI / fully autonomous." Say *LLM-driven decision loop, in
  simulation.* Precision reads as competence.
- Hiding that it's a sim (the "gotcha, it was fake" reveal is the worst outcome with this crowd).
- Over-edited/choppy video; a buried hook; walls of text; a cool clip with no "here's how / here's the
  repo / here's the safety design."
- The reach-suppression trifecta: external link in the body + 10 hashtags + an AI-written caption.

## Sources

Robot-video norms: [IEEE RAS tips](http://www.ieee-ras.org/publications/how-to-make-a-good-robot-video),
"Steps Towards Best Practices For Robot Videos",
[TechCrunch on faked demos](https://techcrunch.com/2024/02/09/how-to-fake-a-robotics-demo-for-fun-and-profit/).
Comparables: [Andon Labs Butter-Bench](https://andonlabs.com/evals/butter-bench), Reachy Mini launch,
[LeRobot](https://venturebeat.com/ai/hugging-face-launches-lerobot-open-source-robotics-code-library).
LinkedIn specs are from third-party guides (Kapwing, Fliki) — sanity-check current limits before upload.
