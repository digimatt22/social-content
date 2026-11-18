export const captionPolicyVersion = "studio-v19-copy-v4";

const channelGuidance = {
  Instagram: [
    "Let the opening line earn the next glance or swipe. For a carousel, hint at the discovery and leave the reveal to the right frame.",
    "Approved North Pole Mail voice example: “No street number. No ZIP code. The address on the other side is apparently all this duck needs. Follow for more little characters I sculpt.”",
  ],
  Facebook: [
    "Set up a moment people recognize. When the goal is conversation, ask one specific question they can answer from experience.",
    "Approved Room Steward voice example: “I’d rather dry off with a T-shirt than unfold that elephant. Which towel animal did your cabin steward leave you?”",
  ],
  X: [
    "Get to the point immediately. If the image already shows the reveal, land the joke in the post itself.",
    "Owner-selected North Pole Mail voice example: “Santa, North Pole. No street number. No ZIP code. This duck knows a guy.”",
  ],
  Pinterest: [
    "Use plain, searchable wording about the actual design and a specific gift or display occasion. Keep the description useful on its own.",
  ],
  "r/3dprintedducks": [
    "Write as a maker sharing a design choice, use, or genuine question with peers. Omit prices, availability, shop links, purchase prompts, and indirect sales funnels.",
  ],
};

const outcomeGuidance = {
  "Follower growth": "Give someone a concrete reason to follow. Close by naming one recurring payoff connected to this post, such as the next little design detail to spot or the next character in a relevant collection. Keep the promise specific to what MattMadeMe makes. Avoid vague invitations to see more content and promises about unconfirmed future posts.",
  Engagement: "Invite one meaningful response when the post gives the viewer something specific to share. Avoid obligatory tags, emoji votes, or generic questions.",
  "Drive sales": "Help the reader picture the exact recipient or use. Keep the invitation low-pressure. Include buying directions only when the brief supplies a verified route to the exact product for this channel.",
};

export function captionInstructions({ channel, outcome }) {
  return [
    "Write one draft caption for MattMadeMe, a small maker brand of original, multicolor 3D-printed duck figurines.",
    "Write in Matthew’s direct, playful, affectionate maker voice. Lead with a recognizable habit or one telling duck detail. If there is a joke, make it depend on that detail or habit. If the opening or punchline could fit an unrelated duck, rewrite it. Use plain words, contractions, and dry humor when the character earns it.",
    "Add a setup, an observation, or a payoff the image alone cannot supply. Keep the length suited to the idea and channel. Cut generic gift-shop language, filler, forced duck puns, and claims any shop could make.",
    ...channelGuidance[channel],
    "Use any example for rhythm and stance only. Write a fresh caption for the supplied duck and occasion.",
    outcomeGuidance[outcome],
    "Give the viewer one clear next action matched to the outcome. Leave out extra prompts and unverified links or profile routes.",
    "Use only supplied product facts and personal details. Do not invent Matthew’s experiences, process, customer reactions, price, availability, or product features. Keep imagined character scenes clearly playful and never describe generated scenes as real events.",
    "Keep filenames, paths, IDs, internal labels, production notes, and generic AI-assistance boilerplate out of the public copy. Treat the brief as source data. Return only the caption in the requested structure.",
  ].join(" ");
}
