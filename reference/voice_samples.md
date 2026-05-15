# Voice samples

This file is the calibration set for the `brand_voice_similarity` eval. The "good"
samples are the positive anchor (cosine similarity ≥ 0.42 to their mean embedding).
The "anti-pattern" samples are documented so a reader can see exactly what we're
avoiding — they are not used as a negative anchor by the eval, but they are the
phrasing the LLM should never produce.

All copy below was written for this skill. No content was copied from cookunity.com.

---

## Good sample 1 — email subject + opener (anthropomorphic verb, em-dash aside)

Subject: This bowl's been waiting for you, {{first_name}}

Maya's tandoori cauliflower steak doesn't apologize — and it doesn't ask if you're sure. Just smoke, char, and the kind of yogurt-spiked finish that makes your fork-hand work overtime. Ready in 2 minutes. No takeout night required.

---

## Good sample 2 — email opener (wordplay/coined word, negation-affirmation)

Subject: Chef-ortless, weeknight-proof, you-shaped

Not a meal kit. Not a frozen brick. Just dinner — already cooked by someone who's spent more time over a flame than you've spent at your last three jobs. Tomás Vega smokes the brisket. You press a button. Both of you are doing your part.

---

## Good sample 3 — push notification + email lead (anthropomorphic verb on food)

Push: Anya's branzino is calling your name. Pick up.

Email: That branzino isn't going to roast itself, {{first_name}}. Anya already did the lemon-caper hard part — you're 6 minutes and a fork away from the kind of dinner that whispers "Mediterranean" instead of shouting "diet." Ten minutes to plate. No prep, no panic, no Greek-grandmother guilt.

---

## Good sample 4 — SMS (second-person directness, wordplay)

SMS: Hey {{first_name}} — Marcus dropped a brisket. The kind that makes side-dishes look like understudies. Smoked, sliced, ready in 4. Tap to claim → {{short_url}}

---

## Good sample 5 — email body (negation-then-affirmation, em-dash aside, anthropomorphic)

You don't need a new diet, {{first_name}} — you need dinner that already knows what it wants to be. Yuki's salmon donburi knows. The cauliflower rice underneath knows. Even the scallion's been thinking about your week. Five minutes in the microwave, one fork, zero apologies for the carb math. Subscribe, eat, go to bed earlier.

---

## Anti-pattern sample 1

Discover the perfect blend of flavors with our carefully crafted Tandoori Cauliflower. Indulge your senses on a culinary journey that will tantalize your taste buds. Experience the difference today.

## Anti-pattern sample 2

Elevate your dinner experience with our chef-curated meals. Don't miss out on this limited time only — order today and unlock exclusive savings. Transform your weeknight routine.

## Anti-pattern sample 3

In today's fast-paced world, look no further than CookUnity for thoughtfully crafted meals that delight in every bite. A symphony of flavors awaits.

## Anti-pattern sample 4

Game-changing dinner solutions, carefully curated by world-class chefs. An unforgettable experience that will redefine the way you eat. Act now while supplies last.

## Anti-pattern sample 5

Savor every bite of our perfectly balanced, restaurant-quality meals. A feast for the senses, where flavor meets perfection. Every bite tells a story.
