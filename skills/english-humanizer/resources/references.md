# English Humanizer: Full Pattern Library

This document contains the canonical list of **40 AI-generation patterns**, categorized by vocabulary, structure, tone, and formatting. It draws on [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing), community-maintained reverse-engineering catalogs, and internal observations.

## How to Use This List

Three principles matter more than any single pattern:

1. **Clustering is the signal, not single occurrences.** A human can legitimately write "delve" once. Three of these tropes in the same paragraph is AI. Always ask "how many tells, how close together?" before flagging text.
2. **Regression to the mean is the root cause.** LLMs launder specific facts into statistically common generic descriptions. The deepest diagnostic is not "does this sound fancy?" but "has concrete information been replaced with generic gravitas?" If specific names, numbers, dates, or places were available and the text went abstract, that's the real tell.
3. **Watch lists age — track model eras.** The GPT-4 era (2023–2024) favored *delve, tapestry, testament, intricate, meticulous*. The GPT-4o era (2024–2025) shifted to *align with, fostering, bolstered*. The GPT-5 era (2025+) favors *emphasizing, enhance, highlighting, showcasing*. "Delve" in particular has receded sharply. Expect vocabulary to drift; the structural patterns below are more stable than the word lists.

## Table of Contents

- [Vocabulary & Phrasing (1–10)](#vocabulary--phrasing)
- [Sentence Structure & Grammar (11–18)](#sentence-structure--grammar)
- [Narrative & Tone (19–29)](#narrative--tone)
- [Formatting & Provenance (30–40)](#formatting--provenance)
- [Full Before & After Example](#full-before--after-example)

---

## Vocabulary & Phrasing

### 1. The AI Glossary

LLMs rely on a specific cluster of words that are statistically highly probable but rarely used by humans in everyday writing. The cluster drifts by model generation.

- **GPT-4 era (2023–2024):** *delve, tapestry, testament, landscape, intricate, meticulous, beacon, crucial, pivotal, realm.*
- **GPT-4o era (2024–2025):** *align with, fostering, bolstered, robust, dynamic, multifaceted, leverage, harness, paradigm, synergy.*
- **GPT-5 era (2025+):** *emphasizing, enhance, highlighting, showcasing, streamline, utilize, interplay, valuable, profound, ecosystem, framework, vibrant.*
- **Before:** This underscores the crucial role of robust frameworks in the digital landscape.
- **After:** This shows why strong frameworks matter online.

### 2. Exaggerated Significance

AI inflates the historical or practical importance of mundane topics.

- **Watch phrases:** *serves as a testament to, marks a pivotal moment, stands as a beacon, is a reminder, indelible mark, deeply rooted, key turning point, focal point, setting the stage for, shapes the, reflects broader, symbolizing ongoing/enduring/lasting, contributing to the evolving landscape of.*
- **Before:** The release of the new smartphone update marks a pivotal moment in mobile history.
- **After:** The new smartphone update adds several requested features.

### 3. Promotional Ad-Speak

AI struggles to maintain a neutral tone, often slipping into flowery, marketing-style language even for encyclopedic topics.

- **Watch phrases:** *nestled in, breathtaking, vibrant, seamless, unparalleled, boasts a, rich, profound, exemplifies, commitment to, natural beauty, in the heart of, groundbreaking, renowned, featuring, diverse array.*
- **Before:** Nestled in the vibrant heart of the city, the breathtaking library offers an unparalleled reading experience.
- **After:** The downtown library is a popular spot for reading.

### 4. Transitional Duct Tape

AI overuses formal conjunctive adverbs to force flow between disconnected ideas. Distinct from #9 emphasis hedges — these are logical connectors, not gravitas markers.

- **Watch words:** *Furthermore, moreover, additionally, consequently, as such, in addition.*
- **Before:** The battery life is short. Furthermore, the screen is dim.
- **After:** The battery life is short and the screen is dim.

### 5. Vague Attribution

AI attributes claims to unnamed authorities to sound credible without citing sources. Also watch for **"such as" used as a preamble to an exhaustive list** rather than a sample — a distinctive AI tell flagged by the Wikipedia catalog.

- **Watch phrases:** *Experts note, observers point out, studies show, critics argue, industry reports suggest, several publications have cited, observers have cited, some argue that.*
- **Before:** Experts note that this trend is accelerating.
- **After:** [Name the specific expert or study, or state it as a direct claim.]

### 6. Copula Avoidance ("is/are" Avoidance)

AI avoids simple verbs like *is, are, has*, replacing them with clunky phrases. Corpus studies have measured a noticeable drop in "is/are" frequency in online text since LLMs became mainstream.

- **Watch verbs:** *serves as, stands as, marks, features, offers, represents, boasts, ventured into.*
- **Before:** The building *serves as* a headquarters and *boasts* three floors.
- **After:** The building *is* the headquarters and *has* three floors.

### 7. Wordy Evasion (Fluff)

Using ten words where three would do.

- **Before:** Due to the fact that the system has the capacity to handle...
- **After:** Because the system can handle...

### 8. Magic Adverbs

Understated adverbs that manufacture gravitas without adding meaning. Distinct from #22 over-qualification because these don't hedge — they amplify.

- **Watch words:** *quietly, deeply, fundamentally, remarkably, arguably, notably, profoundly, inherently.*
- **Before:** The team was *quietly* orchestrating a *fundamentally* different approach.
- **After:** The team was building a different approach.

### 9. Emphasis Hedges

Sentence-level phrases that flag "this next bit is important" without carrying any logical function. Distinct from #4 transitional duct tape, which glues clauses together.

- **Watch phrases:** *It's worth noting that, It bears mentioning, Importantly, Interestingly, Notably, Of particular note.*
- **Before:** It's worth noting that the API rate limit has changed.
- **After:** The API rate limit has changed.

### 10. Stock Clichéd Idioms

Figurative stock phrases AI reaches for when it wants to sound seasoned. Distinct from the AI glossary (#1) — these are folk idioms, not corporate Latinisms.

- **Watch phrases:** *smoking gun, perfect storm, move the needle, at the end of the day, game changer, double-edged sword, low-hanging fruit, boil the ocean, paradigm shift, tip of the iceberg.*
- **Fix:** Delete the idiom and state the literal claim.

---

## Sentence Structure & Grammar

### 11. The Rule of Three

AI compulsively groups ideas, adjectives, or examples into threes to simulate comprehensiveness.

- **Before:** The workshop will provide innovation, inspiration, and industry insights.
- **After:** The workshop covers industry insights and new ideas.

### 12. Trailing Participles (Fake Depth)

Adding an "-ing" phrase at the end of a sentence to force a profound conclusion.

- **Watch words:** *highlighting, underscoring, emphasizing, ensuring, reflecting, symbolizing, contributing to, cultivating, fostering, encompassing, showcasing, resonating with.*
- **Before:** The team finished the project early, *highlighting their dedication to excellence.*
- **After:** The team finished the project early.

### 13. Negative Parallelism

Overusing "Not only X, but also Y" or "It's not just about X, it's about Y" — plus two related variants that appear frequently:

- **Staccato reveal:** "Not a bug. Not a feature. A fundamental design flaw."
- **Causal inversion:** "Not because it's easy, but because it's hard."
- **Before:** It's not just about writing code; it's about crafting a digital experience.
- **After:** Good code creates a better user experience.

### 14. False Scope (From X to Y)

Using "From A to B" where A and B aren't actually on a meaningful spectrum.

- **Before:** We cover everything from the birth of stars to the mystery of dark matter.
- **After:** We cover star formation and dark matter.

### 15. Elegant Variation (Synonym Cycling)

LLMs have a "repetition penalty" in their sampling parameters, so they unnaturally cycle through synonyms instead of just reusing a noun. Humans repeat words much more freely.

- **Before:** The *car* drove fast. The *vehicle* turned left. The *automobile* stopped.
- **Before (a sharper example from Wikipedia's catalog):** The *main character* appears in chapter one. The *protagonist* meets the *key player* soon after. This *eponymous character*...
- **After:** The *car* drove fast, turned left, and stopped.

### 16. Metronomic Rhythm

AI writes sentences of the exact same length and structure, creating a robotic, metronome-like reading experience.

- **Fix:** Break up the rhythm. Use a very short sentence. Follow it with a longer, more complex one.

### 17. Rhetorical Question + Immediate Answer

Self-posed questions followed by clipped reveals. Distinct from a genuine rhetorical question because AI always answers its own question one or two words later.

- **Before:** The result? Devastating. The worst part? Nobody saw it coming.
- **After:** The result was devastating, and nobody saw it coming.

### 18. Anaphora & Fragment Stacking

Two related rhythmic tells that often appear together:

- **Anaphora abuse:** Same sentence opening repeated for dramatic effect. *"They assume… They assume… They assume…"*
- **Fragment-as-paragraph:** One- to four-word sentence fragments stacked for manufactured drama. *"He published this. Openly. In a book. As a priest."*
- **Fix:** Combine the fragments into a single sentence with ordinary prose rhythm.

---

## Narrative & Tone

### 19. The "Despite Challenges" Formula

AI loves to write a "Challenges" paragraph that immediately dismisses the challenge to maintain a positive tone.

- **Before:** Despite facing supply chain challenges, the company continues to thrive and the future looks bright.
- **After:** Supply chain issues have slowed production, though revenue remains stable.

### 20. Generic Optimistic Conclusions

AI cannot handle ambiguity or dark endings, always wrapping up with a vague, positive summary.

- **Before:** As we look to the horizon, the journey of discovery continues to unfold, promising exciting new advancements.
- **After:** [Delete entirely, or end on a concrete factual note.]

### 21. Sycophantic Tone

Overly eager, people-pleasing language (a direct artifact of RLHF training). Includes the **compliment sandwich** — leading any critique with forced positivity.

- **Before:** That is a fantastic point! You are absolutely right that inflation is a factor.
- **Before (sandwich):** Great suggestion! That said, the schema won't support it.
- **After:** Inflation is definitely a factor here. / The schema won't support that.

### 22. Over-Qualification (Hedging)

Hedging bets so much that the sentence loses all meaning.

- **Before:** It could potentially be argued that this might possibly have an effect.
- **After:** This will likely have an effect.

### 23. The "In Conclusion" Crutch

Starting the final paragraph with "In conclusion," "Ultimately," or "To summarize." Humans rarely do this outside of middle-school essays. Related: **fractal summaries** — recursive "as we've seen in this section" recaps at every nesting level of a document.

### 24. Voice Inversion (Missing "I/We" or Overused "Let's")

AI has two opposite failure modes around first person:

- **Sterile passive:** avoiding first person entirely ("It was decided that…").
- **Pedagogical "Let's":** over-using collective tour-guide framing. Watch: *Let's break this down, Let's unpack this, Let's explore, Let's dive in, Together we'll discover.*
- **Fix:** Use "I" or "we" honestly when it fits; drop the tour-guide "Let's" phrasing.

### 25. Explaining the Joke/Metaphor

AI doesn't trust the reader's intelligence and will over-explain its own figures of speech.

- **Before:** It was a Trojan Horse, meaning it looked like a gift but contained a hidden threat.
- **After:** It was a Trojan Horse.

### 26. Invented Concept Labels

Compound neologisms ending in *paradox, trap, creep, divide, vacuum, inversion, effect*. Used to make ordinary observations sound like named theories. A strong and underappreciated signature.

- **Watch templates:** *the X paradox, the X trap, X creep, the X divide, the X vacuum, the X inversion.*
- **Examples:** "the supervision paradox," "the acceleration trap," "workload creep."
- **Fix:** Drop the label; describe the phenomenon directly.

### 27. Dead Metaphor Overuse

One metaphor hammered 5–10+ times across a single piece — ecosystems, bridges, walls, highways, tapestries — until the figurative meaning dissolves.

- **Fix:** Use the metaphor once, or not at all.

### 28. False Exclusivity ("Here's What Nobody Tells You")

Manufactured insider framing that claims the reader is about to learn something rare. Also covers false-suspense transitions.

- **Watch phrases:** *What most people miss, What nobody talks about, Here's the kicker, Here's the thing, Here's where it gets interesting, The truth is simpler than you think, History is unambiguous on this.*
- **Fix:** Just state the point without the sales pitch.

### 29. One-Point Dilution

The same single argument restated ten different ways across thousands of words. A model padding length without adding new content.

- **Fix:** Identify the one claim. Keep the best sentence. Delete the rest.

---

## Formatting & Provenance

### 30. Em-Dash Overuse

AI uses the em-dash (—) constantly to simulate a punchy or conversational tone. Human prose uses em-dashes sparingly; unedited chatbot output often uses them several times per paragraph.

- **Fix:** Replace with commas, periods, or rewrite the sentence.

### 31. Over-Bolding

Mechanically bolding every key term or concept in a paragraph.

- **Fix:** Remove bolding unless it is a strict sub-header.

### 32. Inline Header Lists

Outputting bulleted lists where every item starts with a bolded word followed by a colon.

- **Before:**
  - **Speed:** The app is faster.
  - **Security:** The app is safer.
- **After:** The app is now faster and more secure.

### 33. Emoji Bullet Points

Using 🚀, 💡, or ✅ as bullet points in professional text. Also: emoji-prefixed section headers.

### 34. Knowledge Cutoff Disclaimers & Prompt Leakage

Leaving in chatbot apologies or generation artifacts that no human would write in a finished document.

- **Watch phrases:** *As of my last knowledge update, As of my last update, There may be recent developments not captured here, I cannot provide, As a large language model, [insert X here], [add content here].*
- **Also watch:** abrupt mid-sentence cutoffs (token exhaustion) and unfilled bracket placeholders left behind.
- **Fix:** Delete the disclaimer and state the fact directly.

### 35. Title Case Headings

Capitalizing every main word in section headings ("Global Context: Critical Mineral Demand") instead of sentence case. Most modern style guides prefer sentence case; mechanical title case on every heading is a strong provenance tell for paste-from-chatbot content.

### 36. Smart-Quote, Unicode, & Markdown Artifacts

Paste-from-chatbot provenance signals. In a document expecting plain ASCII or wikitext, watch for:

- **Smart quotes:** curly " " ' ' instead of straight " '
- **Arrows and special chars:** → ⇒ • ×
- **Markdown leakage:** literal `**bold**` or `*italic*` appearing in a non-Markdown target
- **Excess em-dashes** (see #30)

### 37. Credential & Notability Dumping

Listing media outlets, awards, degrees, or coverage venues instead of synthesizing content. Common in bios, company pages, and wiki-style articles.

- **Watch phrases:** *profiled in, covered by, featured in, active social media presence, independent coverage, local/regional/national media outlets, written by a leading expert.*
- **Fix:** Cite one or two concrete sources inline; drop the rest.

### 38. Sudden Style Shift

Mid-document tonal or vocabulary change that reveals a human/AI boundary, or one model's output handed off to another. Paragraph 1 reads like a textbook, paragraph 2 reads like marketing copy. Also includes **content duplication** — entire paragraphs repeated verbatim within one piece because the model lost track of state.

- **Fix:** Pick one voice and enforce it end-to-end. Remove duplicated paragraphs.

### 39. Listicle-in-Prose / Phase Labels

Numbered enumeration disguised as narrative. *"The first wall is… The second wall is… The third wall is…"* or *"Phase 1: … Phase 2: … Stage 3: …"* stamped over content that has no genuine ordering.

- **Fix:** Describe by topic, not by number, unless the ordering is meaningful.

### 40. Canned Opening Hooks

Stock openers that flag chatbot output within the first sentence.

- **Watch phrases:** *Imagine a world where…, Think of it as…, Picture this:, In today's fast-paced world, In an era of…, It's no secret that…*
- **Fix:** Start with the actual subject.

---

## Full Before & After Example

### Before (AI-Generated)
>
> **The Future of Remote Work**
>
> The shift to remote work marks a pivotal moment in the modern corporate landscape. Furthermore, it serves as a testament to human adaptability. Not only does it offer unparalleled flexibility, but it also fosters a vibrant tapestry of global collaboration.
>
> Experts note that companies must navigate intricate challenges, from technological hurdles to communication breakdowns. However, despite these challenges, organizations are implementing robust frameworks to ensure seamless operations.
>
> In conclusion, as we look to the horizon, the future of remote work remains incredibly bright. By leveraging dynamic tools and prioritizing employee well-being, businesses can unlock new realms of productivity.

### After (Humanized)
>
> The shift to remote work has permanently changed corporate culture. While it offers employees much-needed flexibility, it has also forced companies to rethink how global teams collaborate.
>
> It hasn't been entirely smooth. IT departments are still dealing with security hurdles, and managers are finding that asynchronous communication often leads to misunderstandings. To fix this, many companies are standardizing their software stacks and setting stricter core working hours.
>
> Remote work isn't going anywhere, but the tools and policies surrounding it will likely look very different five years from now.

### Summary of Changes Made

- Removed exaggerated significance ("pivotal moment", "testament to human adaptability").
- Removed AI vocabulary ("landscape", "tapestry", "intricate", "robust", "seamless", "dynamic").
- Removed transitional fluff ("Furthermore", "In conclusion").
- Fixed negative parallelism ("Not only... but also").
- Removed vague attribution ("Experts note").
- Replaced the generic optimistic conclusion with a concrete, realistic prediction.
- Varied sentence lengths to break the metronomic rhythm.
