# Image Creator Examples

## Built-In Image Generation

Input:

```json
{
  "destination": "newsletter",
  "format": "hero image",
  "audience": "past customers",
  "goal": "announce a cozy winter launch",
  "subject": "handmade gift products on a warm workbench",
  "brand_style": "warm, handmade, softly lit",
  "provider_path": "built-in"
}
```

Output shape:

- Final image prompt.
- Aspect ratio.
- Avoid list.
- Review checklist.

## Magnific/Freepik MCP

Input:

```json
{
  "destination": "instagram",
  "format": "square product scene",
  "subject": "exact product from references in a realistic environment",
  "reference_images": ["front.jpg", "side.jpg", "detail.jpg"],
  "provider_path": "magnific-mcp"
}
```

Output shape:

- Reference image roles.
- Product-preserving prompt.
- MCP handoff steps.
- Review checklist.
