# Security Policy

## Reporting a vulnerability

Please report security issues privately. Do not open a public issue for them.

Use GitHub's **Report a vulnerability** button on the repository's **Security** tab, or
open the advisory form directly at
https://github.com/IACBI/DS2_To_Mp3_Converter/security/advisories/new. Include the steps
to reproduce, the affected version or commit, and, if possible, a small sample file that
triggers the problem.

## Scope

In scope:

- Crafted `.DS2` files that crash the converter, hang it, or exhaust memory or disk.
- Unsafe file writes, such as writing outside the output directory or through a
  symlink the user did not expect.
- Terminal injection through header fields that reach the console.

Out of scope:

- Problems that need an attacker who already has write access to your files or
  account.
- Issues in Python, NumPy, lameenc, or mutagen themselves. Report those upstream.

## Intended use

The converter is meant for local use on files you trust or have reviewed. If you
must process recordings from an untrusted source, run it under a normal, non-admin
account, in a folder that holds nothing else you care about.
