# Phase 5 Operator Workflow Proof

Date: 2026-06-17

## Scenario

This proof covers the local-app workflow that Phase 5 needs before it can be considered operational:

1. Create a planned marketing item.
2. Run content production.
3. Approve generated Facebook copy.
4. Create a posting task from the planned item and approved candidate.
5. Mark the task posted.
6. Record outcome metrics and qualitative outcome tags.
7. Confirm Insights links the outcome back to generated copy, product, channel, and task.

## Automated Evidence

Covered by:

```text
tests/test_phase3.py::Phase3LocalWebConsoleTests::test_phase5_web_operator_workflow_posts_generated_copy_and_records_outcome
```

The test uses the Flask web/API surface rather than only direct service calls.

## Workflow Details

- Planned item destination: Facebook
- Goal: Sales growth
- Product focus: Bingo Duck
- Audience: gift buyers
- Occasion: new batch
- Generated candidate type: `facebook_post`
- Review state: `approved`
- Created task platform: Facebook
- Posted URL placeholder: `https://facebook.example/mattmademe/proof`
- Outcome tags: `sold item`, `got comments`
- Metric fields recorded: reach, likes, comments, Etsy order note

## What This Proves

- Planning intent can become generated copy without final copy being written at planning time.
- Generated copy must be reviewed before it becomes task copy.
- The approved candidate can create a real posting task.
- The task can move through posted and metric-recorded states.
- Manual outcome notes and tags can feed the Insights learning loop.

## What This Does Not Prove

- It does not prove that the content was actually posted to Facebook.
- It does not replace Matt's human taste review.
- It does not prove a real Freepik/Magnific generated image is good enough to approve.
