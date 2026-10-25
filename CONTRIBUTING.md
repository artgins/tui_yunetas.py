# Contributing to the yunetas CLI

Thank you for wanting to improve `yunetas`, the command line of Yuneta. It is
part of Yuneta, the framework of ArtGins (https://github.com/artgins/yunetas),
and follows its rules.

## Before you start

- For anything beyond a small fix, open an issue first and say what you want
  to change and why: the shape of a change is cheaper to agree on before it
  is written.
- Read the `CLAUDE.md` of this repository and the one of yunetas: they carry
  the rules every change follows (braces on every block, also in Python, no
  silent errors, and the build, deploy and release flows this CLI drives,
  which must stay in step with `docs/doc.yuneta.io/deploying-yunos.md` of
  yunetas).
- Everything committed is in English: code, comments, docs, commit messages.

## Build and test

```sh
python3 -m venv /tmp/venv-yunetas
/tmp/venv-yunetas/bin/pip install -e . pytest
/tmp/venv-yunetas/bin/python -m pytest tests
```

A change comes with the test that shows it: a fix with the case that failed,
a feature with the cases it promises. A release bumps the version (each
segment is one digit, see `CLAUDE.md`) and has its section in `CHANGELOG.md`.

## Code of others

Do not paste code you did not write unless its license allows it in an MIT
project and you say where it comes from; then it keeps its notice, and its
license is recorded in the same pull request. Code under the GPL, AGPL or
LGPL, under CC BY-SA (answers of StackOverflow and other Q&A sites), or with
no license at all (most gists) cannot come in.

Code written with an AI assistant is welcome, under the same rule: you have
read it, you answer for it, and you say so in the commit (a `Co-Authored-By:`
line).

## Contributor License Agreement

Before ArtGins can merge your first pull request, you must agree to the
Contributor License Agreement of the Yuneta projects:
https://github.com/artgins/yunetas/blob/main/CLA.md

You keep the copyright of your contribution. The CLA gives ArtGins the right
to distribute it under the license of the project and under other licenses,
which is what lets Yuneta be offered under more than one license. To agree,
write this line in the description of your pull request, with your name and
email:

    I have read the CLA of the Yuneta projects (CLA.md, version 1.0) and I
    agree to it for this contribution and my future ones.
    Name: <your name>   Email: <your email>

If you contribute as part of your job, your employer may have to sign a
corporate agreement first: write to support@artgins.com.

## License

By contributing, you agree that your contribution is distributed under the
MIT License of `LICENSE`, and under the terms of the CLA.
