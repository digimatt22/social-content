# Phase 1 Marketing Agent

Build Phase 1 of a Marketing Operating System for MattMadeMe.

## Business Context

The authoritative business information is stored in:

- `docs/business/company-profile.md`
- `docs/business/business-goals.md`
- `docs/business/products.md`
- `docs/business/audiences.md`
- `docs/business/brand-voice.md`
- `docs/business/marketing-channels.md`

Use these files as the sole source of truth for business context, business goals, products, audiences, brand voice, and marketing channels.

Review and understand these files before creating an implementation plan.

## Objective

Create a local-first marketing assistant that helps a solo business owner consistently market MattMadeMe across its sales and marketing channels.

The system should act as a marketing manager and planning assistant, not a fully autonomous marketing platform.

## Required Capabilities

### 1. Business Knowledge Base

- Load and use business information from the `docs/business` directory.
- Allow business information to be updated without code changes.
- Use business goals to evaluate whether generated tactics are strategically useful.

### 2. Content Generation

- Generate Instagram post ideas.
- Generate Instagram Reel ideas.
- Generate Facebook post ideas.
- Generate Etsy promotion ideas.
- Generate blog topic ideas.
- Generate email newsletter ideas.

### 3. Marketing Planning

- Generate a 30-day content calendar.
- Assign platform, objective, CTA, and featured product.

### 4. Weekly Marketing Report

- Summarize planned content.
- Identify opportunities.
- Recommend priorities.
- Highlight seasonal opportunities.

### 5. Recommendation Engine

- Suggest high-impact marketing actions.
- Prioritize recommendations by effort and expected impact.
- Tie each recommendation to at least one business goal.

## Technical Constraints

- Python preferred.
- Local-first architecture.
- Open-source components preferred.
- Modular architecture.
- Future integrations should be easy to add.
- Use interfaces/adapters where future external integrations would exist.

## Out Of Scope

Do not implement:

- Etsy API integration
- Instagram API integration
- Facebook API integration
- Google Analytics integration
- Search Console integration
- Automated content publishing

Create extension points and mock implementations instead.

## Definition Of Done

The project is complete when:

1. A user can clone the repository and run the application.
2. The application successfully loads business context from the `docs/business` directory.
3. The application can generate a complete 30-day marketing calendar.
4. The application can generate:
   - 30 Instagram post ideas
   - 30 Facebook post ideas
   - 10 Reel ideas
   - 10 Blog ideas
   - 10 Email newsletter ideas
5. The application can generate a weekly marketing report.
6. The application can generate prioritized marketing recommendations.
7. Documentation exists for installation, configuration, and usage.
8. An end-to-end demo workflow executes successfully.

## Acceptance Criteria

### AC1 - Business Knowledge

- Business context is loaded from `docs/business`.
- No business information is hardcoded.
- Changes to business files are reflected without code modifications.
- Business goals are loaded from `docs/business/business-goals.md`.

### AC2 - Content Generation

- Generated content follows the defined brand voice.
- Generated content references relevant products and audiences.
- Generated content includes appropriate calls-to-action.

### AC3 - Content Calendar

- Generates a complete 30-day calendar.
- Each entry includes:
  - date
  - platform
  - content type
  - objective
  - CTA
  - featured product

### AC4 - Recommendations

- Recommendations include:
  - aligned business goal
  - impact estimate
  - effort estimate
  - rationale

### AC5 - Reporting

- Weekly report summarizes:
  - planned activities
  - recommended actions
  - opportunities

### AC6 - Documentation

- README includes installation, configuration, and usage instructions.
- Architecture documentation explains system structure and extension points.

### AC7 - Demonstration

- End-to-end workflow completes successfully using the provided business files.

## Success Metric

A MattMadeMe owner can spend less than 30 minutes per week generating a complete marketing plan, content ideas, and prioritized recommendations for the upcoming week.
