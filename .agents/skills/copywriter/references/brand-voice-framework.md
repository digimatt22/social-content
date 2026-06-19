# Brand Voice Framework

Use supplied voice guidance first. If no voice is supplied, infer a provisional voice from examples, product details, audience, and destination, then state that it is inferred.

## Voice Inputs

Look for:

- Personality: warm, expert, playful, premium, practical, rebellious, calm.
- Formality: casual, polished, technical, conversational.
- Energy: restrained, upbeat, urgent, thoughtful.
- Vocabulary: preferred phrases, banned phrases, industry terms.
- Proof style: story, data, craft, customer outcome, authority.
- CTA style: direct, invitational, educational, community-oriented.

## Applying Voice

Preserve the facts while adapting:

- Sentence length.
- Word choice.
- Rhythm.
- Amount of humor.
- Level of detail.
- CTA tone.

Do not force catchphrases into every asset. Consistency means recognizable judgment, not repeated wording.

## Voice Summary Output

When useful, include:

```json
{
  "voice_used": "warm, practical, lightly playful",
  "voice_evidence": ["source phrase or instruction"],
  "assumptions": ["voice inferred from product details"]
}
```
