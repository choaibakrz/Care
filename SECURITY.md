# Security

This is a hackathon prototype. It is not certified and must not be used with patients or near people without a
trained operator and a physical stop button within reach.

## Reporting a problem

If you find a way to make a robot act without a ticket from the guardian, to bypass a limit, or to read data you
should not, please open a **private security advisory** on this repository (Security → Advisories → Report a
vulnerability) rather than a public issue.

## What to know before running it

- **Secrets are never committed.** `reglages.yaml`, `.env` files and `implementation/server/keys/` are ignored by git.
  Two server keys were committed by mistake in an earlier private working repository; they are not in this one and
  must be treated as public. Generate new ones.
- **The stop button of the screens is open to everyone on the network by design.** Anyone who can reach the screen can
  stop the robot. Use a private network (the team used a phone hotspot), never a shared Wi-Fi.
- **Reception does not verify identity.** The known ways to fool it are listed in [`NON_TESTE.md`](NON_TESTE.md).
- **Patient data is invented.** Do not load real data.

The safety model, and what it does not cover, is described in [`docs/SAFETY.md`](docs/SAFETY.md).
