# Contributing

The project follows a small set of written rules. The full text is in [`AGENTS.md`](AGENTS.md) and
[`docs/projet/REGLES_DES_AGENTS.md`](docs/projet/REGLES_DES_AGENTS.md) (French); the essentials:

1. **One path for robot orders**: brain → guardian (ticket) → socket → adapter. Do not add another.
2. **Do not touch** `briques/b01_prise/prise.py`, `briques/b01_prise/ticket.py` or `briques/b07_gardien/` without the
   security reviewer.
3. **Say what was tested.** "Tested on fake robot" or "tested on real robot", never one passed off as the other.
   Anything not tested goes into [`NON_TESTE.md`](NON_TESTE.md).
4. **Do not invent** a function, a number, a link or a compatibility. If it was not read in a source, write "to verify".
5. **Licences.** MIT, Apache and BSD with attribution in [`LICENCES.md`](LICENCES.md). GPL or AGPL: ask first.
6. **The author is not the reviewer.**
7. **Before calling something done**, the whole suite passes:

```bash
python3 lancer.py tests
```

A real robot is only ever driven through the procedure in [`BRANCHER_UN_ROBOT.md`](BRANCHER_UN_ROBOT.md), started by a human.
