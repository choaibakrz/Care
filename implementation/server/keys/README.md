# Keys — never commit them

The clinic server creates two secret files here the first time it runs (see `../docs/dev-setup.md`):

- `journal.key` (and `journal.key.pub`): the key that signs the audit journal;
- `account.pepper`: the secret that protects account identifiers.

They are listed in `.gitignore`. A pair of keys was committed by mistake in an earlier, private working repository:
**those keys must be considered public and must not be reused.** Generate new ones.
