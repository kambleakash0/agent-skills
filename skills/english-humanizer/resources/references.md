# English Humanizer: Full Pattern Library

This document contains the canonical list of 25 AI-generation patterns, categorized by vocabulary, structure, tone, and formatting.

## Table of Contents

- [Vocabulary & Phrasing (1-7)](#vocabulary--phrasing)
- [Sentence Structure & Grammar (8-13)](#sentence-structure--grammar)
- [Narrative & Tone (14-20)](#narrative--tone)
- [Formatting & Chatbot Quirks (21-25)](#formatting--chatbot-quirks)
- [Full Before & After Example](#full-before--after-example)

---

## Vocabulary & Phrasing

### 1. The AI Glossary

LLMs rely on a specific cluster of words that are statistically highly probable but rarely used by humans in everyday writing.

- **Watch words:** *Delve, tapestry, crucial, testament, landscape, intricate, beacon, underscore, pivotal, robust, dynamic, multifaceted, realm.*
- **Before:** This underscores the crucial role of robust frameworks in the digital landscape.
- **After:** This shows why strong frameworks matter online.

### 2. Exaggerated Significance

AI inflates the historical or practical importance of mundane topics.

- **Watch words:** *Serves as a testament to, marks a pivotal moment, stands as a beacon.*
- **Before:** The release of the new smartphone update marks a pivotal moment in mobile history.
- **After:** The new smartphone update adds several requested features.

### 3. Promotional Ad-Speak

AI struggles to maintain a neutral tone, often slipping into flowery, marketing-style language even for encyclopedic topics.

- **Watch words:** *Nestled in, breathtaking, vibrant, seamless, unparalleled.*
- **Before:** Nestled in the vibrant heart of the city, the breathtaking library offers an unparalleled reading experience.
- **After:** The downtown library is a popular spot for reading.

### 4. Transitional Duct Tape

AI overuses formal conjunctive adverbs to force flow between disconnected ideas.

- **Watch words:** *Furthermore, moreover, additionally, consequently, it is worth noting that.*
- **Before:** The battery life is short. Furthermore, the screen is dim.
- **After:** The battery life is short and the screen is dim.

### 5. Vague Attribution

AI attributes claims to unnamed authorities to sound credible without citing sources.

- **Watch words:** *Experts note, observers point out, studies show, critics argue.*
- **Before:** Experts note that this trend is accelerating.
- **After:**[Name the specific expert/study, or state it as a direct claim].

### 6. "To" Avoidance (Over-complication)

AI avoids simple verbs like "is" or "has," replacing them with clunky phrases.

- **Before:** The building *serves as a* headquarters and *boasts* three floors.
- **After:** The building *is* the headquarters and *has* three floors.

### 7. Wordy Evasion (Fluff)

Using ten words where three would do.

- **Before:** Due to the fact that the system has the capacity to handle...
- **After:** Because the system can handle...

---

## Sentence Structure & Grammar

### 8. The Rule of Three

AI compulsively groups ideas, adjectives, or examples into threes to simulate comprehensiveness.

- **Before:** The workshop will provide innovation, inspiration, and industry insights.
- **After:** The workshop covers industry insights and new ideas.

### 9. Trailing Participles (Fake Depth)

Adding an "-ing" phrase at the end of a sentence to force a profound conclusion.

- **Before:** The team finished the project early, *highlighting their dedication to excellence.*
- **After:** The team finished the project early.

### 10. Negative Parallelism

Overusing the "Not only X, but also Y" or "It's not just about X, it's about Y" structures.

- **Before:** It’s not just about writing code; it’s about crafting a digital experience.
- **After:** Good code creates a better user experience.

### 11. False Scope (From X to Y)

Using a "From A to B" structure where A and B aren't actually on a meaningful spectrum.

- **Before:** We cover everything from the birth of stars to the mystery of dark matter.
- **After:** We cover star formation and dark matter.

### 12. Synonym Cycling

Because LLMs have "repetition penalty" parameters, they unnaturally cycle through synonyms instead of just reusing a noun.

- **Before:** The *car* drove fast. The *vehicle* turned left. The *automobile* stopped.
- **After:** The *car* drove fast, turned left, and stopped.

### 13. Metronomic Rhythm

AI writes sentences of the exact same length and structure, creating a robotic, metronome-like reading experience.

- **Fix:** Break up the rhythm. Use a very short sentence. Follow it with a longer, more complex one.

---

## Narrative & Tone

### 14. The "Despite Challenges" Formula

AI loves to write a "Challenges" paragraph that immediately dismisses the challenge to maintain a positive tone.

- **Before:** Despite facing supply chain challenges, the company continues to thrive and the future looks bright.
- **After:** Supply chain issues have slowed production, though revenue remains stable.

### 15. Generic Optimistic Conclusions

AI cannot handle ambiguity or dark endings, always wrapping up with a vague, positive summary.

- **Before:** As we look to the horizon, the journey of discovery continues to unfold, promising exciting new advancements.
- **After:** [Delete entirely, or end on a concrete, factual note].

### 16. Sycophantic Tone

Overly eager, people-pleasing language (a direct artifact of RLHF training).

- **Before:** That is a fantastic point! You are absolutely right that inflation is a factor.
- **After:** Inflation is definitely a factor here.

### 17. Over-Qualification

Hedging bets so much that the sentence loses all meaning.

- **Before:** It could potentially be argued that this might possibly have an effect.
- **After:** This will likely have an effect.

### 18. The "In Conclusion" Crutch

Starting the final paragraph with "In conclusion," "Ultimately," or "To summarize." Humans rarely do this outside of middle-school essays.

### 19. Lack of "I" or "We"

AI avoids the first person, resulting in sterile, passive text.

- **Fix:** Where appropriate (like in a blog post or email), change "It was decided that" to "I decided" or "We decided."

### 20. Explaining the Joke/Metaphor

AI doesn't trust the reader's intelligence and will over-explain its own figures of speech.

- **Before:** It was a Trojan Horse, meaning it looked like a gift but contained a hidden threat.
- **After:** It was a Trojan Horse.

---

## Formatting & Chatbot Quirks

### 21. Em-Dash Overuse

AI uses the em-dash (—) constantly to simulate a "punchy" or conversational tone.

- **Fix:** Replace with commas, periods, or simply rewrite the sentence.

### 22. Over-Bolding

Mechanically bolding every key term or concept in a paragraph.

- **Fix:** Remove bolding unless it is a strict sub-header.

### 23. Inline Header Lists

Outputting bulleted lists where every item starts with a bolded word followed by a colon.

- **Before:**
  - **Speed:** The app is faster.
  - **Security:** The app is safer.
- **After:** The app is now faster and more secure.

### 24. Emoji Bullet Points

Using 🚀, 💡, or ✅ as bullet points in professional text.

### 25. Knowledge Cutoff Disclaimers

Leaving in chatbot apologies.

- **Before:** As of my last knowledge update in 2023, the population is...
- **After:** The population is...

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
