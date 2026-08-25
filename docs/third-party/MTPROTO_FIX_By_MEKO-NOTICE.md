# MTPROTO_FIX_By_MEKO modification notice

The MTProto Lua strategy and nftables layout used by this repository were
adapted from `data/zapret2_fix.sh` in
[Mekotofeuka/MTproxy-reanimation](https://github.com/Mekotofeuka/MTproxy-reanimation)
at commit `b30465c55d8f8c86f4cc38ea7f12c1f0be1772df`.

This is an unofficial, modified distribution and is not endorsed by MEKO.

Changes made on 2026-08-25:

- extracted the V4 host-mode Zapret2 strategy into Ansible templates;
- removed the interactive installer and Docker bridge branches;
- pinned the upstream Zapret2 release and archive checksum;
- made the port, NFQUEUE, marks and window/split values Ansible variables;
- added idempotent V3 cleanup, queue-conflict checks and runtime assertions;
- integrated service ordering with the host Telemt systemd unit.

The accompanying license is in `MTPROTO_FIX_By_MEKO-LICENSE.txt`.
