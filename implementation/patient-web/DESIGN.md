# Patient companion web app — design brief

## Scope

This is a patient-facing companion, separate from the staff/admin consoles. It
creates care requests for the care team and shows their status. It never drives
the robot, exposes patient records, or invents medical advice.

## Security boundary

The patient app uses a Vercel API boundary backed by Supabase Auth and
patient-scoped tables. Requests, questions, mood check-ins and the daily plan
are stored per authenticated account. A static preview can still fall back to
in-memory demo data, but the deployed app never connects directly to the
robot, model service, or database.

## Wireframe

```text
+-------------------------------------------------------------+
| Care                                 EN  FR  DE     Help    |
| Room 212 · North wing       Connection secure               |
+-------------------------------------------------------------+
| Good afternoon, Alex                         [Need help?]   |
| Your care team is nearby.                                    |
|                                                             |
| [Request support] [Interpreter] [Privacy status]             |
|                                                             |
| Active request                                               |
| Blanket  ·  On the way                         [View]        |
| [received] ---- [assigned] ---- [on the way] ---- [delivered]|
|                                                             |
| What would make you more comfortable?                        |
| [Water] [Blanket] [Wheelchair] [Call care team]              |
+-------------------------------------------------------------+
| Home              My requests              Support           |
+-------------------------------------------------------------+
```

## Visual direction

- Warm and human, still clearly medical: cream paper, warm ink, terracotta for
  the main action, teal for care and trust, soft tones per request type.
- Logo: a rounded medical cross in warm-to-teal tones with a heart at its centre
  (`favicon.svg`, also used as the brand mark).
- Serif headings for warmth, system sans for reading; large touch targets.
- The hero window illustration and the greeting follow the real time of day
  (morning, afternoon, evening, night).
- A mood check-in lets the patient tell the care team how they feel; a low
  answer offers to call someone.
- No robot imagery: requests go to people first; the delivery assistant is only
  mentioned for small items.
- All dynamic text is inserted with `textContent`; texts live in `copy.js`
  (EN, FR, DE, chosen from the browser language).
- Reduced-motion support is mandatory.
